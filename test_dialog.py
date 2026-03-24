from PySide6.QtWidgets import QApplication
from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit, PrimaryPushButton, PushButton

class APIRetryDialog(MessageBoxBase):
    def __init__(self, error_msg, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("⚠️ API 请求失败")
        self.errorLabel = SubtitleLabel(f"发生错误:\n{error_msg}")
        self.errorLabel.setStyleSheet("color: red;")

        self.ent_api = LineEdit()
        self.ent_api.setPlaceholderText("API Key")
        self.ent_base = LineEdit()
        self.ent_base.setPlaceholderText("Base URL")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.errorLabel)
        self.viewLayout.addWidget(self.ent_api)
        self.viewLayout.addWidget(self.ent_base)

        self.yesButton.setText("💾 保存并继续重试")
        self.cancelButton.setText("⏭️ 取消并降级跳过")

        self.widget.setMinimumWidth(350)
