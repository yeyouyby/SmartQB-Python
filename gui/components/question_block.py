from pathlib import Path
from typing import Optional
import json
import bleach  # type: ignore
from bleach.css_sanitizer import CSSSanitizer  # type: ignore
import logging
import markdown  # type: ignore

try:
    import importlib.util

    HAS_ARITHMATEX = importlib.util.find_spec("pymdownx.arithmatex") is not None
    if not HAS_ARITHMATEX:
        logging.warning("pymdownx.arithmatex not found, math rendering may be limited.")
except ImportError:
    HAS_ARITHMATEX = False

from PySide6.QtCore import (
    QMimeData,
    Signal,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Slot,
    QObject,
    QUrl,
    QEvent,
)
from PySide6.QtGui import QMouseEvent, QDragEnterEvent, QDropEvent, QDrag

from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLabel,
    QSizePolicy,
    QApplication,
)
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from qfluentwidgets import ElevatedCardWidget, TextEdit


class Bridge(QObject):
    snapshotReadySignal = Signal(int)
    dragRequestedSignal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str)
    def startDrag(self, temp_id: str):
        logging.info(f"Drag requested from JS for image UUID: {temp_id}")
        self.dragRequestedSignal.emit(temp_id)

    @Slot(int)
    def snapshotReady(self, height: int = 0):
        self.snapshotReadySignal.emit(height)


class DroppableTextEdit(TextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasText():
            text = e.mimeData().text()
            if text.startswith("smartqb-image-drag://"):
                e.acceptProposedAction()
                return
        super().dragEnterEvent(e)

    def dropEvent(self, e: QDropEvent):
        text = e.mimeData().text()
        if text.startswith("smartqb-image-drag://"):
            temp_id = text[len("smartqb-image-drag://") :]
            cursor = self.cursorForPosition(e.pos())

            # Use beginEditBlock/endEditBlock to group undo
            cursor.beginEditBlock()
            cursor.insertText(f"\n![img]({temp_id})\n")
            cursor.endEditBlock()
            self.setTextCursor(cursor)

            e.acceptProposedAction()
            return
        super().dropEvent(e)


class QuestionBlockWidget(ElevatedCardWidget):
    """
    流式双态题目块 (Flyweight Pattern)
    """

    # Shared Flyweight Instances
    _shared_web_view: Optional[QWebEngineView] = None
    _shared_web_channel: Optional[QWebChannel] = None
    _shared_dummy_parent: Optional[QWidget] = None
    _shared_load_connection = None
    _shared_bridge: Optional["Bridge"] = None
    _current_editing_block: Optional["QuestionBlockWidget"] = None
    _css_sanitizer = CSSSanitizer(
        allowed_css_properties={
            "color",
            "background-color",
            "font-weight",
            "text-align",
            "width",
            "height",
        }
    )

    _DEBOUNCE_INTERVAL = 300
    _ANIMATION_DURATION = 250
    _MIN_PREVIEW_HEIGHT = 60
    _MIN_EDITOR_HEIGHT = 150
    _FALLBACK_CAPTURE_WIDTH = 400
    _QWIDGETSIZE_MAX = 16777215

    _ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
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
    _ALLOWED_ATTRS = {
        "*": ["class", "id", "style"],
        "img": ["src", "alt", "title", "width", "height", "data-uuid"],
        "a": ["href", "title"],
    }

    # Resolve project root statically
    _project_root = Path(__file__).resolve().parents[2]

    _RESOURCES_PATH = _project_root / "resources"
    _ASSETS_PATH = _RESOURCES_PATH / "assets"
    _TEMPLATE_FILE = _RESOURCES_PATH / "templates" / "question_template.html"

    if not _TEMPLATE_FILE.exists():
        logging.critical(f"Required template file not found: {_TEMPLATE_FILE}")
        raise FileNotFoundError(f"Required template file not found: {_TEMPLATE_FILE}")
    _HTML_TEMPLATE = _TEMPLATE_FILE.read_text(encoding="utf-8")

    @classmethod
    def cleanup_shared_resources(cls):
        if cls._shared_web_view:
            cls._shared_web_view.deleteLater()
            cls._shared_web_view = None
        if cls._shared_dummy_parent:
            cls._shared_dummy_parent.deleteLater()
            cls._shared_dummy_parent = None
        cls._shared_web_channel = None
        cls._shared_load_connection = None
        cls._current_editing_block = None
        cls._shared_bridge = None

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
        self.header_label = QLabel(self.tr("题号: ") + str(self._question_number))
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
        self.preview_label.setMinimumHeight(QuestionBlockWidget._MIN_PREVIEW_HEIGHT)
        self.preview_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.MinimumExpanding
        )
        self.content_layout.addWidget(self.preview_label)

        # Edit State Widgets (None initially)
        self.web_view: Optional[QWebEngineView] = None
        self.text_edit: Optional[DroppableTextEdit] = None
        self.web_channel: Optional[QWebChannel] = None
        # Debounce Timer
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(QuestionBlockWidget._DEBOUNCE_INTERVAL)
        self.debounce_timer.timeout.connect(self._sync_preview)

        # Animation
        self.animation = QPropertyAnimation(self, b"minimumHeight")
        self.animation.setDuration(QuestionBlockWidget._ANIMATION_DURATION)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.destroyed.connect(self._on_destroyed)
        self._update_preview_content()

    def set_question_number(self, num: int):
        self._question_number = num
        self.setObjectName(f"QuestionBlockWidget_{num}")
        self.header_label.setText(self.tr("题号: ") + str(self._question_number))

    def set_markdown(self, text: str):
        self._markdown_source = text
        if self._is_editing and self.text_edit:
            self.text_edit.setPlainText(text)
        else:
            self._update_preview_content()

    def _compile_markdown(self) -> str:
        # Combine extensions for better support and handle potential missing dependencies
        extensions = ["md_in_html"]
        if HAS_ARITHMATEX:
            extensions.append("pymdownx.arithmatex")

        raw_html = markdown.markdown(self._markdown_source, extensions=extensions)

        sanitized_html = bleach.clean(
            raw_html,
            tags=QuestionBlockWidget._ALLOWED_TAGS,
            attributes=QuestionBlockWidget._ALLOWED_ATTRS,
            css_sanitizer=QuestionBlockWidget._css_sanitizer,
            strip=True,
        )
        return sanitized_html

    def deleteLater(self):
        # Detach shared resources BEFORE Qt destroys children
        self._detach_shared_resources()
        super().deleteLater()

    def _detach_shared_resources(self):
        try:
            # Safely check if this instance is the current owner of the shared resources
            if QuestionBlockWidget._current_editing_block == self:
                if QuestionBlockWidget._shared_load_connection is not None:
                    try:
                        if QuestionBlockWidget._shared_web_view:
                            QuestionBlockWidget._shared_web_view.loadFinished.disconnect(
                                QuestionBlockWidget._shared_load_connection
                            )
                        QuestionBlockWidget._shared_load_connection = None
                    except (RuntimeError, TypeError):
                        pass

                if (
                    QuestionBlockWidget._shared_web_view
                    and QuestionBlockWidget._shared_dummy_parent
                ):
                    QuestionBlockWidget._shared_web_view.setParent(
                        QuestionBlockWidget._shared_dummy_parent
                    )

                QuestionBlockWidget._current_editing_block = None

        except RuntimeError:
            # Clear the reference if the C++ object is dead
            QuestionBlockWidget._shared_web_view = None

    def _on_destroyed(self):
        # Fallback if deleteLater wasn't explicitly called (e.g. parent destroyed natively)
        self._detach_shared_resources()

    def _cleanup_edit_widgets(self):
        # Clean up bridge signal
        if QuestionBlockWidget._shared_bridge:
            try:
                QuestionBlockWidget._shared_bridge.dragRequestedSignal.disconnect(
                    self._on_drag_requested
                )
            except (RuntimeError, TypeError):
                pass

        if self.web_view:
            self.web_view.hide()
            self.content_layout.removeWidget(self.web_view)
            if QuestionBlockWidget._shared_dummy_parent:
                self.web_view.setParent(QuestionBlockWidget._shared_dummy_parent)

        if QuestionBlockWidget._shared_bridge:
            try:
                QuestionBlockWidget._shared_bridge.snapshotReadySignal.disconnect(
                    self._capture_snapshot
                )
            except (RuntimeError, TypeError):
                pass  # Ignore if already disconnected or C++ object is dead

        if self.text_edit:
            self.content_layout.removeWidget(self.text_edit)
            self.text_edit.removeEventFilter(self)
            self.text_edit.deleteLater()
            self.text_edit = None

        self.web_view = None
        self.web_channel = None

    def _capture_snapshot(self, content_height: int = 0):
        if not self.web_view or self._is_editing:
            return

        # Ensure we capture exactly the content height (with a minimum)
        # and maintain the current width since it's removed from layout
        target_height = max(content_height, QuestionBlockWidget._MIN_EDITOR_HEIGHT)

        # Ensure width is valid even if layout is temporarily collapsed
        target_width = max(
            self.content_widget.width(), QuestionBlockWidget._FALLBACK_CAPTURE_WIDTH
        )
        self.web_view.setFixedSize(target_width, target_height)

        # Use a small delay to allow the browser to reflow and paint at the new size
        QTimer.singleShot(100, self, self._perform_grab)

    def _perform_grab(self):
        if not self.web_view or self._is_editing:
            return

        # Force a full layout and grab
        pixmap = self.web_view.grab()
        if not pixmap.isNull():
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")

        # Restore original geometry properties
        self.web_view.setMinimumHeight(QuestionBlockWidget._MIN_EDITOR_HEIGHT)
        self.web_view.setMaximumHeight(
            QuestionBlockWidget._QWIDGETSIZE_MAX
        )  # QWIDGETSIZE_MAX

        self._cleanup_edit_widgets()

    def _update_preview_content(self):
        # Convert markdown to HTML
        html_content = self._compile_markdown()
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
            QuestionBlockWidget._current_editing_block._exit_edit_state(force_sync=True)

        QuestionBlockWidget._current_editing_block = self
        self._is_editing = True

        # Hide preview browser
        self.preview_label.hide()

        # Leverage Flyweight pattern for WebEngineView
        view_just_created = False

        # Ensure shared view is still valid (not deleted by Qt)
        if QuestionBlockWidget._shared_web_view is not None:
            try:
                QuestionBlockWidget._shared_web_view.parent()
            except RuntimeError:
                QuestionBlockWidget._shared_web_view = None

        if QuestionBlockWidget._shared_web_view is None:
            # Create a dedicated hidden parent to prevent top-level window behavior
            QuestionBlockWidget._shared_dummy_parent = QWidget()
            QuestionBlockWidget._shared_dummy_parent.hide()

            QuestionBlockWidget._shared_web_view = QWebEngineView(
                QuestionBlockWidget._shared_dummy_parent
            )

            # Ensure scrollbars are enabled for live editing (snapshots naturally hide them via height expansion)

            QuestionBlockWidget._shared_web_view.settings().setAttribute(
                QWebEngineSettings.ShowScrollBars, True
            )

            QuestionBlockWidget._shared_web_view.setMinimumHeight(
                QuestionBlockWidget._MIN_EDITOR_HEIGHT
            )
            view_just_created = True

            QuestionBlockWidget._shared_web_channel = QWebChannel(
                QuestionBlockWidget._shared_web_view.page()
            )
            QuestionBlockWidget._shared_web_view.page().setWebChannel(
                QuestionBlockWidget._shared_web_channel
            )

            QuestionBlockWidget._shared_bridge = Bridge()
            QuestionBlockWidget._shared_web_channel.registerObject(
                "pyBridge", QuestionBlockWidget._shared_bridge
            )

            QuestionBlockWidget._shared_web_view.setHtml(
                QuestionBlockWidget._HTML_TEMPLATE,
                baseUrl=QUrl.fromLocalFile(str(QuestionBlockWidget._ASSETS_PATH) + "/"),
            )

        self.web_view = QuestionBlockWidget._shared_web_view
        self.web_view.setMinimumSize(0, QuestionBlockWidget._MIN_EDITOR_HEIGHT)
        self.web_view.setMaximumSize(
            QuestionBlockWidget._QWIDGETSIZE_MAX, QuestionBlockWidget._QWIDGETSIZE_MAX
        )
        self.web_channel = QuestionBlockWidget._shared_web_channel

        # Direct the shared bridge to this instance via Signal
        if QuestionBlockWidget._shared_bridge:
            QuestionBlockWidget._shared_bridge.snapshotReadySignal.connect(
                self._capture_snapshot
            )

        # Connect bridge and load callback
        # We must disconnect old bindings first to avoid firing signals multiple times
        if QuestionBlockWidget._shared_load_connection is not None:
            try:
                QuestionBlockWidget._shared_web_view.loadFinished.disconnect(
                    QuestionBlockWidget._shared_load_connection
                )
                QuestionBlockWidget._shared_load_connection = None
            except (RuntimeError, TypeError):
                pass

        # Connect bridge dragRequestedSignal
        if QuestionBlockWidget._shared_bridge:
            try:
                QuestionBlockWidget._shared_bridge.dragRequestedSignal.disconnect(
                    self._on_drag_requested
                )
            except (RuntimeError, TypeError):
                pass
            QuestionBlockWidget._shared_bridge.dragRequestedSignal.connect(
                self._on_drag_requested
            )

        QuestionBlockWidget._shared_load_connection = (
            self.web_view.loadFinished.connect(self._on_web_view_loaded)
        )

        # If it's already loaded (not just created), we sync immediately
        if (
            not view_just_created
            and self.web_view.url().isValid()
            and not self.web_view.url().isEmpty()
        ):
            self._on_web_view_loaded(True)

        # Instantiate TextEdit
        self.text_edit = DroppableTextEdit()
        self.text_edit.setPlainText(self._markdown_source)
        self.text_edit.setMinimumHeight(QuestionBlockWidget._MIN_EDITOR_HEIGHT)
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

    def _on_drag_requested(self, temp_id: str):
        if not self.web_view:
            return
        drag = QDrag(self.web_view)
        mime_data = QMimeData()
        mime_data.setText(f"smartqb-image-drag://{temp_id}")
        drag.setMimeData(mime_data)
        drag.exec()

    def get_markdown(self) -> str:
        return self._markdown_source

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

    def _sync_preview(self, capture_after: bool = False):
        if not self.web_view:
            return

        # Convert markdown to HTML
        html_content = self._compile_markdown()

        safe_html = json.dumps(html_content)
        capture_flag = str(capture_after).lower()

        js_code = f"if (typeof window.updateContent === 'function') {{ window.updateContent({safe_html}, {capture_flag}); }}"
        self.web_view.page().runJavaScript(js_code)

    def eventFilter(self, obj, event):
        if not self.text_edit:
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

    def _exit_edit_state(self, force_sync: bool = False):
        if not self._is_editing:
            return

        self._is_editing = False
        if QuestionBlockWidget._current_editing_block == self:
            QuestionBlockWidget._current_editing_block = None

        if force_sync and self.web_view:
            # Another block is claiming the shared view immediately.
            # QWebEngineView.grab() is asynchronously unreliable, so we completely fallback
            # to compiling simple markdown text to guarantee we have content immediately.
            if self.debounce_timer.isActive():
                self.debounce_timer.stop()
            html_content = self._compile_markdown()
            self.preview_label.setText(html_content)
            self._cleanup_edit_widgets()

            # Since we cleaned up, we should ensure the preview shows
            self.preview_label.show()
        else:
            # Show fallback HTML immediately to avoid stale text flicker during async grab
            html_content = self._compile_markdown()
            self.preview_label.setText(html_content)

            # Force any pending updates to compile
            if self.debounce_timer.isActive():
                self.debounce_timer.stop()
                self._sync_preview(capture_after=True)
            elif self.web_view:
                # We already synced, just request a snapshot
                js = "if (window.pyBridge) window.pyBridge.snapshotReady(document.body.scrollHeight);"
                self.web_view.page().runJavaScript(js)

            # Do NOT hide self.web_view here, as we need it visible for the async .grab().
            # It will be hidden inside _perform_grab via _cleanup_edit_widgets()

        # Note: If we don't hide the text_edit here, the minimumSizeHint() below will include it,
        # causing the card to animate to a large height instead of the preview height.
        if self.text_edit:
            self.text_edit.hide()

        # To ensure the collapse animation targets the correct final preview height,
        # the web_view is temporarily removed from the layout manager before the
        # animation starts. This prevents its own minimum size from interfering
        # with the layout's size hint calculation. The web_view remains a visible
        # child of the widget, allowing the asynchronous grab() to function
        # correctly. It is fully cleaned up later in _perform_grab().
        if self.web_view and not force_sync:
            self.content_layout.removeWidget(self.web_view)

        self.preview_label.show()

        # Force layout to recalculate size hint before animating
        self.layout().activate()
        self.updateGeometry()

        self.animation.setStartValue(self.height())
        self.animation.setEndValue(self.minimumSizeHint().height())
        self.animation.start()
