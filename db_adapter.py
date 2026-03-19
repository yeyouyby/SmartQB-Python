import pyarrow as pa
import logging
import json
import time
import threading
logger = logging.getLogger(__name__)

import lancedb
def get_db():
    logger.info("Connecting to LanceDB database: 'smartqb_lancedb'")
    return lancedb.connect('smartqb_lancedb')

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

        if machine_id < 0 or machine_id > self.max_machine_id:
            raise ValueError(f"Machine ID must be between 0 and {self.max_machine_id}")


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

            return ((timestamp - self.epoch) << self.timestamp_left_shift) |                    (self.machine_id << self.machine_id_shift) |                    self.sequence

    def _wait_next_millis(self, last_timestamp):
        timestamp = self._gen_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._gen_timestamp()
        return timestamp

id_generator = SnowflakeIDGenerator()

class LanceDBAdapter:
    def __init__(self):
        self.db = get_db()
        try:
            self.q_table = self.db.open_table("questions")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'questions' table, attempting to create it.", exc_info=True)
            self.q_table = self.db.create_table(
                "questions",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("content", pa.string()),
                    pa.field("logic_descriptor", pa.string()),
                    pa.field("difficulty", pa.float64()),
                    pa.field("vector", pa.list_(pa.float32(), 1536)),
                    pa.field("diagram_base64", pa.string()),
                ]),
            )

        try:
            self.t_table = self.db.open_table("tags")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'tags' table, attempting to create it.", exc_info=True)
            self.t_table = self.db.create_table(
                "tags",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("name", pa.string()),
                ]),
            )

        try:
            self.qt_table = self.db.open_table("question_tags")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'question_tags' table, attempting to create it.", exc_info=True)
            self.qt_table = self.db.create_table(
                "question_tags",
                schema=pa.schema([
                    pa.field("question_id", pa.int64()),
                    pa.field("tag_id", pa.int64()),
                ]),
            )

    def execute_insert_question(self, content, logic, vec, diagram_b64):
        if not vec:
            vec = [0.0] * 1536
        new_q_id = id_generator.next_id()
        self.q_table.add([{
            "id": new_q_id,
            "content": content,
            "logic_descriptor": logic or "",
            "difficulty": 0.0,
            "vector": vec,
            "diagram_base64": diagram_b64 or ""
        }])
        return new_q_id

    def execute_insert_tag(self, tag_name):
        # Prevent check-then-insert race
        with id_generator.lock:
            # Escape single quotes in tag_name for the where clause
            safe_tag_name = tag_name.replace("'", "''")
            # Check for existing tag using LanceDB search for performance
            existing = self.t_table.search().where(f"name = '{safe_tag_name}'").limit(1).to_list()
            if existing:
                return int(existing[0]['id'])
            # Note: next_id() also uses id_generator.lock, so we MUST return or
            # exit this 'with' block before calling it to avoid a deadlock.

        new_t_id = id_generator.next_id()
        self.t_table.add([{"id": new_t_id, "name": tag_name}])
        return new_t_id

    def execute_insert_question_tag(self, q_id, t_id):
        qt_df = self.qt_table.to_pandas()
        exists = not qt_df.empty and len(qt_df[(qt_df['question_id'] == q_id) & (qt_df['tag_id'] == t_id)]) > 0
        if not exists:
            self.qt_table.add([{"question_id": int(q_id), "tag_id": int(t_id)}])

    def get_all_tags(self):
        t_df = self.t_table.to_pandas()
        if t_df.empty: return []
        return [(int(r['id']), r['name']) for _, r in t_df.iterrows()]

    def search_questions(self, kw):
        if not kw:
            q_df = self.q_table.to_pandas()
            if q_df.empty: return []
            q_df = q_df.sort_values(by="id", ascending=False)
            return [(int(r['id']), r['content']) for _, r in q_df.iterrows()]

        # SQL equivalent: LIKE %kw%
        q_df = self.q_table.to_pandas()
        t_df = self.t_table.to_pandas()
        qt_df = self.qt_table.to_pandas()

        if q_df.empty: return []

        # Match content
        content_matches = q_df[q_df['content'].str.contains(kw, case=False, na=False)]['id'].tolist()

        # Match tags
        tag_matches = []
        if not t_df.empty and not qt_df.empty:
            matching_tags = t_df[t_df['name'].str.contains(kw, case=False, na=False)]['id'].tolist()
            if matching_tags:
                tag_matches = qt_df[qt_df['tag_id'].isin(matching_tags)]['question_id'].tolist()

        all_matches = set(content_matches + tag_matches)

        if not all_matches: return []

        res_df = q_df[q_df['id'].isin(all_matches)].sort_values(by="id", ascending=False)
        return [(int(r['id']), r['content']) for _, r in res_df.iterrows()]

    def get_question(self, q_id):
        try:
            q_id = int(q_id)
            res = self.q_table.search().where(f"id = {q_id}").limit(1).to_list()
            if not res:
                return None, None
            return res[0]['content'], res[0].get('diagram_base64', '')
        except Exception as e:
            logger.error(f"Error getting question: {e}")
            return None, None

    def get_question_tags(self, q_id):
        try:
            q_id = int(q_id)
            qt_res = self.qt_table.search().where(f"question_id = {q_id}").to_list()
            if not qt_res:
                return []

            tag_ids = [r['tag_id'] for r in qt_res]
            if not tag_ids:
                return []

            # Filter tags by id. We can load to pandas since it's smaller, or use where IN equivalent (LanceDB might lack IN)
            t_df = self.t_table.to_pandas()
            if t_df.empty:
                return []
            names = t_df[t_df['id'].isin(tag_ids)]['name'].tolist()
            return [(n,) for n in names]
        except Exception as e:
            logger.error(f"Error getting question tags: {e}")
            return []

    def clear_question_tags(self, q_id):
        try:
            q_id = int(q_id)
            self.qt_table.delete(f"question_id = {q_id}")
        except Exception as e:
            logger.error(f"Error clearing question tags: {e}")

    def delete_question(self, q_id):
        try:
            q_id = int(q_id)
            self.qt_table.delete(f"question_id = {q_id}")
            self.q_table.delete(f"id = {q_id}")
        except Exception as e:
            logger.error(f"Error deleting question: {e}")
