from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QSplitter, QWidget
from qfluentwidgets import (
    ComboBox,
    TreeWidget,
    SmoothScrollArea,
    ElevatedCardWidget,
    ListWidget,
    SubtitleLabel,
    InfoBadge,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


class ProductionWorkspace(QFrame):
    """
    组卷导出模块 (Production Workspace)
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ProductionWorkspace")
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.splitter)

        # Left Column: Outline Tree
        self.left_panel = QWidget(self)
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(16, 16, 16, 16)

        self.template_combo = ComboBox(self.left_panel)
        self.template_combo.addItems(
            ["2024年高考数学新高考I卷", "高三期中测验摸底卷", "清北学堂培优竞赛卷"]
        )
        self.left_layout.addWidget(self.template_combo)

        self.outline_tree = TreeWidget(self.left_panel)
        self.outline_tree.setHeaderLabel("试卷大纲结构")
        from PySide6.QtWidgets import QTreeWidgetItem

        root = QTreeWidgetItem(self.outline_tree, ["高中数学测试卷"])
        sec1 = QTreeWidgetItem(root, ["一、单项选择题 (共8题，40分)"])
        QTreeWidgetItem(sec1, ["1. 集合运算"])
        QTreeWidgetItem(sec1, ["2. 复数运算"])
        QTreeWidgetItem(sec1, ["3. 空间几何"])
        sec2 = QTreeWidgetItem(root, ["二、多项选择题 (共3题，18分)"])
        QTreeWidgetItem(sec2, ["9. 解析几何"])
        sec3 = QTreeWidgetItem(root, ["三、解答题 (共5题，77分)"])
        QTreeWidgetItem(sec3, ["15. 三角函数"])
        self.outline_tree.expandAll()
        self.left_layout.addWidget(self.outline_tree, 1)

        # Middle Column: A4 Preview
        self.middle_panel = QWidget(self)
        self.middle_panel.setStyleSheet("QWidget { background-color: #F3F3F3; }")
        self.middle_layout = QVBoxLayout(self.middle_panel)
        self.middle_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = SmoothScrollArea(self.middle_panel)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll_layout.setContentsMargins(20, 40, 20, 40)

        # A4 Paper Mock
        self.a4_paper = ElevatedCardWidget(self.scroll_content)
        self.a4_paper.setFixedSize(800, 1131)  # A4 ratio
        self.a4_paper.setStyleSheet(
            "ElevatedCardWidget { background-color: white; border-radius: 4px; }"
        )

        self.a4_layout = QVBoxLayout(self.a4_paper)
        self.a4_layout.setContentsMargins(40, 40, 40, 40)

        self.preview_view = QWebEngineView(self.a4_paper)
        self.preview_view.setHtml(
            "<html><body style='font-family: \"Microsoft YaHei\", sans-serif; text-align: center;'><h1>2024 年普通高等学校招生全国统一考试</h1><h2>理科数学</h2><p style='text-align: left;'><b>注意事项：</b></p><ol style='text-align: left;'><li>答卷前，考生务必将自己的姓名、准考证号填写在答题卡上。</li><li>回答选择题时，选出每小题答案后，用铅笔把答题卡上对应题目的答案标号涂黑。</li></ol></body></html>"
        )

        self.a4_layout.addWidget(self.preview_view)

        self.scroll_layout.addWidget(self.a4_paper)
        self.scroll_area.setWidget(self.scroll_content)

        self.middle_layout.addWidget(self.scroll_area)

        # Right Column: Question Basket Drawer
        self.right_panel = QWidget(self)
        # Acrylic simulation with semitransparent background
        self.right_panel.setStyleSheet(
            "QWidget { background-color: rgba(255, 255, 255, 0.7); }"
        )
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(16, 16, 16, 16)

        header_layout = QVBoxLayout()
        title_label = SubtitleLabel("试题篮 (Basket)")
        header_layout.addWidget(title_label)

        # We can't easily position an InfoBadge next to a label without absolute coords or a dedicated container,
        # so we just add a badge to the layout directly
        badge = InfoBadge.info("12")
        header_layout.addWidget(badge)
        self.right_layout.addLayout(header_layout)

        self.basket_list = ListWidget(self.right_panel)
        self.basket_list.addItems(
            [
                "第 1 题: [集合] 设集合 A = {x | -1 < x < 2}...",
                "第 2 题: [复数] 若 z = 1 + i, 则 |z| = ...",
                "第 3 题: [导数] 已知函数 f(x) = e^x - x...",
                "第 4 题: [圆锥曲线] 已知椭圆 C: x^2/a^2 + y^2/b^2 = 1...",
            ]
        )
        self.right_layout.addWidget(self.basket_list)

        # Add to splitter
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.middle_panel)
        self.splitter.addWidget(self.right_panel)

        # Set stretch factors (approximate proportions: 2.5 : 6 : 1.5)
        self.splitter.setStretchFactor(0, 25)
        self.splitter.setStretchFactor(1, 60)
        self.splitter.setStretchFactor(2, 15)
