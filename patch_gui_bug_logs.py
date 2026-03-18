import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix save_manual bug
old_save_manual = """
            if getattr(self, "_manual_save_inflight", False):
                messagebox.showinfo("提示", "正在入库，请勿重复提交。")
                return
            self._manual_save_inflight = True
            self.lbl_manual_status.config(text="正在入库...", foreground="blue")
            threading.Thread(target=bg_save, daemon=True).start()"""

new_save_manual = """
        if getattr(self, "_manual_save_inflight", False):
            messagebox.showinfo("提示", "正在入库，请勿重复提交。")
            return
        self._manual_save_inflight = True
        self.lbl_manual_status.config(text="正在入库...", foreground="blue")
        threading.Thread(target=bg_save, daemon=True).start()"""

content = content.replace(old_save_manual, new_save_manual)


# 2. Add lbl_lib_diagram to build_library_tab
lib_tab_search = """        self.ent_lib_tags = ttk.Entry(action_frame, width=30)
        self.ent_lib_tags.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="更新标签", command=self.update_lib_tags).pack(side=tk.LEFT)

        ttk.Button(action_frame, text="🛍️ 加入题目袋", command=self.add_to_bag).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="🗑️ 彻底删除", command=self.delete_lib_question).pack(side=tk.RIGHT)"""

lib_diagram_ui = """        self.ent_lib_tags = ttk.Entry(action_frame, width=30)
        self.ent_lib_tags.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="更新标签", command=self.update_lib_tags).pack(side=tk.LEFT)

        ttk.Button(action_frame, text="🛍️ 加入题目袋", command=self.add_to_bag).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="🗑️ 彻底删除", command=self.delete_lib_question).pack(side=tk.RIGHT)

        # New diagram UI missing from previous
        self.lbl_lib_diagram = ttk.Label(det_frame, text="无图样", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_lib_diagram.pack(fill=tk.BOTH, expand=True, pady=5)"""

content = content.replace(lib_tab_search, lib_diagram_ui)

# 3. Add more logging in gui_app.py
content = content.replace('print("正在加载 Pix2Text', 'logger.info("正在加载 Pix2Text')
content = content.replace('print("Pix2Text 引擎加载完成', 'logger.info("Pix2Text 引擎加载完成')
content = content.replace('print("正在加载 Surya', 'logger.info("正在加载 Surya')
content = content.replace('print("Surya Layout 引擎加载完成', 'logger.info("Surya Layout 引擎加载完成')
content = content.replace('print("警告: 无法导入 surya', 'logger.warning("警告: 无法导入 surya')
content = content.replace('print("Surya OCR 引擎加载完成', 'logger.info("Surya OCR 引擎加载完成')

# In save_staging_to_db
content = content.replace('self.update_status("正在检查 LaTeX 编译并准备入库...")', 'self.update_status("正在检查 LaTeX 编译并准备入库...")\n        logger.info("Starting LaTeX check and DB insertion for staged questions...")')
content = content.replace('messagebox.showinfo("成功", "已全部保存至题库！")', 'logger.info("All staged questions saved to DB successfully.")\n                    messagebox.showinfo("成功", "已全部保存至题库！")')

# In save_manual
content = content.replace('messagebox.showinfo("成功", "手工录入成功，已存入题库！")', 'logger.info("Manual question saved to DB successfully.")\n                    messagebox.showinfo("成功", "手工录入成功，已存入题库！")')

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
