from pathlib import Path
from typing import Optional
import json
import markdown  # type: ignore

from PySide6.QtCore import (
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Slot,
    QObject,
    QUrl,
    QEvent,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLabel,
    QTextBrowser,
    QSizePolicy,
    QApplication,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from qfluentwidgets import ElevatedCardWidget, TextEdit


class Bridge(QObject):
    @Slot(str)
    def startDrag(self, temp_id: str):
        # We will handle the drag logic later
        print(f"Dragging image with UUID: {temp_id}")


class QuestionBlockWidget(ElevatedCardWidget):
    """
    流式双态题目块 (Flyweight Pattern)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QuestionBlockWidget")

        # Private data bindings
        self._markdown_source = ""
        self._question_number = 1

        self._is_editing = False

        # Setup layouts
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(5)

        # Header
        self.header_label = QLabel(f"题号: {self._question_number}")
        self.header_label.setStyleSheet("font-weight: bold; color: #5c5c5c;")
        self.main_layout.addWidget(self.header_label)

        # Content Container (Fixed height for preview or animated)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(5)
        self.main_layout.addWidget(self.content_widget)

        # Preview State Widget (Lightweight)
        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(False)
        self.preview_browser.setReadOnly(True)
        self.preview_browser.setStyleSheet("border: none; background: transparent;")
        self.preview_browser.setMinimumHeight(60)
        self.preview_browser.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.MinimumExpanding
        )
        self.content_layout.addWidget(self.preview_browser)

        # Edit State Widgets (None initially)
        self.web_view: Optional[QWebEngineView] = None
        self.text_edit: Optional[TextEdit] = None
        self.web_channel: Optional[QWebChannel] = None
        self.bridge = Bridge(self)

        # Debounce Timer
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(300)
        self.debounce_timer.timeout.connect(self._sync_preview)

        # Animation
        self.animation = QPropertyAnimation(self, b"minimumHeight")
        self.animation.setDuration(250)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self._update_preview_content()

    def set_question_number(self, num: int):
        self._question_number = num
        self.header_label.setText(f"题号: {self._question_number}")

    def set_markdown(self, text: str):
        self._markdown_source = text
        if self._is_editing and self.text_edit:
            self.text_edit.setPlainText(text)
        else:
            self._update_preview_content()

    def _compile_markdown(self) -> str:
        # Use md_in_html extension to better support custom tags and MathJax block skipping
        return markdown.markdown(self._markdown_source, extensions=["md_in_html"])

    def _update_preview_content(self):
        # Convert markdown to basic HTML for preview (without MathJax support)
        html_content = self._compile_markdown()
        # Use simple QTextBrowser for Preview
        self.preview_browser.setHtml(html_content)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._is_editing:
            self._enter_edit_state()
        super().mouseDoubleClickEvent(event)

    def _enter_edit_state(self):
        self._is_editing = True

        # Hide preview browser
        self.preview_browser.hide()

        # Instantiate WebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setMinimumHeight(150)

        # Setup QWebChannel
        self.web_channel = QWebChannel(self.web_view.page())
        # Reuse the existing bridge instance
        self.web_channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.web_channel)

        # Load local HTML template
        # Use a dynamic root finder from config or default to a safe known anchor

        # Traverse up to find the root by looking for main.py or resources to be robust against file moves
        current_dir = Path(__file__).resolve()
        while (
            current_dir.parent != current_dir
            and not (current_dir / "resources" / "templates").exists()
        ):
            current_dir = current_dir.parent
        template_path = (
            current_dir / "resources" / "templates" / "question_template.html"
        )
        self.web_view.setUrl(QUrl.fromLocalFile(str(template_path)))

        # Wait for page to load to inject initial content
        self.web_view.loadFinished.connect(self._on_web_view_loaded)

        # Instantiate TextEdit
        self.text_edit = TextEdit()
        self.text_edit.setPlainText(self._markdown_source)
        self.text_edit.setMinimumHeight(150)
        self.text_edit.textChanged.connect(self._on_text_changed)

        # Add to layout
        self.content_layout.addWidget(self.web_view)
        self.content_layout.addWidget(self.text_edit)

        # Animate expansion
        current_height = self.height()

        # Force layout update to calculate accurate target height
        self.layout().activate()
        self.updateGeometry()
        target_height = self.minimumSizeHint().height()

        self.animation.setStartValue(current_height)
        self.animation.setEndValue(target_height)
        self.animation.start()

        # Request focus on text edit
        self.text_edit.setFocus()
        self.text_edit.installEventFilter(self)

    def _on_web_view_loaded(self, ok):
        if ok:
            self._sync_preview()

    def _on_text_changed(self):
        if not self._is_editing or not self.text_edit:
            return
        self._markdown_source = self.text_edit.toPlainText()
        self.debounce_timer.start()

    def _sync_preview(self):
        if not self.web_view:
            return

        # Convert markdown to HTML
        html_content = self._compile_markdown()

        safe_html = json.dumps(html_content)

        js_code = f"""
        (function() {{
            const container = document.getElementById('math-content');
            if (container) {{
                container.innerHTML = {safe_html};
                if (typeof MathJax !== 'undefined') {{
                    MathJax.typesetPromise([container]).catch(function (err) {{
                        console.log(err.message);
                    }});
                }}
            }}
        }})();
        """
        self.web_view.page().runJavaScript(js_code)

    def eventFilter(self, obj, event):
        if self.text_edit and obj == self.text_edit and event.type() == QEvent.FocusOut:
            # Check in the next event loop cycle to allow focus to settle
            QTimer.singleShot(0, self._check_focus_and_exit)
        return super().eventFilter(obj, event)

    def _check_focus_and_exit(self):
        focused = QApplication.focusWidget()
        # If no widget has focus, the application likely lost focus to another window.
        # We should only exit edit mode if focus moved to another widget within our app.
        if not focused or focused == self or self.isAncestorOf(focused):
            return
        self._exit_edit_state()

    def _exit_edit_state(self):
        if not self._is_editing:
            return

        self.debounce_timer.stop()
        self._is_editing = False

        if self.text_edit:
            self.text_edit.hide()
            self.content_layout.removeWidget(self.text_edit)
            self.text_edit.removeEventFilter(self)
            self.text_edit.deleteLater()
            self.text_edit = None

        if self.web_view:
            self.web_view.hide()
            self.content_layout.removeWidget(self.web_view)
            self.web_view.deleteLater()
            self.web_view = None
            self.web_channel = None

        self._update_preview_content()
        self.preview_browser.show()

        # Force layout to recalculate size hint before animating
        self.layout().activate()
        self.updateGeometry()

        self.animation.setStartValue(self.height())
        self.animation.setEndValue(self.minimumSizeHint().height())
        self.animation.start()
