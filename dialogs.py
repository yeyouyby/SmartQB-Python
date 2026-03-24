from qfluentwidgets import MessageBoxBase, SubtitleLabel, BodyLabel, LineEdit

class APIRetryDialog(MessageBoxBase):
    def __init__(self, error_msg, current_api, current_base, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("⚠️ API 请求失败")
        self.errorLabel = BodyLabel(f"发生错误:\n{error_msg}")
        self.errorLabel.setStyleSheet("color: red;")
        self.errorLabel.setWordWrap(True)

        self.ent_api = LineEdit()
        self.ent_api.setPlaceholderText("API Key")
        self.ent_api.setText(current_api)

        self.ent_base = LineEdit()
        self.ent_base.setPlaceholderText("Base URL")
        self.ent_base.setText(current_base)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.errorLabel)
        self.viewLayout.addWidget(self.ent_api)
        self.viewLayout.addWidget(self.ent_base)

        self.yesButton.setText("💾 保存并继续重试")
        self.cancelButton.setText("⏭️ 取消并降级跳过")

        self.widget.setMinimumWidth(400)
