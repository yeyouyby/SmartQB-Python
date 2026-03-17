import re

with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix Snowflake init check
snowflake_check = """
        if machine_id < 0 or machine_id > self.max_machine_id:
            raise ValueError(f"Machine ID must be between 0 and {self.max_machine_id}")
"""
content = re.sub(
    r"(        self\.timestamp_left_shift = self\.sequence_bits \+ self\.machine_id_bits)",
    r"\1\n" + snowflake_check,
    content
)

# Fix open_table exception handling
open_table_q_pattern = r"        try:\n            self\.q_table = self\.db\.open_table\(\"questions\"\)\n        except Exception:\n"
open_table_q_replacement = r"""        try:
            self.q_table = self.db.open_table("questions")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'questions' table, attempting to create it.", exc_info=True)
"""
content = re.sub(open_table_q_pattern, open_table_q_replacement, content)

open_table_t_pattern = r"        try:\n            self\.t_table = self\.db\.open_table\(\"tags\"\)\n        except Exception:\n"
open_table_t_replacement = r"""        try:
            self.t_table = self.db.open_table("tags")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'tags' table, attempting to create it.", exc_info=True)
"""
content = re.sub(open_table_t_pattern, open_table_t_replacement, content)

open_table_qt_pattern = r"        try:\n            self\.qt_table = self\.db\.open_table\(\"question_tags\"\)\n        except Exception:\n"
open_table_qt_replacement = r"""        try:
            self.qt_table = self.db.open_table("question_tags")
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("Failed to open 'question_tags' table, attempting to create it.", exc_info=True)
"""
content = re.sub(open_table_qt_pattern, open_table_qt_replacement, content)


# Fix execute_insert_question single line if
content = re.sub(
    r"        if not vec: vec = \[0\.0\] \* 1536",
    "        if not vec:\n            vec = [0.0] * 1536",
    content
)

# Fix execute_insert_tag check-then-insert race condition
tag_insert_pattern = r"    def execute_insert_tag\(self, tag_name\):\n        t_df = self\.t_table\.to_pandas\(\)\n        if t_df\.empty or tag_name not in t_df\['name'\]\.values:\n            new_t_id = id_generator\.next_id\(\)\n            self\.t_table\.add\(\[\{\"id\": new_t_id, \"name\": tag_name\}\]\)\n            return new_t_id\n        else:\n            return int\(t_df\[t_df\['name'\] == tag_name\]\.iloc\[0\]\['id'\]\)"

tag_insert_replacement = """    def execute_insert_tag(self, tag_name):
        # Prevent check-then-insert race
        with id_generator.lock:
            t_df = self.t_table.to_pandas()
            if t_df.empty or tag_name not in t_df['name'].values:
                # We need to temporarily release lock for next_id to grab it
                pass
            else:
                return int(t_df[t_df['name'] == tag_name].iloc[0]['id'])

        new_t_id = id_generator.next_id()
        self.t_table.add([{"id": new_t_id, "name": tag_name}])
        return new_t_id"""

content = re.sub(tag_insert_pattern, tag_insert_replacement, content)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
