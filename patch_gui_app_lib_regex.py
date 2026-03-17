import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# For on_hard_search, try to find it with simpler pattern
pattern_on_hard_search = r"    def on_hard_search\(self\):.*?            self\.tree_lib\.insert\(\"\", \"end\", values=\(r\[0\], short_c\)\)"

replacement_on_hard_search = """    def on_hard_search(self):
        kw = self.ent_lib_search.get().strip()
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        rows = adapter.search_questions(kw)

        for item in self.tree_lib.get_children():
            self.tree_lib.delete(item)
        for r in rows:
            short_c = r[1][:30].replace("\\n", " ")
            self.tree_lib.insert("", "end", values=(r[0], short_c))"""

content = re.sub(pattern_on_hard_search, replacement_on_hard_search, content, flags=re.DOTALL)


# For update_lib_tags
pattern_update_lib_tags = r"    def update_lib_tags\(self\):.*?        messagebox\.showinfo\(\"提示\", \"标签更新成功！\"\)"

replacement_update_lib_tags = """    def update_lib_tags(self):
        if getattr(self, "current_lib_q_id", None) is None: return
        new_tags = [t.strip() for t in self.ent_lib_tags.get().split(',') if t.strip()]

        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        adapter.clear_question_tags(self.current_lib_q_id)

        for tn in new_tags:
            tid = adapter.execute_insert_tag(tn)
            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)

        messagebox.showinfo("提示", "标签更新成功！")"""

content = re.sub(pattern_update_lib_tags, replacement_update_lib_tags, content, flags=re.DOTALL)


# For delete_lib_question
pattern_delete_lib_question = r"    def delete_lib_question\(self\):.*?            self\.current_lib_q_id = None\n            self\.on_hard_search\(\)"

replacement_delete_lib_question = """    def delete_lib_question(self):
        if getattr(self, "current_lib_q_id", None) is None: return
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

content = re.sub(pattern_delete_lib_question, replacement_delete_lib_question, content, flags=re.DOTALL)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
