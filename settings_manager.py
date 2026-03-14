import os
import json
try:
    import keyring
except ImportError:
    keyring = None
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

        self.recognition_mode = 2
        self.use_prm_optimization = False
        self.prm_batch_size = 3

        self.keyring_service_name = "SmartQB_Pro_V3"
        self.keyring_username_api = "default_api_key"
        self.keyring_username_embed = "default_embed_api_key"

        self.load()

    def load(self):
        # Load standard settings from JSON
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if not isinstance(d, dict): return

                self.base_url = d.get("base_url", "")
                self.model_id = d.get("model_id", "gpt-4o-mini")
                self.embed_base_url = d.get("embed_base_url", "")
                self.embed_model_id = d.get("embed_model_id", "text-embedding-3-small")

                self.recognition_mode = d.get("recognition_mode", 2)
                self.use_prm_optimization = d.get("use_prm_optimization", False)
                self.prm_batch_size = d.get("prm_batch_size", 3)

                # Fallback for plain text keys if keyring fails or is not populated
                self.api_key = d.get("api_key", "")
                self.embed_api_key = d.get("embed_api_key", "")

            except (OSError, json.JSONDecodeError):
                pass

        # Try to load API keys securely from Keyring
        try:
            secure_api_key = keyring.get_password(self.keyring_service_name, self.keyring_username_api)
            if secure_api_key:
                self.api_key = secure_api_key

            secure_embed_key = keyring.get_password(self.keyring_service_name, self.keyring_username_embed)
            if secure_embed_key:
                self.embed_api_key = secure_embed_key
        except Exception as e:
            # Silently fallback
            pass

    def save(self):
        # Try keyring first, if fails we must save to JSON
        keyring_success = False
        try:
            if keyring is None:
                raise Exception("Keyring module not available")

            if self.api_key:
                keyring.set_password(self.keyring_service_name, self.keyring_username_api, self.api_key)
            else:
                try: keyring.delete_password(self.keyring_service_name, self.keyring_username_api)
                except Exception: pass

            if self.embed_api_key:
                keyring.set_password(self.keyring_service_name, self.keyring_username_embed, self.embed_api_key)
            else:
                try: keyring.delete_password(self.keyring_service_name, self.keyring_username_embed)
                except Exception: pass

            keyring_success = True
        except Exception as e:
            import logging
            logging.warning(f"Keyring save failed, falling back to JSON: {e}")

        # Save standard settings
        tmp_file = f"{SETTINGS_FILE}.tmp"
        try:
            payload = {
                "base_url": self.base_url,
                "model_id": self.model_id,
                "embed_base_url": self.embed_base_url,
                "embed_model_id": self.embed_model_id,
                "recognition_mode": self.recognition_mode,
                "use_prm_optimization": self.use_prm_optimization,
                "prm_batch_size": self.prm_batch_size
            }
            if not keyring_success:
                # Fallback to plain text save if keyring is unavailable
                payload["api_key"] = self.api_key
                payload["embed_api_key"] = self.embed_api_key

            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)
            os.replace(tmp_file, SETTINGS_FILE)
        except OSError:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)