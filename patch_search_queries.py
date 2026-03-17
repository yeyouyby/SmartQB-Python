import re

with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

# For search_questions we can't do LIKE easily in native LanceDB unless using fts, but LanceDB fts requires creating index which might not exist.
# Let's just keep the pandas search but we can optimize memory or at least leave it for now if full text search is not configured.
# We will optimize the search_questions to avoid loading qt_table and t_table if not kw, etc. Wait, it's already doing that.

# But we need to use where for the simple get question
search_question_new = """    def search_questions(self, kw):
        try:
            if not kw:
                q_df = self.q_table.to_pandas()
                if q_df.empty: return []
                q_df = q_df.sort_values(by="id", ascending=False)
                return [(int(r['id']), r['content']) for _, r in q_df.iterrows()]

            # We perform string match. We'll load the required columns only to save memory if possible
            q_df = self.q_table.to_pandas()
            if q_df.empty: return []

            t_df = self.t_table.to_pandas()
            qt_df = self.qt_table.to_pandas()

            content_matches = q_df[q_df['content'].str.contains(kw, case=False, na=False)]['id'].tolist()

            tag_matches = []
            if not t_df.empty and not qt_df.empty:
                matching_tags = t_df[t_df['name'].str.contains(kw, case=False, na=False)]['id'].tolist()
                if matching_tags:
                    tag_matches = qt_df[qt_df['tag_id'].isin(matching_tags)]['question_id'].tolist()

            all_matches = set(content_matches + tag_matches)

            if not all_matches: return []

            res_df = q_df[q_df['id'].isin(all_matches)].sort_values(by="id", ascending=False)
            return [(int(r['id']), r['content']) for _, r in res_df.iterrows()]
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []"""

content = re.sub(
    r"    def search_questions\(self, kw\):.*?\(\(int\(r\['id'\]\), r\['content'\]\) for _, r in res_df\.iterrows\(\)\]",
    search_question_new,
    content,
    flags=re.DOTALL
)

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
