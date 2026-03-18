import os
import shutil
import pytest
import pyarrow as pa
from db_adapter import LanceDBAdapter, SnowflakeIDGenerator

@pytest.fixture
def mock_db():
    import db_adapter
    # Override get_db to use a local test directory
    test_db_path = "test_lancedb_dir"
    import lancedb

    def mock_get_db():
        return lancedb.connect(test_db_path)

    original_get_db = db_adapter.get_db
    db_adapter.get_db = mock_get_db

    # ensure tables
    adapter = LanceDBAdapter()
    db = adapter.db

    table_names = db.table_names() if hasattr(db, "table_names") else db.list_tables()

    if "questions" not in table_names:
        db.create_table("questions", schema=pa.schema([
            pa.field("id", pa.int64()),
            pa.field("content", pa.string()),
            pa.field("logic_descriptor", pa.string()),
            pa.field("difficulty", pa.float64()),
            pa.field("vector", pa.list_(pa.float32(), 1536)),
            pa.field("diagram_base64", pa.string()),
        ]))
    if "tags" not in table_names:
        db.create_table("tags", schema=pa.schema([
            pa.field("id", pa.int64()),
            pa.field("name", pa.string()),
        ]))
    if "question_tags" not in table_names:
        db.create_table("question_tags", schema=pa.schema([
            pa.field("question_id", pa.int64()),
            pa.field("tag_id", pa.int64()),
        ]))

    # Refresh the adapter so it binds the tables correctly
    adapter = LanceDBAdapter()
    yield adapter

    # cleanup
    db_adapter.get_db = original_get_db
    if os.path.exists(test_db_path):
        shutil.rmtree(test_db_path)

def test_snowflake_id():
    gen = SnowflakeIDGenerator(machine_id=1)
    id1 = gen.next_id()
    id2 = gen.next_id()
    assert id1 != id2
    assert id1 > 0

def test_db_adapter_crud(mock_db):
    mock_db.execute_insert_tag("math")
    tags = mock_db.get_all_tags()

    assert any(t[1] == "math" for t in tags)
    t_id = next(t[0] for t in tags if t[1] == "math")

    q_id = mock_db.execute_insert_question("What is 1+1?", "Basic math logic", [0.1]*1536, "")

    q_data = mock_db.get_question(q_id)
    assert q_data is not None

    mock_db.execute_insert_question_tag(q_id, t_id)

    q_tags = mock_db.get_question_tags(q_id)
    # The return format of get_question_tags might just be a list of strings
    if len(q_tags) > 0 and isinstance(q_tags[0], str):
        assert "math" in q_tags
    else:
        assert any("math" in t for t in q_tags)

    mock_db.delete_question(q_id)
    q_data_after = mock_db.get_question(q_id)
    assert q_data_after is None or q_data_after == (None, None)
