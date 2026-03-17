import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace on_hard_search sqlite queries with LanceDBAdapter
on_hard_search_pattern = r"    def on_hard_search\(self\):\n        kw = self\.ent_lib_search\.get\(\)\.strip\(\)\n        conn = sqlite3\.connect\(DB_NAME\); c = conn\.cursor\(\)\n        if kw:\n            c\.execute\(\"SELECT DISTINCT q\.id, q\.content FROM questions q LEFT JOIN question_tags qt ON q\.id = qt\.question_id LEFT JOIN tags t ON qt\.tag_id = t\.id WHERE q\.content LIKE \? OR t\.name LIKE \?\", \(f'%\{kw\}%', f'%\{kw\}%'\)\)\n        else:\n            c\.execute\(\"SELECT id, content FROM questions ORDER BY id DESC\"\)\n        rows = c\.fetchall\(\)\n        conn\.close\(\)\n\n        for item in self\.tree_lib\.get_children\(\):\n            self\.tree_lib\.delete\(item\)\n        for r in rows:\n            short_c = r\[1\]\[:30\]\.replace\(\"\\n\", \" \"\)\n            self\.tree_lib\.insert\(\"\", \"end\", values=\(r\[0\], short_c\)\)"

on_hard_search_new = """    def on_hard_search(self):
        kw = self.ent_lib_search.get().strip()
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        rows = adapter.search_questions(kw)

        for item in self.tree_lib.get_children():
            self.tree_lib.delete(item)
        for r in rows:
            short_c = r[1][:30].replace("\\n", " ")
            self.tree_lib.insert("", "end", values=(r[0], short_c))"""

content = re.sub(on_hard_search_pattern, on_hard_search_new, content)

# Replace update_lib_tags sqlite queries with LanceDBAdapter
update_lib_tags_pattern = r"    def update_lib_tags\(self\):\n        if self\.current_lib_q_id is None: return\n        new_tags = \[t\.strip\(\) for t in self\.ent_lib_tags\.get\(\)\.split\(','\) if t\.strip\(\)\]\n\n        conn = sqlite3\.connect\(DB_NAME\); c = conn\.cursor\(\)\n        c\.execute\(\"DELETE FROM question_tags WHERE question_id=\?\", \(self\.current_lib_q_id,\)\)\n\n        for tn in new_tags:\n            c\.execute\(\"SELECT id FROM tags WHERE name=\?\", \(tn,\)\)\n            row = c\.fetchone\(\)\n            if row:\n                tid = row\[0\]\n            else:\n                c\.execute\(\"INSERT INTO tags \(name\) VALUES \(\?\)\", \(tn,\)\)\n                tid = c\.lastrowid\n            c\.execute\(\"INSERT INTO question_tags \(question_id, tag_id\) VALUES \(\?, \?\)\", \(self\.current_lib_q_id, tid\)\)\n        conn\.commit\(\)\n        conn\.close\(\)\n        messagebox\.showinfo\(\"提示\", \"标签更新成功！\"\)"

update_lib_tags_new = """    def update_lib_tags(self):
        if self.current_lib_q_id is None: return
        new_tags = [t.strip() for t in self.ent_lib_tags.get().split(',') if t.strip()]

        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        adapter.clear_question_tags(self.current_lib_q_id)

        for tn in new_tags:
            tid = adapter.execute_insert_tag(tn)
            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)

        messagebox.showinfo("提示", "标签更新成功！")"""

content = re.sub(update_lib_tags_pattern, update_lib_tags_new, content)

# Replace delete_lib_question sqlite queries with LanceDBAdapter
delete_lib_question_pattern = r"    def delete_lib_question\(self\):\n        if self\.current_lib_q_id is None: return\n        if messagebox\.askyesno\(\"确认\", \"确定删除该题？\"\):\n            conn = sqlite3\.connect\(DB_NAME\); c = conn\.cursor\(\)\n            c\.execute\(\"DELETE FROM question_tags WHERE question_id=\?\", \(self\.current_lib_q_id,\)\)\n            c\.execute\(\"DELETE FROM questions WHERE id=\?\", \(self\.current_lib_q_id,\)\)\n            conn\.commit\(\)\n            conn\.close\(\)\n            self\.txt_lib_det\.delete\(\"1\.0\", tk\.END\)\n            self\.ent_lib_tags\.delete\(0, tk\.END\)\n            if hasattr\(self, 'lbl_lib_diagram'\):\n                self\.lbl_lib_diagram\.config\(image='', text=\"无图样\"\)\n            self\.current_lib_q_id = None\n            self\.on_hard_search\(\)"

delete_lib_question_new = """    def delete_lib_question(self):
        if self.current_lib_q_id is None: return
        if messagebox.askyesno("确认", "确定删除该题？"):
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            adapter.delete_question(self.current_lib_q_id)

            self.txt_lib_det.delete("1.0", tk.END)
            self.ent_lib_tags.delete(0, tk.END)
            if hasattr(self, 'lbl_lib_diagram'):
                self.lbl_lib_diagram.config(image='', text="无图样")
            self.current_lib_q_id = None
            self.on_hard_search()"""

content = re.sub(delete_lib_question_pattern, delete_lib_question_new, content)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
