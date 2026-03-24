import sqlite3
import lancedb
import pyarrow as pa
import time
import os
import json
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class dbManager:
    def __init__(self, db_dir="smartqb_lancedb", sqlite_db="smartqb.db"):
        self.db_dir = db_dir
        self.sqlite_db = sqlite_db

        # Initialize SQLite
        self.conn = sqlite3.connect(self.sqlite_db)
        self.cursor = self.conn.cursor()
        self.init_sqlite()

        # Initialize LanceDB
        self.lance_db = lancedb.connect(self.db_dir)
        self.init_lancedb()

    def init_sqlite(self):
        # Settings table for encrypted API Keys
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        # Snowflake ID sequence state (handled in application logic, but stored for reference)
        # Assuming pure application-level Snowflake, but we need relations:
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS exam_bags (
                id INTEGER PRIMARY KEY,
                name TEXT,
                created_at INTEGER
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS exam_groups (
                id INTEGER PRIMARY KEY,
                bag_id INTEGER,
                name TEXT,
                sort_order INTEGER,
                FOREIGN KEY (bag_id) REFERENCES exam_bags(id)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS question_map (
                group_id INTEGER,
                question_id INTEGER,  -- Snowflake ID from LanceDB
                sort_order INTEGER,
                PRIMARY KEY (group_id, question_id),
                FOREIGN KEY (group_id) REFERENCES exam_groups(id)
            )
        ''')

        # SQLite FTS5 extension for BM25 Sparse Index
        # Virtual tables can't be DROPped or CREATEd IF NOT EXISTS safely in all SQLite versions,
        # but modern versions handle IF NOT EXISTS.
        self.cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_questions USING fts5(
                id UNINDEXED, -- Store Snowflake ID without indexing it
                content -- Store full Markdown text to be indexed
            )
        ''')
        self.conn.commit()

    def init_lancedb(self):
        # LanceDB setup for dense vectors
        schema = pa.schema([
            ("id", pa.int64()),
            ("vector", pa.list_(pa.float32(), 1536)),
            ("content_md", pa.string()),
            ("images", pa.string())  # JSON of base64 images
        ])
        if "questions" not in self.lance_db.table_names():
            self.lance_db.create_table("questions", schema=schema)

    def set_setting(self, key, value, master_key):
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        derived_key = kdf.derive(master_key.encode('utf-8'))
        aesgcm = AESGCM(derived_key)
        nonce = os.urandom(12)
        encrypted_value = aesgcm.encrypt(nonce, value.encode('utf-8'), None)

        # Store salt + nonce + encrypted payload
        payload = base64.b64encode(salt + nonce + encrypted_value).decode('utf-8')

        self.cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, payload))
        self.conn.commit()

    def get_setting(self, key, master_key):
        self.cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        if not row:
            return None

        payload = base64.b64decode(row[0].encode('utf-8'))
        salt = payload[:16]
        nonce = payload[16:28]
        encrypted_value = payload[28:]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        derived_key = kdf.derive(master_key.encode('utf-8'))
        aesgcm = AESGCM(derived_key)

        try:
            value = aesgcm.decrypt(nonce, encrypted_value, None)
            return value.decode('utf-8')
        except Exception:
            return None

    def close(self):
        self.conn.close()
