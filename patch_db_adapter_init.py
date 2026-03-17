import re

with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

init_pattern = r"    def __init__\(self\):\n        self\.db = get_db\(\)\n        self\.q_table = self\.db\.open_table\(\"questions\"\)\n        self\.t_table = self\.db\.open_table\(\"tags\"\)\n        self\.qt_table = self\.db\.open_table\(\"question_tags\"\)"

new_init = """    def __init__(self):
        self.db = get_db()
        try:
            self.q_table = self.db.open_table("questions")
        except Exception:
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
        except Exception:
            self.t_table = self.db.create_table(
                "tags",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("name", pa.string()),
                ]),
            )

        try:
            self.qt_table = self.db.open_table("question_tags")
        except Exception:
            self.qt_table = self.db.create_table(
                "question_tags",
                schema=pa.schema([
                    pa.field("question_id", pa.int64()),
                    pa.field("tag_id", pa.int64()),
                ]),
            )"""

content = re.sub(init_pattern, new_init, content)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
