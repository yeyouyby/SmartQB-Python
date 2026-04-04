from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QSplitter,
    QLabel,
    QWidget,
)
from qfluentwidgets import (
    SmoothScrollArea,
)


class CalibrationWorkspace(QFrame):
    """
    核心校对层：三栏联动工作台 (Calibration Workspace)
    分为左 (3.5)、中 (5)、右 (1.5) 三个区域
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("CalibrationWorkspace")
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 核心分栏
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.splitter)

        # ==========================================
        # 1. 左栏：原卷保真参照视图 (Left Panel)
        # ==========================================
        self.left_panel = SmoothScrollArea()
        self.left_panel.setWidgetResizable(True)
        self.left_panel_content = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel_content)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)

        # Placeholder for lazy loading PDF pages
        self.left_placeholder = QLabel("原卷保真视图 (PDF 懒加载区)")
        self.left_placeholder.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(self.left_placeholder)
        self.left_layout.addStretch(1)

        self.left_panel.setWidget(self.left_panel_content)
        self.splitter.addWidget(self.left_panel)

        # ==========================================
        # 2. 中栏：流式双态编辑器 (Mid Panel - 系统的核心与难点)
        # ==========================================
        self.mid_panel = SmoothScrollArea()
        self.mid_panel.setWidgetResizable(True)
        self.mid_panel_content = QWidget()
        self.mid_layout = QVBoxLayout(self.mid_panel_content)
        self.mid_layout.setContentsMargins(10, 10, 10, 10)
        self.mid_layout.setSpacing(15)

        # Placeholder for the dual-state ElevatedCardWidget
        self.mid_placeholder = QLabel("流式双态编辑器 (Markdown / MathJax)")
        self.mid_placeholder.setAlignment(Qt.AlignCenter)
        self.mid_layout.addWidget(self.mid_placeholder)
        self.mid_layout.addStretch(1)

        self.mid_panel.setWidget(self.mid_panel_content)
        self.splitter.addWidget(self.mid_panel)

        # ==========================================
        # 3. 右栏：元数据属性侧边栏 (Right Panel)
        # ==========================================
        self.right_panel = QFrame()
        self.right_layout = QVBoxLayout(self.right_panel)

        self.right_placeholder = QLabel("元数据属性侧边栏\n(AI 逻辑链与标签树)")
        self.right_placeholder.setAlignment(Qt.AlignCenter)
        self.right_layout.addWidget(self.right_placeholder)
        self.right_layout.addStretch(1)

        self.splitter.addWidget(self.right_panel)

        # 严格按照比例划分左、中、右 (3.5 : 5 : 1.5) => (7, 10, 3)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 10)
        self.splitter.setStretchFactor(2, 3)
