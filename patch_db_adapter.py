with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace initialization
old_init = """    def __init__(self, machine_id=None):
        self.db = get_db()

        if machine_id is None:
            mac_address = str(uuid.getnode())
            machine_id = zlib.crc32(mac_address.encode('utf-8')) % 1024"""

new_init = """    def __init__(self, machine_id=None):
        self.db = get_db()

        from settings_manager import SettingsManager
        self.settings = SettingsManager()
        self.embedding_dimension = int(getattr(self.settings, 'embedding_dimension', 1536) or 1536)

        if machine_id is None:
            mac_address = str(uuid.getnode())
            machine_id = zlib.crc32(mac_address.encode('utf-8')) % 1024"""

if old_init in content:
    content = content.replace(old_init, new_init)

old_table_creation = """            self.q_table = self.db.create_table(
                "questions",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("content", pa.string()),
                    pa.field("logic_descriptor", pa.string()),
                    pa.field("difficulty", pa.float64()),
                    pa.field("vector", pa.list_(pa.float32(), 1536)),
                    pa.field("diagram_base64", pa.string()),
                ]),
            )"""

new_table_creation = """            self.q_table = self.db.create_table(
                "questions",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("content", pa.string()),
                    pa.field("logic_descriptor", pa.string()),
                    pa.field("difficulty", pa.float64()),
                    pa.field("vector", pa.list_(pa.float32(), self.embedding_dimension)),
                    pa.field("diagram_base64", pa.string()),
                ]),
            )"""

if old_table_creation in content:
    content = content.replace(old_table_creation, new_table_creation)

# Replace insert logic
old_insert = """    def execute_insert_question(self, content, logic, vec, diagram_b64):
        if not vec:
            vec = [0.0] * 1536
        new_q_id = self.next_id()
        self.q_table.add([{
            "id": new_q_id,
            "content": content,
            "logic_descriptor": logic or "",
            "difficulty": 0.0,
            "vector": vec,
            "diagram_base64": diagram_b64 or ""
        }])
        return new_q_id"""

new_insert = """    def execute_insert_question(self, content, logic, vec, diagram_b64):
        if vec is None:
            vec = []
        vec = list(vec)

        # Pad or truncate the vector to match the embedding dimension
        if len(vec) < self.embedding_dimension:
            vec.extend([0.0] * (self.embedding_dimension - len(vec)))
        elif len(vec) > self.embedding_dimension:
            vec = vec[:self.embedding_dimension]

        new_q_id = self.next_id()
        self.q_table.add([{
            "id": new_q_id,
            "content": content,
            "logic_descriptor": logic or "",
            "difficulty": 0.0,
            "vector": vec,
            "diagram_base64": diagram_b64 or ""
        }])
        return new_q_id"""

if old_insert in content:
    content = content.replace(old_insert, new_insert)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
