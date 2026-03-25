import logging
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
        self.ocr_engine_type = "Pix2Text"
        self.layout_engine_type = "DocLayout-YOLO"
        self.use_prm_optimization = False
        self.prm_batch_size = 3
        self.temperature = 1.0
        self.top_p = 1.0
        self.max_tokens = 4096
        self.reasoning_effort = "medium"

        self.keyring_service_name = "SmartQB_Pro_V3"
        self.keyring_username_api = "default_api_key"
        self.keyring_username_embed = "default_embed_api_key"

        self.load()

    def load(self, allow_plaintext_fallback=True):
        # Load standard settings from JSON
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if not isinstance(d, dict):
                    return

                self.base_url = d.get("base_url", "")
                self.model_id = d.get("model_id", "gpt-4o-mini")
                self.embed_base_url = d.get("embed_base_url", "")
                self.embed_model_id = d.get("embed_model_id", "text-embedding-3-small")

                self.recognition_mode = d.get("recognition_mode", 2)
                engine_type = d.get("ocr_engine_type", "Pix2Text")
                self.ocr_engine_type = (
                    engine_type if engine_type in {"Pix2Text", "Surya"} else "Pix2Text"
                )
                layout_type = d.get("layout_engine_type", "DocLayout-YOLO")
                self.layout_engine_type = (
                    layout_type
                    if isinstance(layout_type, str)
                    and layout_type in {"DocLayout-YOLO", "Surya"}
                    else "DocLayout-YOLO"
                )
                self.use_prm_optimization = d.get("use_prm_optimization", False)
                self.prm_batch_size = d.get("prm_batch_size", 3)
                self.temperature = d.get("temperature", 1.0)
                self.top_p = d.get("top_p", 1.0)
                self.max_tokens = d.get("max_tokens", 4096)
                self.reasoning_effort = d.get("reasoning_effort", "medium")

                if allow_plaintext_fallback:
                    self.api_key = d.get("api_key", "")
                    self.embed_api_key = d.get("embed_api_key", "")

            except (OSError, json.JSONDecodeError):
                pass

        if keyring is not None:
            try:
                secure_api_key = keyring.get_password(
                    self.keyring_service_name, self.keyring_username_api
                )
                if secure_api_key:
                    self.api_key = secure_api_key

                secure_embed_key = keyring.get_password(
                    self.keyring_service_name, self.keyring_username_embed
                )
                if secure_embed_key:
                    self.embed_api_key = secure_embed_key
            except Exception as e:
                logging.warning(f"Failed to load keys from keyring: {e}")
                # We do not swallow error if the caller prefers strict keyring failure
                pass  # Never crash

    def save(self, allow_plaintext_fallback=False):
        keyring_success = False
        if keyring is not None:
            try:
                if self.api_key:
                    keyring.set_password(
                        self.keyring_service_name,
                        self.keyring_username_api,
                        self.api_key,
                    )
                else:
                    keyring.delete_password(
                        self.keyring_service_name, self.keyring_username_api
                    )
            except keyring.errors.PasswordDeleteError:
                pass
            except Exception as e:
                logging.warning(f"Keyring save api_key failed: {e}")
                pass  # Never crash, fallback to plaintext

            try:
                if self.embed_api_key:
                    keyring.set_password(
                        self.keyring_service_name,
                        self.keyring_username_embed,
                        self.embed_api_key,
                    )
                else:
                    keyring.delete_password(
                        self.keyring_service_name, self.keyring_username_embed
                    )
            except keyring.errors.PasswordDeleteError:
                pass
            except Exception as e:
                logging.warning(f"Keyring save embed_api_key failed: {e}")
                pass  # Never crash, fallback to plaintext

            keyring_success = True

        tmp_file = f"{SETTINGS_FILE}.tmp"
        try:
            payload = {
                "base_url": self.base_url,
                "model_id": self.model_id,
                "embed_base_url": self.embed_base_url,
                "embed_model_id": self.embed_model_id,
                "recognition_mode": self.recognition_mode,
                "ocr_engine_type": self.ocr_engine_type,
                "layout_engine_type": self.layout_engine_type,
                "use_prm_optimization": self.use_prm_optimization,
                "prm_batch_size": self.prm_batch_size,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "reasoning_effort": self.reasoning_effort,
            }
            if not keyring_success and allow_plaintext_fallback:
                payload["api_key"] = self.api_key
                payload["embed_api_key"] = self.embed_api_key

            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4)
            os.replace(tmp_file, SETTINGS_FILE)
        except OSError:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
