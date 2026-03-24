from qfluentwidgets import FluentIcon
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QScrollArea, QButtonGroup, QRadioButton
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton,
    LineEdit, ComboBox, SwitchSettingCard, SpinBox, TitleLabel
)
from utils import logger
import tkinter.messagebox as messagebox # Keep old for simple warnings if needed or replace

class SettingsTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = parent.settings
        self.ai_service = parent.ai_service
        self.setObjectName('Settings'.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)
        self._build_ui()

    def _build_ui(self):
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        container = QFrame()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)

        v_layout.addWidget(TitleLabel("应用设置"))

        provider_frame = QFrame()
        h_layout_prov = QHBoxLayout(provider_frame)
        h_layout_prov.setContentsMargins(0, 10, 0, 10)
        h_layout_prov.addWidget(BodyLabel("快捷服务商配置:"))

        self.cbo_provider = ComboBox()
        self.cbo_provider.addItems(["自定义", "DeepSeek", "Kimi", "GLM (智谱)", "SiliconFlow (硅基)"])
        self.cbo_provider.setCurrentIndex(0)
        self.cbo_provider.currentIndexChanged.connect(self.on_provider_changed)
        h_layout_prov.addWidget(self.cbo_provider)
        h_layout_prov.addStretch(1)
        v_layout.addWidget(provider_frame)

        v_layout.addWidget(BodyLabel("API Key (将通过系统凭证管理器自动加密):"))
        self.ent_api = LineEdit()
        self.ent_api.setEchoMode(LineEdit.Password)
        self.ent_api.setText(self.settings.api_key)
        v_layout.addWidget(self.ent_api)

        v_layout.addWidget(BodyLabel("Base URL:"))
        self.ent_base = LineEdit()
        self.ent_base.setText(self.settings.base_url)
        v_layout.addWidget(self.ent_base)

        v_layout.addWidget(BodyLabel("Model ID:"))
        self.ent_model = LineEdit()
        self.ent_model.setText(self.settings.model_id)
        v_layout.addWidget(self.ent_model)

        v_layout.addWidget(SubtitleLabel("高级模型参数"))
        adv_frame = QFrame()
        adv_layout = QHBoxLayout(adv_frame)
        adv_layout.setContentsMargins(0,0,0,0)

        adv_layout.addWidget(BodyLabel("Temperature (0-2):"))
        self.ent_temp = LineEdit()
        self.ent_temp.setText(str(getattr(self.settings, 'temperature', 1.0)))
        adv_layout.addWidget(self.ent_temp)

        adv_layout.addWidget(BodyLabel("Top P (0-1):"))
        self.ent_top_p = LineEdit()
        self.ent_top_p.setText(str(getattr(self.settings, 'top_p', 1.0)))
        adv_layout.addWidget(self.ent_top_p)

        adv_layout.addWidget(BodyLabel("Max Tokens:"))
        self.ent_max_tokens = LineEdit()
        self.ent_max_tokens.setText(str(getattr(self.settings, 'max_tokens', 4096)))
        adv_layout.addWidget(self.ent_max_tokens)

        adv_layout.addWidget(BodyLabel("思考强度(Reasoning Effort):"))
        self.cbo_reasoning = ComboBox()
        self.cbo_reasoning.addItems(["low", "medium", "high", "none"])
        self.cbo_reasoning.setCurrentText(getattr(self.settings, 'reasoning_effort', 'medium'))
        adv_layout.addWidget(self.cbo_reasoning)

        v_layout.addWidget(adv_frame)

        v_layout.addWidget(SubtitleLabel("嵌入向量配置"))

        v_layout.addWidget(BodyLabel("Embedding API Key:"))
        self.ent_embed_api = LineEdit()
        self.ent_embed_api.setEchoMode(LineEdit.Password)
        self.ent_embed_api.setText(self.settings.embed_api_key)
        v_layout.addWidget(self.ent_embed_api)

        v_layout.addWidget(BodyLabel("Embedding Base URL:"))
        self.ent_embed_base = LineEdit()
        self.ent_embed_base.setText(self.settings.embed_base_url)
        v_layout.addWidget(self.ent_embed_base)

        v_layout.addWidget(BodyLabel("Embedding Model ID:"))
        self.ent_embed_model = LineEdit()
        self.ent_embed_model.setText(self.settings.embed_model_id)
        v_layout.addWidget(self.ent_embed_model)

        v_layout.addWidget(BodyLabel("Embedding 向量维度 (与模型输出一致，否则报错):"))
        self.ent_embed_dim = LineEdit()
        self.ent_embed_dim.setText(str(getattr(self.settings, 'embedding_dimension', 1024)))
        v_layout.addWidget(self.ent_embed_dim)

        v_layout.addWidget(SubtitleLabel("📝 核心图像与文字识别模式"))

        engine_frame = QFrame()
        engine_layout = QHBoxLayout(engine_frame)
        engine_layout.setContentsMargins(0,0,0,0)

        engine_layout.addWidget(BodyLabel("版面分析引擎:"))
        self.cbo_layout_engine = ComboBox()
        self.cbo_layout_engine.addItem("DocLayout-YOLO")
        engine_layout.addWidget(self.cbo_layout_engine)

        engine_layout.addWidget(BodyLabel("OCR 识别引擎:"))
        self.cbo_ocr_engine = ComboBox()
        self.cbo_ocr_engine.addItem("Pix2Text")
        engine_layout.addWidget(self.cbo_ocr_engine)
        engine_layout.addStretch(1)

        v_layout.addWidget(engine_frame)

        self.mode_group = QButtonGroup(self)

        self.mode1 = QRadioButton("1. 仅本地 OCR (最快且免费，但不做任何AI纠错处理)")
        self.mode2 = QRadioButton("2. 本地 OCR + 纯文字 AI 纠错 (省流推荐，AI 仅根据 OCR 文本脑补排版)")
        self.mode3 = QRadioButton("3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐，AI 结合原图修正 OCR 错误)")

        self.mode_group.addButton(self.mode1, 1)
        self.mode_group.addButton(self.mode2, 2)
        self.mode_group.addButton(self.mode3, 3)

        mode_val = self.settings.recognition_mode
        if mode_val == 1: self.mode1.setChecked(True)
        elif mode_val == 2: self.mode2.setChecked(True)
        else: self.mode3.setChecked(True)

        v_layout.addWidget(self.mode1)
        v_layout.addWidget(self.mode2)
        v_layout.addWidget(self.mode3)

        v_layout.addWidget(SubtitleLabel("🚀 高级选项:"))

        self.card_prm = SwitchSettingCard(
            icon=FluentIcon.SETTING,
            title="启用多切片并发",
            content="大于1即启用 PRM 优化",
            configItem=None
        )
        self.card_prm.setChecked(self.settings.use_prm_optimization)
        v_layout.addWidget(self.card_prm)

        batch_frame = QFrame()
        batch_layout = QHBoxLayout(batch_frame)
        batch_layout.setContentsMargins(0,0,0,0)
        batch_layout.addWidget(BodyLabel("单次并发主切片数:"))
        self.ent_prm_batch = SpinBox()
        self.ent_prm_batch.setRange(2, 15)
        self.ent_prm_batch.setValue(self.settings.prm_batch_size)
        batch_layout.addWidget(self.ent_prm_batch)
        batch_layout.addStretch(1)
        v_layout.addWidget(batch_frame)

        btn_save = PrimaryPushButton("💾 保存所有设置")
        btn_save.clicked.connect(self.save_settings)

        save_layout = QHBoxLayout()
        save_layout.addWidget(btn_save)
        save_layout.addStretch(1)
        v_layout.addLayout(save_layout)

        v_layout.addStretch(1)

        scroll_area.setWidget(container)
        self.vBoxLayout.addWidget(scroll_area)

    def on_provider_changed(self, idx):
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
        provider = self.cbo_provider.currentText()
        config = provider_presets.get(provider)

        if not config:
            return

        def update_entry(widget, value):
            if value is not None:
                widget.setText(value)

        update_entry(self.ent_base, config.get("base"))
        update_entry(self.ent_model, config.get("model"))
        update_entry(self.ent_embed_base, config.get("embed_base"))
        update_entry(self.ent_embed_model, config.get("embed_model"))

    def save_settings(self):
        self.settings.api_key = self.ent_api.text().strip()
        self.settings.base_url = self.ent_base.text().strip()
        self.settings.model_id = self.ent_model.text().strip()

        try:
            self.settings.temperature = float(self.ent_temp.text())
        except ValueError:
            self.settings.temperature = 1.0
        try:
            self.settings.top_p = float(self.ent_top_p.text())
        except ValueError:
            self.settings.top_p = 1.0
        try:
            self.settings.max_tokens = int(self.ent_max_tokens.text())
        except ValueError:
            self.settings.max_tokens = 4096

        self.settings.reasoning_effort = self.cbo_reasoning.currentText()

        self.settings.embed_api_key = self.ent_embed_api.text().strip()
        self.settings.embed_base_url = self.ent_embed_base.text().strip()
        self.settings.embed_model_id = self.ent_embed_model.text().strip()

        self.settings.recognition_mode = self.mode_group.checkedId()
        self.settings.use_prm_optimization = self.card_prm.isChecked()
        self.settings.ocr_engine_type = self.cbo_ocr_engine.currentText()
        self.settings.layout_engine_type = self.cbo_layout_engine.currentText()
        self.settings.prm_batch_size = max(2, min(15, self.ent_prm_batch.value()))

        try:
            val = int(self.ent_embed_dim.text().strip())
            if val <= 0:
                raise ValueError("Embedding dimension must be > 0")
            self.settings.embedding_dimension = val
        except ValueError:
            self.settings.embedding_dimension = 1024
            self.ent_embed_dim.setText('1024')

        try:
            self.settings.save()
            self.ai_service.settings = self.settings
            self.parent_app.notify_success("成功", "设置保存成功！")
        except Exception as e:
            logger.error(f"Save settings failed: {e}")
            self.parent_app.notify_error("错误", f"保存设置时发生异常:\n{e}")
