import logging
from PySide6.QtCore import Qt, QTimer, QAbstractListModel, QModelIndex, Signal, QThread
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import (
    Pivot,
    SearchLineEdit,
    FlowLayout,
    PillPushButton,
    SmoothScrollArea,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
)

logger = logging.getLogger(__name__)


class SearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, db_adapter, query, parent=None):
        super().__init__(parent)
        self.db_adapter = db_adapter
        self.query = query

    def run(self):
        try:
            safe_query = self.query.replace("'", "''")
            res = (
                self.db_adapter.q_table.search()
                .where(f"content_md LIKE '%{safe_query}%'")
                .limit(50)
                .to_list()
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class VirtualQuestionListModel(QAbstractListModel):
    """Custom high-performance virtual scrolling list model for massive datasets."""

    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self._data = data or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row_data = self._data[index.row()]

        if role == Qt.DisplayRole:
            # We return a truncated string representation or formatting here if using a standard view
            # For a highly customized item view, we would use a delegate. For now, basic string.
            content = row_data.get("content_md", "No Content")
            tags = row_data.get("tags", [])
            tag_str = ", ".join(tags) if tags else "无标签"
            return f"[{tag_str}] {content[:100]}..."

        if role == Qt.UserRole:
            return row_data

        return None

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()


class KnowledgeBaseWorkspace(QFrame):
    """
    题库管理模块基座 (Knowledge Base Workspace)
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("KnowledgeBaseWorkspace")

        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(16)

        # 1. 全局导航枢纽 (Pivot)
        self.pivot = Pivot(self)
        self.main_layout.addWidget(self.pivot, 0, Qt.AlignHCenter)

        self.views_container = QWidget(self)
        self.views_layout = QVBoxLayout(self.views_container)
        self.views_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.views_container, 1)

        # 2. 智能混合检索视图 (Smart Hybrid Search)
        self.search_view = QWidget(self)
        self.setup_search_view()
        self.views_layout.addWidget(self.search_view)

        # Pivot items configuration
        self.pivot.addItem(
            routeKey="search_view",
            text="智能混合检索",
            onClick=lambda: self.switch_view("search_view"),
        )
        self.pivot.addItem(
            routeKey="explore_view",
            text="多模态探索",
            onClick=lambda: self.switch_view("explore_view"),
        )
        self.pivot.addItem(
            routeKey="graph_view",
            text="3D 星空图谱",
            onClick=lambda: self.switch_view("graph_view"),
        )

        self.pivot.setCurrentItem("search_view")

    def setup_search_view(self):
        layout = QVBoxLayout(self.search_view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Super Search Bar
        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText(
            "输入知识点、考点或题目描述 (支持自然语言混合检索)..."
        )
        self.search_bar.setClearButtonEnabled(True)
        layout.addWidget(self.search_bar)

        # Debounce Timer for Search (500ms)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(500)

        # Dynamic Token Container
        self.token_container = QWidget(self)
        self.token_layout = FlowLayout(self.token_container)
        self.token_layout.setContentsMargins(0, 0, 0, 0)
        self.token_layout.setHorizontalSpacing(8)
        self.token_layout.setVerticalSpacing(8)
        layout.addWidget(self.token_container)

        # Virtual Scrolling List
        # Note: In a fully fleshed out QListView we would use a custom ItemDelegate to draw ElevatedCardWidget
        # For this prototype we will use qfluentwidgets.ListWidget and simple strings via the model to prove the pipeline

        # We set up the model
        self.list_model = VirtualQuestionListModel([], self)

        # In a real implementation we would attach it to a QListView. ListWidget is a convenience wrapper.
        # It's better to use a bare QListView with our custom model, but ListWidget might not support setModel
        # properly without breaking some Fluent integrations. We'll use a QListView directly styled like Fluent
        from PySide6.QtWidgets import QListView

        self.list_view = QListView(self)
        self.list_view.setModel(self.list_model)
        self.list_view.setStyleSheet("""
            QListView {
                background: transparent;
                border: none;
                outline: none;
            }
            QListView::item {
                background: rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 8px;
                color: #e0e0e0;
            }
            QListView::item:selected {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid #0078D4;
            }
            QListView::item:hover {
                background: rgba(255, 255, 255, 0.08);
            }
        """)

        # For robust visual styling we wrap it in a smooth scroll area
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidget(self.list_view)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        layout.addWidget(self.scroll_area, 1)

    def setup_connections(self):
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.search_timer.timeout.connect(self._perform_search)

    def switch_view(self, view_key):
        # Placeholder for view switching
        if view_key == "search_view":
            self.search_view.show()
        else:
            InfoBar.info(
                title="即将上线",
                content=f"{view_key} 仍在施工中...",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP,
                parent=self.window(),
            )

    def _on_search_text_changed(self, text):
        # Restart the debounce timer
        self.search_timer.start()

    def _perform_search(self):
        query = self.search_bar.text().strip()
        logger.info(f"Debounced search triggered for: '{query}'")

        # Clear existing tokens for demo purposes
        self._clear_tokens()

        if not query:
            self.list_model.update_data([])
            return

        # Mock NL2F token extraction
        self._add_token(f"模糊匹配: {query}")

        # Execute LanceDB query in a background thread to prevent UI freezing
        if not hasattr(self, "_db_adapter"):
            from db_adapter import LanceDBAdapter

            self._db_adapter = LanceDBAdapter()

        self.search_worker = SearchWorker(self._db_adapter, query, self)

        def handle_results(res):
            self.list_model.update_data(res)

        def handle_error(e):
            logger.error(f"Search failed: {e}")
            self.list_model.update_data([])

        self.search_worker.finished.connect(handle_results)
        self.search_worker.finished.connect(self.search_worker.deleteLater)
        self.search_worker.error.connect(handle_error)
        self.search_worker.error.connect(self.search_worker.deleteLater)
        self.search_worker.start()

    def _clear_tokens(self):
        while self.token_layout.count():
            item = self.token_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_token(self, text):
        token = PillPushButton(text, self)
        token.setIcon(FIF.CANCEL)
        token.clicked.connect(token.deleteLater)
        self.token_layout.addWidget(token)
