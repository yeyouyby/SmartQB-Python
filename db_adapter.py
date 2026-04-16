from utils import pad_or_truncate_vector
import pyarrow as pa
import logging
import time
import threading
import uuid
import zlib

import lancedb
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)


def get_db():
    logger.info("Connecting to LanceDB database: 'smartqb_lancedb'")
    return lancedb.connect("smartqb_lancedb")


_id_lock = threading.RLock()
_last_timestamp = -1
_sequence = 0


class LanceDBAdapter:
    def __init__(self, machine_id=None):
        self.db = get_db()

        self.settings = SettingsManager()
        embedding_dim_str = getattr(self.settings, "embedding_dimension", "1536")
        try:
            self.embedding_dimension = int(embedding_dim_str)
        except (ValueError, TypeError):
            self.embedding_dimension = 1536

        if machine_id is None:
            mac_address = str(uuid.getnode())
            machine_id = zlib.crc32(mac_address.encode("utf-8")) % 1024

        self.machine_id = machine_id

        # Custom Epoch (e.g., 2024-01-01)
        self.twepoch = 1704067200000

        self.machine_id_bits = 10  # 10 bits allows values 0-1023
        self.sequence_bits = 12

        self.max_machine_id = -1 ^ (-1 << self.machine_id_bits)
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)

        self.machine_id_shift = self.sequence_bits
        self.timestamp_left_shift = self.sequence_bits + self.machine_id_bits

        if machine_id < 0 or machine_id > self.max_machine_id:
            raise ValueError(f"Machine ID must be between 0 and {self.max_machine_id}")

        try:
            self.q_table = self.db.open_table("questions")
            if "snowflake_id" not in self.q_table.schema.names:
                logger.warning(
                    "Legacy 'questions' table detected. Dropping to apply new Phase 3 schema."
                )
                self.db.drop_table("questions")
                raise FileNotFoundError("Force recreate")
        except Exception:
            logger.warning(
                "Failed to open 'questions' table, attempting to create it.",
                exc_info=True,
            )
            self.q_table = self.db.create_table(
                "questions",
                schema=pa.schema(
                    [
                        pa.field("snowflake_id", pa.int64()),
                        pa.field(
                            "vector", pa.list_(pa.float32(), self.embedding_dimension)
                        ),
                        pa.field("content_md", pa.string()),
                        pa.field("logic_chain", pa.string()),
                        pa.field("tags", pa.list_(pa.string())),
                        pa.field("created_at", pa.timestamp("s")),
                    ]
                ),
            )

        try:
            self.t_table = self.db.open_table("tags")
        except Exception:
            logger.warning(
                "Failed to open 'tags' table, attempting to create it.", exc_info=True
            )
            self.t_table = self.db.create_table(
                "tags",
                schema=pa.schema(
                    [
                        pa.field("id", pa.int64()),
                        pa.field("name", pa.string()),
                    ]
                ),
            )

        try:
            self.qt_table = self.db.open_table("question_tags")
        except Exception:
            logger.warning(
                "Failed to open 'question_tags' table, attempting to create it.",
                exc_info=True,
            )
            self.qt_table = self.db.create_table(
                "question_tags",
                schema=pa.schema(
                    [
                        pa.field("question_id", pa.int64()),
                        pa.field("tag_id", pa.int64()),
                    ]
                ),
            )

    def _gen_timestamp(self):
        return int(time.time() * 1000)

    def next_id(self):
        global _last_timestamp, _sequence
        with _id_lock:
            timestamp = self._gen_timestamp()
            if timestamp < _last_timestamp:
                raise RuntimeError(
                    f"Clock moved backwards. Refusing to generate id for {_last_timestamp - timestamp} milliseconds"
                )
            if timestamp == _last_timestamp:
                _sequence = (_sequence + 1) & self.sequence_mask
                if _sequence == 0:
                    timestamp = self._wait_next_millis(_last_timestamp)
            else:
                _sequence = 0
            _last_timestamp = timestamp
            return (
                ((timestamp - self.twepoch) << self.timestamp_left_shift)
                | (self.machine_id << self.machine_id_shift)
                | _sequence
            )

    def _wait_next_millis(self, last_timestamp):
        timestamp = self._gen_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._gen_timestamp()
        return timestamp

    def execute_insert_question(self, content, logic, vec, diagram_b64):
        if vec is None:
            vec = []
        vec = list(vec)

        target_dim = self.embedding_dimension
        try:
            schema = self.q_table.schema
            if schema and "vector" in schema.names:
                vector_type = schema.field("vector").type
                if pa.types.is_fixed_size_list(vector_type):
                    target_dim = vector_type.list_size
        except Exception as e:
            logger.warning(
                f"Could not get target vector dimension from schema: {e}", exc_info=True
            )

        vec = pad_or_truncate_vector(vec, target_dim)

        new_q_id = self.next_id()
        self.q_table.add(
            [
                {
                    "id": new_q_id,
                    "content": content,
                    "logic_descriptor": logic or "",
                    "difficulty": 0.0,
                    "vector": vec,
                    "diagram_base64": diagram_b64 or "",
                }
            ]
        )
        return new_q_id

    def execute_insert_tag(self, tag_name):
        # Prevent check-then-insert race
        with _id_lock:
            try:
                # Escape single quotes for DataFusion SQL parser
                safe_tag_name = tag_name.replace("'", "''")
                res = (
                    self.t_table.search()
                    .where(f"name = '{safe_tag_name}'")
                    .limit(1)
                    .to_list()
                )
                if res:
                    return int(res[0]["id"])
            except Exception as e:
                # If the error is related to query parsing, fall back to a safer method.
                err_str = str(e).lower()
                is_query_error = any(
                    keyword in err_str
                    for keyword in [
                        "syntax",
                        "parse",
                        "datafusion",
                        "lanceerror",
                        "invalid user input",
                    ]
                )

                if is_query_error:
                    logger.warning(
                        f"LanceDB search failed for tag '{tag_name}', falling back to pandas due to query error. Error: {e}"
                    )
                    # Using pandas as a fallback for complex tag names
                    t_df = self.t_table.to_pandas()
                    if not t_df.empty:
                        matching_rows = t_df[t_df["name"] == tag_name]
                        if not matching_rows.empty:
                            return int(matching_rows.iloc[0]["id"])
                else:
                    # For other errors, log and re-raise.
                    logger.error(
                        f"LanceDB search failed for tag '{tag_name}'. Error: {e}",
                        exc_info=True,
                    )
                    raise

            new_t_id = self.next_id()
            self.t_table.add([{"id": new_t_id, "name": tag_name}])
            return new_t_id

    def execute_insert_question_tag(self, q_id, t_id):
        # Prevent check-then-insert race
        with _id_lock:
            res = (
                self.qt_table.search()
                .where(f"question_id = {int(q_id)} AND tag_id = {int(t_id)}")
                .limit(1)
                .to_list()
            )
            if not res:
                self.qt_table.add([{"question_id": int(q_id), "tag_id": int(t_id)}])

    def add_questions_bulk(self, arrow_table):
        """
        Bulk insert an arrow table into LanceDB.
        Expects a PyArrow Table matching the LanceDB schema.
        """
        try:
            self.q_table.add(arrow_table)
            logger.info(
                f"Successfully bulk inserted {arrow_table.num_rows} questions into LanceDB."
            )
        except Exception as e:
            logger.error(
                f"Failed to bulk insert questions into LanceDB: {e}", exc_info=True
            )
            raise

    def get_all_tags(self):
        try:
            # For a moderate number of tags, grabbing all via limit(10000) is fine
            # For scale, pagination or autocomplete is preferred
            res = self.t_table.search().limit(10000).to_list()
            return [(int(r["id"]), r["name"]) for r in res]
        except Exception as e:
            logger.error(f"LanceDB get_all_tags failed: {e}", exc_info=True)
            return []

    def search_questions(self, kw):
        if not kw:
            # Native lancedb to retrieve all, sorting in memory is usually fine for a reasonable number of rows
            # but for true scale we might need limit/offset.
            res = self.q_table.search().limit(1000).to_list()  # Adding a safety limit
            res = sorted(res, key=lambda x: x["snowflake_id"], reverse=True)
            return [(int(r["snowflake_id"]), r["content_md"]) for r in res]

        try:
            safe_kw = kw.replace("'", "''")
            # 1. Search in questions using LanceDB where
            q_res = (
                self.q_table.search()
                .where(f"content_md LIKE '%{safe_kw}%'")
                .limit(1000)
                .to_list()
            )
            content_matches = [r["snowflake_id"] for r in q_res]

            # 2. Search in tags
            t_res = (
                self.t_table.search()
                .where(f"name LIKE '%{safe_kw}%'")
                .limit(1000)
                .to_list()
            )
            tag_matches = []
            if t_res:
                tag_ids = [r["id"] for r in t_res]
                tag_id_str = ",".join(map(str, tag_ids))
                qt_res = (
                    self.qt_table.search()
                    .where(f"tag_id IN ({tag_id_str})")
                    .limit(1000)
                    .to_list()
                )
                tag_matches = [r["question_id"] for r in qt_res]

            all_match_ids = list(set(content_matches + tag_matches))
            if not all_match_ids:
                return []

            # 3. Fetch final questions
            id_str = ",".join(map(str, all_match_ids))
            final_res = (
                self.q_table.search()
                .where(f"snowflake_id IN ({id_str})")
                .limit(1000)
                .to_list()
            )
            final_res = sorted(final_res, key=lambda x: x["snowflake_id"], reverse=True)
            return [(int(r["snowflake_id"]), r["content_md"]) for r in final_res]

        except Exception as e:
            logger.error(f"LanceDB search_questions failed: {e}", exc_info=True)
            return []

    def get_question(self, q_id):
        try:
            q_id = int(q_id)
            res = (
                self.q_table.search().where(f"snowflake_id = {q_id}").limit(1).to_list()
            )
            if not res:
                return None, None
            return res[0]["content_md"], ""
        except Exception as e:
            logger.error(f"Error getting question: {e}")
            return None, None

    def get_question_tags(self, q_id):
        try:
            q_id = int(q_id)
            qt_res = self.qt_table.search().where(f"question_id = {q_id}").to_list()
            if not qt_res:
                return []

            tag_ids = [r["tag_id"] for r in qt_res]
            if not tag_ids:
                return []

            tag_id_str = ",".join(map(str, tag_ids))
            t_res = self.t_table.search().where(f"id IN ({tag_id_str})").to_list()
            names = [r["name"] for r in t_res]
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

    def _delete_helper(self, q_ids):
        """Helper to construct filter and delete from both tables for consistency."""
        if not q_ids:
            return
        # Ensure all are integers and build string for filter
        q_ids = [int(q_id) for q_id in q_ids]
        if len(q_ids) == 1:
            filter_str_qt = f"question_id = {q_ids[0]}"
            filter_str_q = f"id = {q_ids[0]}"
        else:
            id_list_str = ",".join(map(str, q_ids))
            filter_str_qt = f"question_id IN ({id_list_str})"
            filter_str_q = f"snowflake_id IN ({id_list_str})"

        # Note: LanceDB does not currently support multi-table ACID transactions in its
        # Python SDK for simple .delete() operations. We execute them sequentially.
        self.qt_table.delete(filter_str_qt)
        self.q_table.delete(filter_str_q)

    def delete_question(self, q_id):
        try:
            self._delete_helper([q_id])
        except Exception as e:
            logger.error(f"Error deleting question: {e}")

    def delete_questions(self, q_ids):
        try:
            self._delete_helper(q_ids)
        except Exception as e:
            logger.error(f"Error deleting questions: {e}")
