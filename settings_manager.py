# settings_manager.py
import os
import json
from config import SETTINGS_FILE

# ==========================================
# 设置服务
# ==========================================

class SettingsManager:
    def __init__(self):
        self.api_key = ""
        self.base_url = ""
        self.model_id = "gpt-4o-mini"

        self.embed_api_key = ""
        self.embed_base_url = ""
        self.embed_model_id = "text-embedding-3-small"

        # 1: 仅本地OCR
        # 2: 本地OCR + 纯文字 AI 纠错
        # 3: 本地OCR + 支持图片识别的 Vision AI 纠错
        self.recognition_mode = 2
        self.use_prm_optimization = False
        self.prm_batch_size = 3
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                self.api_key = d.get("api_key", "")
                self.base_url = d.get("base_url", "")
                self.model_id = d.get("model_id", "gpt-4o-mini")

                self.embed_api_key = d.get("embed_api_key", "")
                self.embed_base_url = d.get("embed_base_url", "")
                self.embed_model_id = d.get("embed_model_id", "text-embedding-3-small")

                self.recognition_mode = d.get("recognition_mode", 2)
                self.use_prm_optimization = d.get("use_prm_optimization", False)
                self.prm_batch_size = d.get("prm_batch_size", 3)

    def save(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "api_key": self.api_key,
                "base_url": self.base_url,
                "model_id": self.model_id,
                "embed_api_key": self.embed_api_key,
                "embed_base_url": self.embed_base_url,
                "embed_model_id": self.embed_model_id,
                "recognition_mode": self.recognition_mode,
                "use_prm_optimization": self.use_prm_optimization,
                "prm_batch_size": self.prm_batch_size
            }, f, indent=4)
