import re

with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

snowflake_impl = """
import time
import threading

class SnowflakeIDGenerator:
    def __init__(self, machine_id=1):
        self.machine_id = machine_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

        # Custom Epoch (e.g., 2024-01-01)
        self.epoch = 1704067200000

        self.machine_id_bits = 5
        self.sequence_bits = 12

        self.max_machine_id = -1 ^ (-1 << self.machine_id_bits)
        self.max_sequence = -1 ^ (-1 << self.sequence_bits)

        self.machine_id_shift = self.sequence_bits
        self.timestamp_left_shift = self.sequence_bits + self.machine_id_bits

    def _gen_timestamp(self):
        return int(time.time() * 1000)

    def next_id(self):
        with self.lock:
            timestamp = self._gen_timestamp()

            if timestamp < self.last_timestamp:
                raise Exception("Clock moved backwards")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.max_sequence
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            return ((timestamp - self.epoch) << self.timestamp_left_shift) | \
                   (self.machine_id << self.machine_id_shift) | \
                   self.sequence

    def _wait_next_millis(self, last_timestamp):
        timestamp = self._gen_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._gen_timestamp()
        return timestamp

id_generator = SnowflakeIDGenerator()

"""

# Insert imports and snowflake impl after imports
import_insert_pos = content.find("class LanceDBAdapter:")
content = content[:import_insert_pos] + snowflake_impl + content[import_insert_pos:]

# Update execute_insert_question
q_insert_pattern = r"        q_df = self\.q_table\.to_pandas\(\)\n        max_q_id = int\(q_df\['id'\]\.max\(\)\) if not q_df\.empty else 0\n        new_q_id = max_q_id \+ 1"
new_q_insert = "        new_q_id = id_generator.next_id()"
content = re.sub(q_insert_pattern, new_q_insert, content)

# Update execute_insert_tag
t_insert_pattern = r"            max_t_id = int\(t_df\['id'\]\.max\(\)\) if not t_df\.empty else 0\n            new_t_id = max_t_id \+ 1"
new_t_insert = "            new_t_id = id_generator.next_id()"
content = re.sub(t_insert_pattern, new_t_insert, content)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
