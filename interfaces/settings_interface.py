from PySide6.QtCore import Qt, QUrl, Signal, QThread, QObject, Slot, QMetaObject, Q_ARG
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QHeaderView, QSplitter, QTableWidgetItem, QListWidgetItem, QApplication, QStackedWidget

from qfluentwidgets import (ScrollArea, SettingCardGroup, PrimaryPushButton,
                            ComboBoxSettingCard, LineEditSettingCard, SwitchSettingCard, SpinBoxSettingCard,
                            MessageBox, InfoBar, InfoBarPosition, OptionsSettingCard, OptionConfigItem)
from qfluentwidgets import ConfigItem, qconfig, QConfig

class SettingsInterface(ScrollArea):
    def __init__(self, app_logic, parent=None):
        super().__init__(parent=parent)
        self.app_logic = app_logic
        self.settings = app_logic.settings
        self.scrollWidget = QWidget()
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(10)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setup_ui()

    def setup_ui(self):
        # Service Provider Config
        api_group = SettingCardGroup("AI 服务商与 API 配置", self.scrollWidget)

        self.cbo_provider = ComboBoxSettingCard(
            ConfigItem("API", "Provider", "自定义"),
            "快捷服务商配置",
            "选择预设的 AI 服务商快速填入 Base URL 和模型名称",
            texts=["自定义", "DeepSeek", "Kimi", "GLM (智谱)", "SiliconFlow (硅基)"],
            parent=api_group
        )
        self.cbo_provider.comboBox.currentIndexChanged.connect(self.on_provider_changed)
        api_group.addSettingCard(self.cbo_provider)

        self.ent_api = LineEditSettingCard(ConfigItem("API", "Key", self.settings.api_key), "API Key", "将通过系统凭证管理器自动加密")
        self.ent_base = LineEditSettingCard(ConfigItem("API", "BaseURL", self.settings.base_url), "Base URL")
        self.ent_model = LineEditSettingCard(ConfigItem("API", "Model", self.settings.model_id), "Model ID")
        api_group.addSettingCard(self.ent_api)
        api_group.addSettingCard(self.ent_base)
        api_group.addSettingCard(self.ent_model)

        self.vBoxLayout.addWidget(api_group)

        # Advanced Model Params
        adv_group = SettingCardGroup("高级模型参数", self.scrollWidget)
        self.ent_temp = LineEditSettingCard(ConfigItem("Adv", "Temp", str(self.settings.temperature)), "Temperature (0-2)")
        self.ent_top_p = LineEditSettingCard(ConfigItem("Adv", "TopP", str(self.settings.top_p)), "Top P (0-1)")
        self.ent_max_tokens = LineEditSettingCard(ConfigItem("Adv", "MaxTokens", str(self.settings.max_tokens)), "Max Tokens")

        self.cbo_reasoning = ComboBoxSettingCard(
            ConfigItem("Adv", "Reasoning", self.settings.reasoning_effort),
            "思考强度 (Reasoning Effort)",
            texts=["low", "medium", "high", "none"],
            parent=adv_group
        )
        adv_group.addSettingCard(self.ent_temp)
        adv_group.addSettingCard(self.ent_top_p)
        adv_group.addSettingCard(self.ent_max_tokens)
        adv_group.addSettingCard(self.cbo_reasoning)
        self.vBoxLayout.addWidget(adv_group)

        # Embedding Config
        embed_group = SettingCardGroup("Embedding 向量配置", self.scrollWidget)
        self.ent_embed_api = LineEditSettingCard(ConfigItem("Embed", "Key", self.settings.embed_api_key), "Embedding API Key")
        self.ent_embed_base = LineEditSettingCard(ConfigItem("Embed", "BaseURL", self.settings.embed_base_url), "Embedding Base URL")
        self.ent_embed_model = LineEditSettingCard(ConfigItem("Embed", "Model", self.settings.embed_model_id), "Embedding Model ID")
        self.ent_embed_dim = LineEditSettingCard(ConfigItem("Embed", "Dim", str(self.settings.embedding_dimension)), "向量维度 (与模型输出一致，否则报错)")

        embed_group.addSettingCard(self.ent_embed_api)
        embed_group.addSettingCard(self.ent_embed_base)
        embed_group.addSettingCard(self.ent_embed_model)
        embed_group.addSettingCard(self.ent_embed_dim)
        self.vBoxLayout.addWidget(embed_group)

        # Engine Options
        engine_group = SettingCardGroup("核心引擎配置", self.scrollWidget)
        self.cbo_layout = ComboBoxSettingCard(
            ConfigItem("Engine", "Layout", self.settings.layout_engine_type),
            "版面分析引擎", texts=["DocLayout-YOLO"], parent=engine_group
        )
        self.cbo_ocr = ComboBoxSettingCard(
            ConfigItem("Engine", "OCR", self.settings.ocr_engine_type),
            "OCR 识别引擎", texts=["Pix2Text"], parent=engine_group
        )

        mode_item = OptionConfigItem("Engine", "Mode", self.settings.recognition_mode - 1, OptionsValidator([0,1,2]), RestartSerializer())
        self.cbo_mode = OptionsSettingCard(
            mode_item, "核心识别模式",
            "1.纯OCR / 2.本地OCR+纯文本AI纠错 / 3.多模态视觉纠错",
            texts=[
                "1. 仅本地 OCR (最快且免费，但不做任何AI纠错)",
                "2. 本地 OCR + 纯文字 AI 纠错 (省流推荐)",
                "3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐)"
            ],
            parent=engine_group
        )

        self.switch_prm = SwitchSettingCard(
            None,
            ConfigItem("Engine", "PRM", self.settings.use_prm_optimization),
            "启用多切片并发 (PRM 优化)", "大于1即启用", parent=engine_group
        )

        self.spin_prm_batch = SpinBoxSettingCard(
            ConfigItem("Engine", "Batch", self.settings.prm_batch_size),
            None, "单次并发主切片数", parent=engine_group
        )
        self.spin_prm_batch.spinBox.setRange(2, 15)

        engine_group.addSettingCard(self.cbo_layout)
        engine_group.addSettingCard(self.cbo_ocr)
        engine_group.addSettingCard(self.cbo_mode)
        engine_group.addSettingCard(self.switch_prm)
        engine_group.addSettingCard(self.spin_prm_batch)
        self.vBoxLayout.addWidget(engine_group)

        btn_save = PrimaryPushButton("💾 保存所有设置")
        btn_save.clicked.connect(self.save_settings)
        self.vBoxLayout.addWidget(btn_save)

    def on_provider_changed(self, idx):
        provider = self.cbo_provider.comboBox.currentText()
        provider_presets = {
            "DeepSeek": {"base": "https://api.deepseek.com", "model": "deepseek-chat", "embed_base": "", "embed_model": ""},
            "Kimi": {"base": "https://api.moonshot.cn/v1", "model": "kimi-k2.5", "embed_base": "", "embed_model": ""},
            "GLM (智谱)": {
                "base": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-plus-0326",
                "embed_base": "https://open.bigmodel.cn/api/paas/v4/",
                "embed_model": "embedding-3",
            },
            "SiliconFlow (硅基)": {
                "base": "https://api.siliconflow.cn/v1",
                "model": "deepseek-ai/DeepSeek-V3.2",
                "embed_base": "https://api.siliconflow.cn/v1",
                "embed_model": "BAAI/bge-m3",
            },
        }

        config = provider_presets.get(provider)
        if config:
            self.ent_base.lineEdit.setText(config["base"])
            self.ent_model.lineEdit.setText(config["model"])
            self.ent_embed_base.lineEdit.setText(config["embed_base"])
            self.ent_embed_model.lineEdit.setText(config["embed_model"])

    def save_settings(self):
        self.settings.api_key = self.ent_api.lineEdit.text().strip()
        self.settings.base_url = self.ent_base.lineEdit.text().strip()
        self.settings.model_id = self.ent_model.lineEdit.text().strip()

        try:
            self.settings.temperature = float(self.ent_temp.lineEdit.text())
        except ValueError:
            self.settings.temperature = 1.0
        try:
            self.settings.top_p = float(self.ent_top_p.lineEdit.text())
        except ValueError:
            self.settings.top_p = 1.0
        try:
            self.settings.max_tokens = int(self.ent_max_tokens.lineEdit.text())
        except ValueError:
            self.settings.max_tokens = 4096

        self.settings.reasoning_effort = self.cbo_reasoning.comboBox.currentText()

        self.settings.embed_api_key = self.ent_embed_api.lineEdit.text().strip()
        self.settings.embed_base_url = self.ent_embed_base.lineEdit.text().strip()
        self.settings.embed_model_id = self.ent_embed_model.lineEdit.text().strip()

        # mode_index + 1 because the backend uses 1, 2, 3
        # In OptionsSettingCard, index starts at 0
        try:
            # Fallback if config is used differently
            self.settings.recognition_mode = self.cbo_mode.buttonGroup.checkedId() + 1
        except:
            pass # Use standard config fallback if needed

        self.settings.layout_engine_type = self.cbo_layout.comboBox.currentText()
        self.settings.ocr_engine_type = self.cbo_ocr.comboBox.currentText()

        self.settings.use_prm_optimization = self.switch_prm.switchButton.isChecked()
        self.settings.prm_batch_size = self.spin_prm_batch.spinBox.value()

        try:
            val = int(self.ent_embed_dim.lineEdit.text().strip())
            if val <= 0: raise ValueError
            self.settings.embedding_dimension = val
        except ValueError:
            self.settings.embedding_dimension = 1024
            self.ent_embed_dim.lineEdit.setText('1024')

        try:
            self.settings.save()
            self.app_logic.ai_service.settings = self.settings
            InfoBar.success("成功", "设置保存成功！", duration=3000, position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            MessageBox("错误", f"保存设置时发生异常:\n{e}", self.window()).exec()

# Mock definitions for missing qfluentwidgets validator objects if they error out
# Just for layout safety
try:
    from qfluentwidgets import OptionsValidator, RestartSerializer
except ImportError:
    class OptionsValidator:
        def __init__(self, x): pass
        def validate(self, x): return True
        def correct(self, x): return x
    class RestartSerializer:
        def serialize(self, x): return x
        def deserialize(self, x): return x

# Patch OptionsValidator/RestartSerializer at module level if needed
import sys
import qfluentwidgets
if not hasattr(qfluentwidgets, 'OptionsValidator'):
    setattr(qfluentwidgets, 'OptionsValidator', OptionsValidator)
if not hasattr(qfluentwidgets, 'RestartSerializer'):
    setattr(qfluentwidgets, 'RestartSerializer', RestartSerializer)
