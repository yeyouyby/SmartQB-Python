with open("gui_app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if line.strip() == "def on_hard_search(self):":
        new_lines.extend([
            "    def on_hard_search(self):\n",
            "        kw = self.ent_lib_search.get().strip()\n",
            "        from db_adapter import LanceDBAdapter\n",
            "        adapter = LanceDBAdapter()\n",
            "        rows = adapter.search_questions(kw)\n",
            "        for item in self.tree_lib.get_children():\n",
            "            self.tree_lib.delete(item)\n",
            "        for r in rows:\n",
            "            short_c = r[1][:30].replace('\\n', ' ')\n",
            "            self.tree_lib.insert('', 'end', values=(r[0], short_c))\n"
        ])
        skip = True
        continue

    if skip:
        if line.strip() == "def on_lib_select(self, event):":
            skip = False
        else:
            continue

    if line.strip() == "def update_lib_tags(self):":
        new_lines.extend([
            "    def update_lib_tags(self):\n",
            "        if getattr(self, 'current_lib_q_id', None) is None: return\n",
            "        new_tags = [t.strip() for t in self.ent_lib_tags.get().split(',') if t.strip()]\n",
            "        from db_adapter import LanceDBAdapter\n",
            "        adapter = LanceDBAdapter()\n",
            "        adapter.clear_question_tags(self.current_lib_q_id)\n",
            "        for tn in new_tags:\n",
            "            tid = adapter.execute_insert_tag(tn)\n",
            "            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)\n",
            "        messagebox.showinfo('提示', '标签更新成功！')\n"
        ])
        skip = True
        continue

    if skip:
        if line.strip() == "def delete_lib_question(self):":
            skip = False
        else:
            continue

    if line.strip() == "def delete_lib_question(self):":
        new_lines.extend([
            "    def delete_lib_question(self):\n",
            "        if getattr(self, 'current_lib_q_id', None) is None: return\n",
            "        if messagebox.askyesno('确认', '确定删除该题？'):\n",
            "            from db_adapter import LanceDBAdapter\n",
            "            adapter = LanceDBAdapter()\n",
            "            adapter.delete_question(self.current_lib_q_id)\n",
            "            self.txt_lib_det.delete('1.0', tk.END)\n",
            "            self.ent_lib_tags.delete(0, tk.END)\n",
            "            if hasattr(self, 'lbl_lib_diagram'):\n",
            "                self.lbl_lib_diagram.config(image='', text='无图样')\n",
            "            self.current_lib_q_id = None\n",
            "            self.on_hard_search()\n"
        ])
        skip = True
        continue

    if skip:
        if line.strip() == "def run_ai_chat(self):":
            skip = False
        else:
            continue

    if not skip:
        new_lines.append(line)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
