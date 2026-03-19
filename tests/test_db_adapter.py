import os
import pytest
import shutil
import lancedb
import pyarrow as pa
from db_adapter import LanceDBAdapter

# Set up a temporary database for testing
TEST_DB_PATH = "test_smartqb_lancedb"

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    # Remove existing test database if it exists
    if os.path.exists(TEST_DB_PATH):
        shutil.rmtree(TEST_DB_PATH)

    # Mock the get_db function in db_adapter to use our test database
    import db_adapter
    original_get_db = db_adapter.get_db
    db_adapter.get_db = lambda: lancedb.connect(TEST_DB_PATH)

    yield

    # Cleanup
    if os.path.exists(TEST_DB_PATH):
        shutil.rmtree(TEST_DB_PATH)
    db_adapter.get_db = original_get_db

@pytest.fixture
def adapter():
    return LanceDBAdapter()

def test_execute_insert_tag(adapter):
    tag_name = "Test Tag"

    # Insert a new tag
    tag_id1 = adapter.execute_insert_tag(tag_name)
    assert tag_id1 is not None

    # Verify it exists in the table
    tags = adapter.get_all_tags()
    assert any(name == tag_name and id == tag_id1 for id, name in tags)

    # Insert the same tag again
    tag_id2 = adapter.execute_insert_tag(tag_name)

    # Verify it returns the same ID and doesn't create a duplicate
    assert tag_id1 == tag_id2

    tags = adapter.get_all_tags()
    matching_tags = [name for id, name in tags if name == tag_name]
    assert len(matching_tags) == 1

def test_execute_insert_multiple_tags(adapter):
    tag1 = "Tag 1"
    tag2 = "Tag 2"

    id1 = adapter.execute_insert_tag(tag1)
    id2 = adapter.execute_insert_tag(tag2)

    assert id1 != id2

    tags = adapter.get_all_tags()
    names = [name for id, name in tags]
    assert tag1 in names
    assert tag2 in names
