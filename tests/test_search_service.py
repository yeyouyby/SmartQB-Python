import pytest
from search_service import vector_search_db

class MockAIService:
    def get_embedding(self, text):
        if text == "fail": return None
        return [0.5] * 1536

def test_vector_search_db(monkeypatch):
    class MockTable:
        def search(self, vec):
            return self
        def limit(self, l):
            return self
        def to_pandas(self):
            import pandas as pd
            return pd.DataFrame([{"id": 1, "content": "mocked", "_distance": 0.1}])

    class MockAdapter:
        @property
        def q_table(self):
            return MockTable()

    monkeypatch.setattr("search_service.LanceDBAdapter", MockAdapter)

    ai = MockAIService()
    res = vector_search_db(ai, "test query")
    assert len(res) == 1
    assert res[0]["content"] == "mocked"

    res_fail = vector_search_db(ai, "fail")
    assert res_fail == []
