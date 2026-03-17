import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace merge thread
content = re.sub(
    r"        def task\(\):\n            merged = self\.ai_service\.ai_merge_questions\(texts_to_merge\)(.*?)(            self\.after\(0, update_ui\)\n\n        threading\.Thread\(target=task, daemon=True\)\.start\(\))",
    r"""        def task():
            merged = self.ai_service.ai_merge_questions(texts_to_merge)\1            self.after(0, update_ui)

        def run_merge_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_merge_inflight", False))

        if getattr(self, "_merge_inflight", False):
            messagebox.showinfo("提示", "AI 合并正在进行，请稍候。")
            return
        self._merge_inflight = True
        threading.Thread(target=run_merge_task, daemon=True).start()""",
    content,
    flags=re.DOTALL
)

# Replace split thread
content = re.sub(
    r"        def task\(\):\n            splits = self\.ai_service\.ai_split_question\(text_to_split\)(.*?)(            self\.after\(0, update_ui\)\n\n        threading\.Thread\(target=task, daemon=True\)\.start\(\))",
    r"""        def task():
            splits = self.ai_service.ai_split_question(text_to_split)\1            self.after(0, update_ui)

        def run_split_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_split_inflight", False))

        if getattr(self, "_split_inflight", False):
            messagebox.showinfo("提示", "AI 拆分正在进行，请稍候。")
            return
        self._split_inflight = True
        threading.Thread(target=run_split_task, daemon=True).start()""",
    content,
    flags=re.DOTALL
)

# Replace format thread
content = re.sub(
    r"        def task\(\):\n            formatted = self\.ai_service\.ai_format_question\(text_to_format\)(.*?)(            self\.after\(0, update_ui\)\n\n        threading\.Thread\(target=task, daemon=True\)\.start\(\))",
    r"""        def task():
            formatted = self.ai_service.ai_format_question(text_to_format)\1            self.after(0, update_ui)

        def run_format_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_format_inflight", False))

        if getattr(self, "_format_inflight", False):
            messagebox.showinfo("提示", "AI 格式化正在进行，请稍候。")
            return
        self._format_inflight = True
        threading.Thread(target=run_format_task, daemon=True).start()""",
    content,
    flags=re.DOTALL
)

# Replace save staging thread
content = re.sub(
    r"        def task\(\):\n            to_db = \[\]\n            failed_indices = \[\]\n(.*?)        threading\.Thread\(target=task, daemon=True\)\.start\(\)",
    r"""        def task():
            to_db = []
            failed_indices = []\n\1
        def run_save_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_save_staging_inflight", False))

        if getattr(self, "_save_staging_inflight", False):
            messagebox.showinfo("提示", "正在入库，请勿重复提交。")
            return
        self._save_staging_inflight = True
        threading.Thread(target=run_save_task, daemon=True).start()""",
    content,
    flags=re.DOTALL
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
