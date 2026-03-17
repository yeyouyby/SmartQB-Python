import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

delete_method = """
    def delete_lib_question(self):
        sel = self.tree_lib.selection()
        if not sel: return
        selected_ids = [self.tree_lib.item(item)["values"][0] for item in sel]
        if messagebox.askyesno("危险操作", f"确定要彻底删除选中的 {len(selected_ids)} 道题目吗？不可恢复！"):
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            for q_id in selected_ids:
                adapter.delete_question(q_id)

            selected_id_set = set(selected_ids)
            self.export_bag = [q for q in self.export_bag if q["id"] not in selected_id_set]

            self.on_hard_search()
            self.txt_lib_det.delete("1.0", tk.END)
            self.ent_lib_tags.delete(0, tk.END)

            if getattr(self, 'current_lib_q_id', None) in selected_id_set:
                self.current_lib_q_id = None

            messagebox.showinfo("成功", "选中题目已彻底删除！")
"""

# Insert delete_lib_question right before add_to_bag
content = re.sub(
    r"(    def add_to_bag\(self\):)",
    delete_method + "\n" + r"\1",
    content
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
