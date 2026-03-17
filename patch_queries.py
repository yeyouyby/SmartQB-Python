import re

with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace get_all_tags using direct scanner if possible, or just keep to_pandas for now if we can't optimize easily since it's a small table.
# But for get_question, we can definitely use .search().where()
get_question_new = """    def get_question(self, q_id):
        try:
            q_id = int(q_id)
            res = self.q_table.search().where(f"id = {q_id}").limit(1).to_list()
            if not res:
                return None, None
            return res[0]['content'], res[0].get('diagram_base64', '')
        except Exception as e:
            logger.error(f"Error getting question: {e}")
            return None, None"""

content = re.sub(
    r"    def get_question\(self, q_id\):.*?return match\.iloc\[0\]\['content'\], match\.iloc\[0\]\.get\('diagram_base64', ''\)",
    get_question_new,
    content,
    flags=re.DOTALL
)


# get_question_tags type cast and use where
get_question_tags_new = """    def get_question_tags(self, q_id):
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
            return []"""

content = re.sub(
    r"    def get_question_tags\(self, q_id\):.*?return \[\(n,\) for n in names\]",
    get_question_tags_new,
    content,
    flags=re.DOTALL
)

# delete_question needs type cast
delete_question_new = """    def clear_question_tags(self, q_id):
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
            logger.error(f"Error deleting question: {e}")"""

content = re.sub(
    r"    def clear_question_tags\(self, q_id\):.*?self\.q_table\.delete\(f\"id = {q_id}\"\)",
    delete_question_new,
    content,
    flags=re.DOTALL
)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
