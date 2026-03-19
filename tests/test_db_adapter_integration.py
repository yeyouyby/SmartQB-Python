import sys
import unittest
import os
import shutil
from db_adapter import LanceDBAdapter
import lancedb

TEST_DB_DIR = "test_smartqb_lancedb_tmp"

class TestLanceDBAdapterExecuteInsertTag(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

        self.db = lancedb.connect(TEST_DB_DIR)

        import db_adapter
        self.original_get_db = db_adapter.get_db
        db_adapter.get_db = lambda: self.db

        self.adapter = LanceDBAdapter(machine_id=2)

    def tearDown(self):
        import db_adapter
        db_adapter.get_db = self.original_get_db

        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

    def test_execute_insert_tag_new(self):
        tag_id = self.adapter.execute_insert_tag("Math")
        self.assertIsInstance(tag_id, int)
        df = self.adapter.t_table.to_pandas()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['name'], "Math")
        self.assertEqual(df.iloc[0]['id'], tag_id)

    def test_execute_insert_tag_existing(self):
        tag_id1 = self.adapter.execute_insert_tag("Physics")
        tag_id2 = self.adapter.execute_insert_tag("Physics")
        self.assertEqual(tag_id1, tag_id2)
        df = self.adapter.t_table.to_pandas()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['name'], "Physics")

    def test_execute_insert_tag_with_quotes(self):
        tag_id = self.adapter.execute_insert_tag("O'Reilly")
        self.assertIsInstance(tag_id, int)
        tag_id2 = self.adapter.execute_insert_tag("O'Reilly")
        self.assertEqual(tag_id, tag_id2)
        df = self.adapter.t_table.to_pandas()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['name'], "O'Reilly")
        self.assertEqual(df.iloc[0]['id'], tag_id)

if __name__ == '__main__':
    unittest.main()
