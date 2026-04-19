from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QHeaderView, QTableWidgetItem
from qfluentwidgets import (
    SmoothScrollArea,
    ElevatedCardWidget,
    LargeTitleLabel,
    SubtitleLabel,
    BodyLabel,
    PrimaryPushButton,
    TableWidget,
    FlowLayout,
    IconWidget,
    FluentIcon as FIF,
)


class HomeDashboard(QFrame):
    """
    主页看板 (Home Dashboard)
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("HomeDashboard")
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Base Container: Mica-style SmoothScrollArea
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(32, 32, 32, 32)
        self.scroll_layout.setSpacing(24)

        # 1. Hero Area (Welcome + Indicators)
        self.hero_card = ElevatedCardWidget(self.scroll_content)
        self.hero_layout = QHBoxLayout(self.hero_card)
        self.hero_layout.setContentsMargins(24, 24, 24, 24)

        self.greeting_label = LargeTitleLabel("早安，李老师。", self.hero_card)
        self.hero_layout.addWidget(self.greeting_label)
        self.hero_layout.addStretch()

        # State Indicators Mock
        self.indicator_layout = QVBoxLayout()
        self.indicator_layout.setAlignment(Qt.AlignRight)

        db_state = QHBoxLayout()
        db_state.addWidget(IconWidget(FIF.DATABASE, self.hero_card))
        db_state.addWidget(BodyLabel("LanceDB: 在线 (1ms)", self.hero_card))
        self.indicator_layout.addLayout(db_state)

        api_state = QHBoxLayout()
        api_state.addWidget(IconWidget(FIF.CLOUD, self.hero_card))
        api_state.addWidget(BodyLabel("API 延迟: 124ms", self.hero_card))
        self.indicator_layout.addLayout(api_state)

        self.hero_layout.addLayout(self.indicator_layout)
        self.scroll_layout.addWidget(self.hero_card)

        # 2. Data Dashboard (FlowLayout for Stats Cards)
        self.stats_container = QWidget(self.scroll_content)
        self.stats_layout = FlowLayout(self.stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setHorizontalSpacing(16)
        self.stats_layout.setVerticalSpacing(16)

        stats = [
            ("总收录题目", "1,245", FIF.DOCUMENT),
            ("活跃标签", "128", FIF.TAG),
            ("已生成试卷", "34", FIF.PRINT),
            ("智能纠错数", "5,412", FIF.COMPLETED),
        ]

        for title, value, icon in stats:
            card = ElevatedCardWidget(self.stats_container)
            card.setFixedSize(220, 140)
            card_vbox = QVBoxLayout(card)

            header = QHBoxLayout()
            header.addWidget(SubtitleLabel(title))
            header.addStretch()
            header.addWidget(IconWidget(icon, card))
            card_vbox.addLayout(header)

            val_label = LargeTitleLabel(value)
            val_label.setStyleSheet("color: #0078D4;")
            val_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
            card_vbox.addWidget(val_label, 1)

            self.stats_layout.addWidget(card)

        self.scroll_layout.addWidget(self.stats_container)

        # 3. Quick Actions
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(16)

        btn_import = PrimaryPushButton(FIF.ADD, "快速导入", self.scroll_content)
        btn_import.setMinimumHeight(50)
        btn_assemble = PrimaryPushButton(FIF.DOCUMENT, "智能组卷", self.scroll_content)
        btn_assemble.setMinimumHeight(50)
        btn_tags = PrimaryPushButton(FIF.TAG, "标签治理", self.scroll_content)
        btn_tags.setMinimumHeight(50)

        self.action_layout.addWidget(btn_import)
        self.action_layout.addWidget(btn_assemble)
        self.action_layout.addWidget(btn_tags)
        self.action_layout.addStretch()

        self.scroll_layout.addLayout(self.action_layout)

        # 4. Recent Activity Log
        self.log_title = SubtitleLabel("系统动态流水", self.scroll_content)
        self.scroll_layout.addWidget(self.log_title)

        self.log_table = TableWidget(self.scroll_content)
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["时间", "操作类型", "详细信息"])
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.log_table.setRowCount(4)


        logs = [
            ("10:45 AM", "试题入库", "成功解析并导入 25 道试题 (海淀期末模拟.pdf)"),
            ("09:21 AM", "自动打标", "AI 成功为 14 题提取考点标签"),
            ("昨天 16:30", "导出试卷", "生成资产：2024冲刺训练卷.pdf"),
            ("昨天 14:15", "系统更新", "LanceDB 索引重建完成 (0.8s)"),
        ]

        for i, (time_str, type_str, info) in enumerate(logs):
            self.log_table.setItem(i, 0, QTableWidgetItem(time_str))
            self.log_table.setItem(i, 1, QTableWidgetItem(type_str))
            self.log_table.setItem(i, 2, QTableWidgetItem(info))

        self.log_table.setMinimumHeight(200)
        self.scroll_layout.addWidget(self.log_table)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)
