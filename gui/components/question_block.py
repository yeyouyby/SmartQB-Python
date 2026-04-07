from pathlib import Path
from typing import Optional
import json
import bleach  # type: ignore
from bleach.css_sanitizer import CSSSanitizer  # type: ignore
import logging
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
        logging.info(f"Dragging image with UUID: {temp_id}")


class QuestionBlockWidget(ElevatedCardWidget):
    """
    流式双态题目块 (Flyweight Pattern)
    """

    # Shared Flyweight Instances
    _shared_web_view: Optional[QWebEngineView] = None
    _shared_web_channel: Optional[QWebChannel] = None
    _shared_load_connection = None
    _current_editing_block = None

    @classmethod
    def cleanup_shared_resources(cls):
        if cls._shared_web_view:
            cls._shared_web_view.deleteLater()
            cls._shared_web_view = None
            cls._shared_web_channel = None
            cls._shared_load_connection = None
            cls._current_editing_block = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QuestionBlockWidget")

        # Private data bindings
        self._markdown_source = ""
        self._question_number = 1

        self._is_editing = False
        self._has_arithmatex: bool = False

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
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("border: none; background: transparent;")
        self.preview_label.setMinimumHeight(60)
        self.preview_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.MinimumExpanding
        )
        self.content_layout.addWidget(self.preview_label)

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
        # Combine extensions for better support and handle potential missing dependencies
        extensions = ["md_in_html"]
        if hasattr(self, "_has_arithmatex"):
            if self._has_arithmatex:
                extensions.append("pymdownx.arithmatex")
        else:
            try:
                import pymdownx.arithmatex  # noqa: F401

                extensions.append("pymdownx.arithmatex")
                self._has_arithmatex = True
            except ImportError:
                logging.warning(
                    "pymdownx.arithmatex not found, math rendering may be limited."
                )
                self._has_arithmatex = False

        raw_html = markdown.markdown(self._markdown_source, extensions=extensions)

        # Sanitize HTML to prevent XSS
        allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
            "p",
            "div",
            "span",
            "br",
            "img",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "pre",
            "code",
            "blockquote",
        ]
        allowed_attrs = {
            "*": ["class", "id", "style"],
            "img": ["src", "alt", "title", "width", "height", "data-uuid"],
            "a": ["href", "title"],
        }

        css_sanitizer = CSSSanitizer()
        sanitized_html = bleach.clean(
            raw_html,
            tags=allowed_tags,
            attributes=allowed_attrs,
            css_sanitizer=css_sanitizer,
            strip=True,
        )
        return sanitized_html

    def _update_preview_content(self):
        # Convert markdown to HTML
        html_content = self._compile_markdown()

        # If we have a shared web view (from exiting edit state), we can use it to grab a snapshot
        # For initial load, we fallback to simple rich text without math support unless we create a dedicated renderer
        if (
            QuestionBlockWidget._shared_web_view
            and self.web_view == QuestionBlockWidget._shared_web_view
        ):
            # We are exiting edit mode, the web_view currently holds our rendered content
            # Let's take a snapshot right before we hide it
            pixmap = self.web_view.grab()
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")
        else:
            # Simple rich text fallback for initial load (won't render JS math)
            self.preview_label.setText(html_content)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._is_editing:
            self._enter_edit_state()
        super().mouseDoubleClickEvent(event)

    def _enter_edit_state(self):
        # Enforce single active edit state globally
        if (
            QuestionBlockWidget._current_editing_block is not None
            and QuestionBlockWidget._current_editing_block != self
        ):
            QuestionBlockWidget._current_editing_block._exit_edit_state()

        QuestionBlockWidget._current_editing_block = self
        self._is_editing = True

        # Hide preview browser
        self.preview_label.hide()

        # Leverage Flyweight pattern for WebEngineView
        view_just_created = False
        if QuestionBlockWidget._shared_web_view is None:
            QuestionBlockWidget._shared_web_view = QWebEngineView()
            QuestionBlockWidget._shared_web_view.setMinimumHeight(150)
            view_just_created = True

            QuestionBlockWidget._shared_web_channel = QWebChannel(
                QuestionBlockWidget._shared_web_view.page()
            )
            QuestionBlockWidget._shared_web_view.page().setWebChannel(
                QuestionBlockWidget._shared_web_channel
            )

            template_path = (
                Path(__file__).resolve().parents[2]
                / "resources"
                / "templates"
                / "question_template.html"
            )
            QuestionBlockWidget._shared_web_view.setUrl(
                QUrl.fromLocalFile(str(template_path))
            )

        self.web_view = QuestionBlockWidget._shared_web_view
        self.web_channel = QuestionBlockWidget._shared_web_channel

        # Connect bridge and load callback
        # We must disconnect old bindings first to avoid firing signals multiple times
        if QuestionBlockWidget._shared_load_connection is not None:
            try:
                QObject.disconnect(QuestionBlockWidget._shared_load_connection)
                QuestionBlockWidget._shared_load_connection = None
            except (RuntimeError, TypeError):
                pass

        QuestionBlockWidget._shared_load_connection = (
            self.web_view.loadFinished.connect(self._on_web_view_loaded)
        )

        # Clear out any old objects in the channel if they exist
        if "pyBridge" in self.web_channel.registeredObjects():
            self.web_channel.deregisterObject(
                self.web_channel.registeredObjects()["pyBridge"]
            )

        self.web_channel.registerObject("pyBridge", self.bridge)

        # We also need to re-parent the web view to the current widget layout
        if (
            self.web_view.parentWidget() is not None
            and self.web_view.parentWidget() != self.content_widget
        ):
            self.web_view.setParent(None)

        # If it's already loaded (not just created), we sync immediately
        if (
            not view_just_created
            and self.web_view.url().isValid()
            and not self.web_view.url().isEmpty()
        ):
            self._on_web_view_loaded(True)

        # Instantiate TextEdit
        self.text_edit = TextEdit()
        self.text_edit.setPlainText(self._markdown_source)
        self.text_edit.setMinimumHeight(150)
        self.text_edit.textChanged.connect(self._on_text_changed)

        # Add to layout
        self.content_layout.addWidget(self.web_view)
        self.web_view.show()
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

    def _on_web_view_loaded(self, ok: bool):
        if ok:
            self._sync_preview()
        else:
            logging.error(f"Failed to load web engine content for {self.objectName()}.")

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
        if not hasattr(self, "text_edit"):
            return super().eventFilter(obj, event)
        if self.text_edit and obj == self.text_edit and event.type() == QEvent.FocusOut:
            # Check in the next event loop cycle to allow focus to settle
            QTimer.singleShot(0, self, self._check_focus_and_exit)
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
        self._has_arithmatex: bool = False
        if QuestionBlockWidget._current_editing_block == self:
            QuestionBlockWidget._current_editing_block = None

        if self.text_edit:
            self.text_edit.hide()
            self.content_layout.removeWidget(self.text_edit)
            self.text_edit.removeEventFilter(self)
            self.text_edit.deleteLater()
            self.text_edit = None

        # Capture snapshot before hiding if possible
        if self.web_view:
            self._update_preview_content()

        if self.web_view:
            self.web_view.hide()
            self.content_layout.removeWidget(self.web_view)
            # Re-parent to None so it doesn't get destroyed if parent gets destroyed, preserving the flyweight
            self.web_view.setParent(None)

            # Remove our bridge object to avoid memory leaks or crossing calls
            if "pyBridge" in self.web_channel.registeredObjects():
                self.web_channel.deregisterObject(self.bridge)

            self.web_view = None
            self.web_channel = None

        self.preview_label.show()

        # Force layout to recalculate size hint before animating
        self.layout().activate()
        self.updateGeometry()

        self.animation.setStartValue(self.height())
        self.animation.setEndValue(self.minimumSizeHint().height())
        self.animation.start()
