from database import get_db
import pyarrow as pa
import logging
logger = logging.getLogger(__name__)
import json

class LanceDBAdapter:
    def __init__(self):
        self.db = get_db()
        self.q_table = self.db.open_table("questions")
        self.t_table = self.db.open_table("tags")
        self.qt_table = self.db.open_table("question_tags")

    def execute_insert_question(self, content, logic, vec, diagram_b64):
        if not vec: vec = [0.0] * 1536
        q_df = self.q_table.to_pandas()
        max_q_id = int(q_df['id'].max()) if not q_df.empty else 0
        new_q_id = max_q_id + 1
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
        t_df = self.t_table.to_pandas()
        if t_df.empty or tag_name not in t_df['name'].values:
            max_t_id = int(t_df['id'].max()) if not t_df.empty else 0
            new_t_id = max_t_id + 1
            self.t_table.add([{"id": new_t_id, "name": tag_name}])
            return new_t_id
        else:
            return int(t_df[t_df['name'] == tag_name].iloc[0]['id'])

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
        q_df = self.q_table.to_pandas()
        if q_df.empty: return None, None
        match = q_df[q_df['id'] == q_id]
        if match.empty: return None, None
        return match.iloc[0]['content'], match.iloc[0].get('diagram_base64', '')

    def get_question_tags(self, q_id):
        qt_df = self.qt_table.to_pandas()
        t_df = self.t_table.to_pandas()
        if qt_df.empty or t_df.empty: return []

        tag_ids = qt_df[qt_df['question_id'] == q_id]['tag_id'].tolist()
        if not tag_ids: return []

        names = t_df[t_df['id'].isin(tag_ids)]['name'].tolist()
        return [(n,) for n in names]

    def clear_question_tags(self, q_id):
        self.qt_table.delete(f"question_id = {q_id}")

    def delete_question(self, q_id):
        self.qt_table.delete(f"question_id = {q_id}")
        self.q_table.delete(f"id = {q_id}")
