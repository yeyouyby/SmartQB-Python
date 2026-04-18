from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from qfluentwidgets import (
    SmoothScrollArea,
    SettingCardGroup,
    OptionsSettingCard,
    SwitchSettingCard,
    ComboBoxSettingCard,
    LineEditSettingCard,
    LargeTitleLabel,
    FluentIcon as FIF,
)


class SettingsCenter(QFrame):
    """
    全局设置中心 (Settings Center)
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SettingsCenter")
        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(32, 32, 32, 32)
        self.scroll_layout.setSpacing(24)

        self.title_label = LargeTitleLabel("系统设置", self.scroll_content)
        self.scroll_layout.addWidget(self.title_label)

        # 1. 视觉与主题组
        self.theme_group = SettingCardGroup("视觉体验", self.scroll_content)
        self.scroll_layout.addWidget(self.theme_group)

        # We simulate options list for demonstration
        from qfluentwidgets import (
            OptionsConfigItem,
            OptionsValidator,
        )

        self.theme_mode_card = OptionsSettingCard(
            configItem=OptionsConfigItem(
                "Theme", "Mode", "Light", OptionsValidator(["Light", "Dark", "Auto"])
            ),
            icon=FIF.BRUSH,
            title="应用主题",
            content="调整应用程序的外观与色彩模式",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.theme_group,
        )
        self.theme_group.addSettingCard(self.theme_mode_card)

        self.mica_card = SwitchSettingCard(
            icon=FIF.TRANSPARENT,
            title="云母效果材质",
            content="开启 Mica 材质获取模糊透视效果 (Windows 11)",
            parent=self.theme_group,
        )
        # Note: In a real app we pass a configItem boolean to SwitchSettingCard, but for static mock we just initialize it
        self.theme_group.addSettingCard(self.mica_card)

        # 2. 解析引擎与模型配置组
        self.engine_group = SettingCardGroup("MinerU & AI 引擎", self.scroll_content)
        self.scroll_layout.addWidget(self.engine_group)

        self.engine_card = ComboBoxSettingCard(
            configItem=OptionsConfigItem(
                "Engine", "Type", "Cloud", OptionsValidator(["Cloud", "Local"])
            ),
            icon=FIF.CLOUD,
            title="MinerU 提取引擎",
            content="选择试卷 OCR 提取引擎（本地需安装 40GB 模型）",
            texts=["NVIDIA NIM 云端推理", "本地 MinerU 本地部署"],
            parent=self.engine_group,
        )
        self.engine_group.addSettingCard(self.engine_card)

        self.api_key_card = LineEditSettingCard(
            icon=FIF.LOCK,
            title="API Key 配置",
            content="用于混合检索的向量化与 NL2F",
            parent=self.engine_group,
        )
        self.api_key_card.lineEdit.setPlaceholderText("sk-...")
        self.api_key_card.lineEdit.setEchoMode(
            self.api_key_card.lineEdit.EchoMode.Password
        )
        self.engine_group.addSettingCard(self.api_key_card)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)
