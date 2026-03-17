import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# I noticed one last thing: gui_app.py's refresh_bag_ui still has `hasattr(self, 'listbox_bag')` which we can leave as is.
# But there is a missing `self.after(0, update_ui)` in merge_staging_items maybe? Or rather, `_merge_inflight` flag from codeant-ai.
# Let's fix the inflight race conditions as suggested by CodeAnt AI for merge, split, format, and save.

merge_pattern = r"(        def task\(\):\n            merged = self\.ai_service\.ai_merge_questions\(texts_to_merge\))"
merge_repl = r"""        def task():
            try:
                merged = self.ai_service.ai_merge_questions(texts_to_merge)"""
content = re.sub(merge_pattern, merge_repl, content)

merge_thread_pattern = r"(        threading\.Thread\(target=task, daemon=True\)\.start\(\))"
merge_thread_repl = r"""        def run_merge_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_merge_inflight", False))

        if getattr(self, "_merge_inflight", False):
            messagebox.showinfo("提示", "AI 合并正在进行，请稍候。")
            return
        self._merge_inflight = True
        threading.Thread(target=run_merge_task, daemon=True).start()"""
# Wait, merge_thread_repl requires careful replacement only around `merge_staging_items`. I'll do this safely.
