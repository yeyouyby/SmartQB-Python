import sqlite3
import lancedb
import pyarrow as pa
import os
import base64
import binascii
import threading
import logging
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

logger = logging.getLogger(__name__)


class dbManager:
    def __init__(self, db_dir="smartqb_lancedb", sqlite_db="smartqb.db"):
        self.db_dir = os.path.abspath(db_dir)
        self.sqlite_db = os.path.abspath(sqlite_db)
        self._lock = threading.RLock()

        # Initialize SQLite
        self.conn = sqlite3.connect(self.sqlite_db, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_sqlite()

        # Initialize LanceDB
        self.lance_db = lancedb.connect(self.db_dir)
        self.init_lancedb()

    def init_sqlite(self):
        with self._lock:
            # Settings table for encrypted API Keys
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Snowflake ID sequence state
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS exam_bags (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    created_at INTEGER
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS exam_groups (
                    id INTEGER PRIMARY KEY,
                    bag_id INTEGER,
                    name TEXT,
                    sort_order INTEGER,
                    FOREIGN KEY (bag_id) REFERENCES exam_bags(id)
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS question_map (
                    group_id INTEGER,
                    question_id INTEGER,  -- Snowflake ID from LanceDB
                    sort_order INTEGER,
                    PRIMARY KEY (group_id, question_id),
                    FOREIGN KEY (group_id) REFERENCES exam_groups(id)
                )
            """)

            # SQLite FTS5 extension for BM25 Sparse Index
            self.cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_questions USING fts5(
                    id UNINDEXED,
                    content
                )
            """)
            self.conn.commit()

    def init_lancedb(self):
        # LanceDB setup for dense vectors
        schema = pa.schema(
            [
                ("id", pa.int64()),
                ("vector", pa.list_(pa.float32(), 1536)),
                ("content_md", pa.string()),
                ("images", pa.string()),  # JSON of base64 images
                ("score", pa.int64()),
                ("difficulty", pa.float32()),
            ]
        )
        if "questions" not in self.lance_db.table_names():
            self.lance_db.create_table("questions", schema=schema)

    def set_setting(self, key, value, master_key):
        with self._lock:
            salt = os.urandom(16)
            iterations = 600000
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=iterations,
                backend=default_backend(),
            )
            derived_key = kdf.derive(master_key.encode("utf-8"))
            aesgcm = AESGCM(derived_key)
            nonce = os.urandom(12)
            encrypted_value = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

            # Prepend structured header for forward compatibility: version||kdf_id||iterations||salt||nonce||ciphertext
            header = f"v1:pbkdf2-sha256:{iterations}:".encode("utf-8")
            full_payload = header + salt + nonce + encrypted_value

            # Store base64 encoded payload
            encoded_payload = base64.b64encode(full_payload).decode("utf-8")

            self.cursor.execute(
                "REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, encoded_payload),
            )
            self.conn.commit()

    def get_setting(self, key, master_key):
        with self._lock:
            self.cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = self.cursor.fetchone()
            if not row:
                return None

        try:
            payload = base64.b64decode(row[0].encode("utf-8"))
        except (binascii.Error, ValueError) as e:
            logger.error(
                f"Failed to decrypt setting '{key}': Invalid base64 or length. Data might be corrupted. {e}"
            )
            return None

        # Parse structured header if present. Backward compatibility fallback.
        if payload.startswith(b"v1:"):
            parts = payload.split(b":", 3)
            if len(parts) == 4:
                version, kdf_id, iterations_str, remaining = parts
                try:
                    iterations = int(iterations_str)
                except ValueError:
                    logger.error(
                        f"Failed to decrypt setting '{key}': Malformed iteration count '{iterations_str.decode('utf-8', 'ignore')}'."
                    )
                    return None

                if kdf_id != b"pbkdf2-sha256":
                    logger.error(
                        f"Failed to decrypt setting '{key}': Unknown KDF '{kdf_id.decode('utf-8', 'ignore')}'."
                    )
                    return None
            else:
                logger.error(f"Failed to decrypt setting '{key}': Malformed header.")
                return None
        else:
            # Fallback for legacy items without header
            remaining = payload
            iterations = 600000

        # AES-GCM minimum remaining payload: 16 (salt) + 12 (nonce) + 16 (tag) = 44 bytes
        if len(remaining) < 44:
            logger.error(
                f"Failed to decrypt setting '{key}': Payload too short ({len(remaining)} bytes, need >= 44)."
            )
            return None

        salt = remaining[:16]
        nonce = remaining[16:28]
        encrypted_value = remaining[28:]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend(),
        )
        derived_key = kdf.derive(master_key.encode("utf-8"))
        aesgcm = AESGCM(derived_key)

        try:
            value = aesgcm.decrypt(nonce, encrypted_value, None)
            return value.decode("utf-8")
        except InvalidTag:
            logger.error(
                f"Failed to decrypt setting '{key}': Invalid auth tag. Data might be tampered or key is wrong."
            )
            return None
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode setting '{key}': {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error decrypting setting '{key}': {e}", exc_info=True
            )
            return None

    def get_all_questions_for_sa(self):
        """Fetch all questions from LanceDB as a pool for Simulated Annealing."""
        with self._lock:
            try:
                table = self.lance_db.open_table("questions")
                # Selecting specific columns to save memory if needed
                df = table.search().limit(10000).to_pandas()
                pool = []
                for _, row in df.iterrows():
                    pool.append(
                        {
                            "id": int(row["id"]),
                            "score": float(row.get("score", 5.0)),
                            "difficulty": float(row.get("difficulty", 0.5)),
                        }
                    )
                return pool
            except Exception as e:
                logger.error(f"Failed to load questions from LanceDB: {e}")
                return []

    def get_exam_bag_markdown(self, bag_id: int):
        """Retrieve full markdown content for a given exam bag."""
        with self._lock:
            self.cursor.execute("SELECT name FROM exam_bags WHERE id = ?", (bag_id,))
            bag = self.cursor.fetchone()
            if not bag:
                return None

            bag_name = bag[0]
            md_lines = [f"# {bag_name}\n"]

            self.cursor.execute(
                "SELECT id, name FROM exam_groups WHERE bag_id = ? ORDER BY sort_order",
                (bag_id,),
            )
            groups = self.cursor.fetchall()

            table = None
            try:
                table = self.lance_db.open_table("questions")
            except Exception as e:
                logger.warning(
                    f"Failed to open 'questions' table in LanceDB for bag {bag_id}: {e}",
                    exc_info=True,
                )

            for group_id, group_name in groups:
                md_lines.append(f"## {group_name}\n")

                self.cursor.execute(
                    "SELECT question_id FROM question_map WHERE group_id = ? ORDER BY sort_order",
                    (group_id,),
                )
                q_ids = [row[0] for row in self.cursor.fetchall()]

                if not q_ids:
                    continue

                if table:
                    id_filter = ", ".join(str(i) for i in q_ids)
                    try:
                        # LanceDB syntax: table.search().where(f"id IN ({id_filter})").to_list()
                        q_data = (
                            table.search()
                            .where(f"id IN ({id_filter})")
                            .limit(len(q_ids))
                            .to_list()
                        )
                        # Sort results back to order of q_ids
                        q_map = {
                            item["id"]: item.get(
                                "content_md", f"[Question {item['id']} content]"
                            )
                            for item in q_data
                        }
                        for index, qid in enumerate(q_ids, 1):
                            md_lines.append(
                                f"{index}. {q_map.get(qid, f'[Question {qid} missing]')}\n"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error fetching questions {q_ids} for group {group_id}: {e}"
                        )
                        for index, qid in enumerate(q_ids, 1):
                            md_lines.append(
                                f"{index}. [Question ID: {qid} could not be loaded]\n"
                            )
                else:
                    # Fallback placeholders when LanceDB is totally inaccessible
                    for index, qid in enumerate(q_ids, 1):
                        md_lines.append(
                            f"{index}. [Question ID: {qid} could not be loaded]\n"
                        )

            return "\n".join(md_lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        with self._lock:
            self.conn.close()
