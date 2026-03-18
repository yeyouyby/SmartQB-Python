import pytest
from ai_service import AIService
from settings_manager import SettingsManager

class DummySettings(SettingsManager):
    def load(self, fallback=True):
        pass
    def __init__(self):
        self.api_key = "dummy"
        self.base_url = "dummy"
        self.model_id = "dummy"
        self.embed_api_key = "dummy"
        self.embed_base_url = "dummy"
        self.embed_model_id = "dummy"

def test_ai_service_client_creation():
    settings = DummySettings()
    ai = AIService(settings)
    client = ai.get_client()
    assert client is not None
    assert client.api_key == "dummy"

def test_ai_service_parse_json_success():
    ai = AIService(DummySettings())
    json_str = '```json\n{"Questions": [{"Content": "1+1=?", "Status": "Complete"}], "NextIndex": 2, "PendingFragment": ""}\n```'
    parsed = ai._parse_json(json_str)
    assert "Questions" in parsed
    assert len(parsed["Questions"]) == 1

def test_ai_service_parse_json_fail():
    ai = AIService(DummySettings())
    json_str = "Invalid JSON string"
    with pytest.raises(Exception):
        ai._parse_json(json_str)
