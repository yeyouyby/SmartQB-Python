import sys
from unittest.mock import MagicMock, patch

# Mock dependencies that are missing in the environment and would prevent import
sys.modules['pyarrow'] = MagicMock()
sys.modules['lancedb'] = MagicMock()

import unittest
from db_adapter import LanceDBAdapter
import time

class TestLanceDBAdapterNextId(unittest.TestCase):
    def setUp(self):
        # We need to mock get_db because LanceDBAdapter calls it in __init__
        with patch('db_adapter.get_db') as mock_get_db:
            mock_get_db.return_value = MagicMock()
            self.adapter = LanceDBAdapter(machine_id=1)

    def test_next_id_incremental(self):
        id1 = self.adapter.next_id()
        id2 = self.adapter.next_id()
        self.assertGreater(id2, id1)

    def test_next_id_same_millisecond(self):
        with patch('time.time') as mock_time:
            mock_time.return_value = 1700000000.000
            id1 = self.adapter.next_id()
            id2 = self.adapter.next_id()

            # Verify they are different (sequence should increment)
            self.assertNotEqual(id1, id2)

            # Extract sequences
            seq1 = id1 & self.adapter.sequence_mask
            seq2 = id2 & self.adapter.sequence_mask
            self.assertEqual(seq1, 0)
            self.assertEqual(seq2, 1)

    def test_next_id_sequence_overflow(self):
        with patch('time.time') as mock_time:
            # We need enough returns for the loop in next_id and _wait_next_millis
            # next_id calls _gen_timestamp once.
            # If sequence reaches 0, it calls _wait_next_millis which calls _gen_timestamp in a loop.

            # Total calls needed: (max_sequence + 1) for first IDs + 1 for next_id + some for _wait_next_millis
            mock_time.side_effect = [1700000000.000] * (self.adapter.sequence_mask + 2) + [1700000000.001]

            # Use up all sequences for the same millisecond
            for _ in range(self.adapter.sequence_mask + 1):
                self.adapter.next_id()

            # The next call should trigger _wait_next_millis
            id_after_overflow = self.adapter.next_id()

            # Verify timestamp increased
            timestamp = (id_after_overflow >> self.adapter.timestamp_left_shift) + self.adapter.twepoch
            self.assertEqual(timestamp, 1700000000001)
            # Sequence should reset
            seq = id_after_overflow & self.adapter.sequence_mask
            self.assertEqual(seq, 0)

    def test_next_id_clock_backwards(self):
        self.adapter.last_timestamp = 1700000000005
        with patch('time.time') as mock_time:
            mock_time.return_value = 1700000000.000 # 1700000000000 ms
            with self.assertRaises(Exception) as cm:
                self.adapter.next_id()
            self.assertIn("Clock moved backwards", str(cm.exception))
            self.assertIn("Refusing to generate id for 5 milliseconds", str(cm.exception))

    def test_id_uniqueness(self):
        ids = set()
        num_ids = 1000
        for _ in range(num_ids):
            ids.add(self.adapter.next_id())
        self.assertEqual(len(ids), num_ids)

if __name__ == '__main__':
    unittest.main()
