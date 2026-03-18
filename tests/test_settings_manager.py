import os
import json
import pytest
import config
from settings_manager import SettingsManager

@pytest.fixture
def override_config():
    old_file = config.SETTINGS_FILE
    config.SETTINGS_FILE = "test_settings.json"
    yield
    config.SETTINGS_FILE = old_file
    if os.path.exists("test_settings.json"):
        os.remove("test_settings.json")

def test_settings_save_load(override_config):
    settings = SettingsManager()
    settings.api_key = "test_key"
    settings.base_url = "http://test.com"
    settings.save(allow_plaintext_fallback=True)

    new_sm = SettingsManager()
    new_sm.load(allow_plaintext_fallback=True)

    assert new_sm.base_url == "http://test.com"
