import logging
from db_adapter import LanceDBAdapter
from PySide6.QtCore import Qt, QTimer, QAbstractListModel, QModelIndex, Signal, QThread
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
)
from qfluentwidgets import (
    Pivot,
    SearchLineEdit,
    FlowLayout,
    PillPushButton,
    SmoothScrollArea,
    ElevatedCardWidget,
    FluentIcon as FIF,
    PopUpAniStackedWidget,
    InfoBadge,
    PrimaryPushButton,
    CardWidget,
    TreeWidget,
    TableWidget,
    ProgressBar,
    SwitchButton,
    SubtitleLabel,
    BodyLabel,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


logger = logging.getLogger(__name__)


class SearchWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, db_adapter, query, parent=None):
        super().__init__(parent)
        self.db_adapter = db_adapter
        self.query = query

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            try:
                # Try FTS search first natively
                res = self.db_adapter.q_table.search(self.query).limit(50).to_list()
            except Exception:
                if self.isInterruptionRequested():
                    return
                # Fallback to LIKE if FTS index missing
                safe_query = (
                    self.query.replace("\\", "\\\\")
                    .replace("'", "''")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                res = (
                    self.db_adapter.q_table.search()
                    .where(
                        f"content_md LIKE '%{safe_query}%' ESCAPE '\\' OR array_to_string(tags, ',') LIKE '%{safe_query}%' ESCAPE '\\'"
                    )
                    .limit(50)
                    .to_list()
                )

            if self.isInterruptionRequested():
                return

            self.finished.emit(res)
        except Exception as e:
            if not self.isInterruptionRequested():
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

        self.views_container = PopUpAniStackedWidget(self)
        self.main_layout.addWidget(self.views_container, 1)

        # 2. 智能混合检索视图 (Smart Hybrid Search)
        self.search_view = QWidget(self)
        self.setup_search_view()
        self.views_container.addWidget(self.search_view)

        # 3. 多模态搜索视图 (Multimodal Search)
        self.explore_view = QWidget(self)
        self.setup_explore_view()
        self.views_container.addWidget(self.explore_view)

        # 4. 3D 星空图谱视图 (Knowledge Graph)
        self.graph_view = QWidget(self)
        self.setup_graph_view()
        self.views_container.addWidget(self.graph_view)

        # 5. 标签治理视图 (Tag Governance)
        self.tag_view = QWidget(self)
        self.setup_tag_view()
        self.views_container.addWidget(self.tag_view)

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
        self.pivot.addItem(
            routeKey="tag_view",
            text="标签治理",
            onClick=lambda: self.switch_view("tag_view"),
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

    def setup_explore_view(self):
        layout = QHBoxLayout(self.explore_view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Left side: Giant drag-and-drop / crop workspace
        self.upload_card = ElevatedCardWidget(self.explore_view)
        upload_layout = QVBoxLayout(self.upload_card)
        upload_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        # Using a text icon as placeholder
        icon_label.setText("📥")
        icon_label.setStyleSheet("font-size: 64px;")
        upload_layout.addWidget(icon_label)

        title_label = SubtitleLabel("拖拽图片或 PDF 至此", self.upload_card)
        title_label.setAlignment(Qt.AlignCenter)
        upload_layout.addWidget(title_label)

        desc_label = BodyLabel("支持多模态搜题与区域裁剪", self.upload_card)
        desc_label.setAlignment(Qt.AlignCenter)
        upload_layout.addWidget(desc_label)

        layout.addWidget(self.upload_card, 1)

        # Right side: Recommendation waterfall
        self.recommendation_scroll = SmoothScrollArea(self.explore_view)
        self.recommendation_scroll.setWidgetResizable(True)
        self.recommendation_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        container = QWidget()
        flow_layout = FlowLayout(container)

        # Mock recommendation cards
        for i in range(4):
            card = ElevatedCardWidget(container)
            card.setFixedSize(250, 180)
            card_layout = QVBoxLayout(card)

            # Badge
            badge_layout = QHBoxLayout()
            badge_layout.addStretch()
            badge = InfoBadge.info("98% 匹配")
            badge_layout.addWidget(badge)
            card_layout.addLayout(badge_layout)

            # Content
            content_label = BodyLabel(
                f"推荐试题 {i + 1}\n考点：导数与函数极值\n难度：0.8"
            )
            content_label.setWordWrap(True)
            card_layout.addWidget(content_label, 1)

            # Action
            action_layout = QHBoxLayout()
            action_layout.addStretch()
            btn = PrimaryPushButton("加入试题袋", card)
            action_layout.addWidget(btn)
            card_layout.addLayout(action_layout)

            flow_layout.addWidget(card)

        self.recommendation_scroll.setWidget(container)
        layout.addWidget(self.recommendation_scroll, 1)

    def setup_graph_view(self):
        layout = QVBoxLayout(self.graph_view)
        layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder for ECharts (QWebEngineView)
        self.graph_web_view = QWebEngineView(self.graph_view)
        self.graph_web_view.setHtml(
            "<html><body style='background-color:#1c1c1c; color:white; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'><h2>ECharts 3D Starry Graph Placeholder</h2></body></html>"
        )

        # Floating transparent CardWidget for controls
        self.graph_control_panel = CardWidget(self.graph_view)
        self.graph_control_panel.setFixedSize(300, 150)
        self.graph_control_panel.setStyleSheet(
            "CardWidget { background-color: rgba(255, 255, 255, 0.8); border-radius: 8px; }"
        )

        # Absolute positioning
        self.graph_control_panel.move(20, 20)

        control_layout = QVBoxLayout(self.graph_control_panel)
        control_title = SubtitleLabel("图谱控制台")
        control_layout.addWidget(control_title)
        control_layout.addWidget(BodyLabel("过滤难度层级"))
        control_layout.addWidget(PrimaryPushButton("重新排列节点"))

        layout.addWidget(self.graph_web_view)

    def setup_tag_view(self):
        layout = QHBoxLayout(self.tag_view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Left side: Taxonomy Tree
        self.tag_tree = TreeWidget(self.tag_view)
        self.tag_tree.setHeaderLabel("知识树分类")
        from PySide6.QtWidgets import QTreeWidgetItem

        root = QTreeWidgetItem(self.tag_tree, ["高中数学"])
        child1 = QTreeWidgetItem(root, ["代数"])
        QTreeWidgetItem(child1, ["函数"])
        QTreeWidgetItem(child1, ["数列"])
        child2 = QTreeWidgetItem(root, ["几何"])
        QTreeWidgetItem(child2, ["立体几何"])
        self.tag_tree.expandAll()

        layout.addWidget(self.tag_tree, 1)

        # Right side: Tag Data Grid
        self.tag_table = TableWidget(self.tag_view)
        self.tag_table.setColumnCount(3)
        self.tag_table.setHorizontalHeaderLabels(
            ["标签名称", "关联试题数", "AI 白名单开关"]
        )
        self.tag_table.setRowCount(3)

        from PySide6.QtWidgets import QTableWidgetItem

        # Row 1
        self.tag_table.setItem(0, 0, QTableWidgetItem("函数单调性"))
        pb1 = ProgressBar()
        pb1.setValue(80)
        self.tag_table.setCellWidget(0, 1, pb1)
        self.tag_table.setCellWidget(0, 2, SwitchButton())

        # Row 2
        self.tag_table.setItem(1, 0, QTableWidgetItem("空间向量"))
        pb2 = ProgressBar()
        pb2.setValue(45)
        self.tag_table.setCellWidget(1, 1, pb2)
        self.tag_table.setCellWidget(1, 2, SwitchButton())

        # Row 3
        self.tag_table.setItem(2, 0, QTableWidgetItem("椭圆方程"))
        pb3 = ProgressBar()
        pb3.setValue(60)
        self.tag_table.setCellWidget(2, 1, pb3)
        self.tag_table.setCellWidget(2, 2, SwitchButton())

        self.tag_table.resizeColumnsToContents()
        layout.addWidget(self.tag_table, 2)

    def setup_connections(self):
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.search_timer.timeout.connect(self._perform_search)

    def switch_view(self, view_key):
        if view_key == "search_view":
            self.views_container.setCurrentWidget(self.search_view)
        elif view_key == "explore_view":
            self.views_container.setCurrentWidget(self.explore_view)
        elif view_key == "graph_view":
            self.views_container.setCurrentWidget(self.graph_view)
        elif view_key == "tag_view":
            self.views_container.setCurrentWidget(self.tag_view)

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
            self._db_adapter = LanceDBAdapter()

        if hasattr(self, "search_worker") and self.search_worker.isRunning():
            # Signal the thread to abort early
            self.search_worker.requestInterruption()
            try:
                self.search_worker.finished.disconnect()
                self.search_worker.error.disconnect()
                # Re-connect deleteLater to ensure the thread is still cleaned up
                self.search_worker.finished.connect(self.search_worker.deleteLater)
                self.search_worker.error.connect(self.search_worker.deleteLater)
            except (RuntimeError, TypeError) as e:
                logger.debug(
                    f"Failed to cleanly disconnect previous search worker: {e}"
                )

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
