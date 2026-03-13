# database.py
import sqlite3
from config import DB_NAME

# ==========================================
# 数据库定义与初始化
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    logic_descriptor TEXT,
                    difficulty REAL,
                    embedding_json TEXT,
                    diagram_base64 TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS question_tags (
                    question_id INTEGER,
                    tag_id INTEGER,
                    PRIMARY KEY (question_id, tag_id),
                    FOREIGN KEY(question_id) REFERENCES questions(id),
                    FOREIGN KEY(tag_id) REFERENCES tags(id)
                )''')
    try:
        c.execute("ALTER TABLE questions ADD COLUMN diagram_base64 TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()