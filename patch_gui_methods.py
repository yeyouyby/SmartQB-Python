import re

with open("missing_methods.py", "r", encoding="utf-8") as f:
    missing_methods = f.read()

# We need to adapt missing_methods to use LanceDBAdapter where it used sqlite3
missing_methods_patched = re.sub(
    r"        conn = sqlite3\.connect\(DB_NAME\); c = conn\.cursor\(\)\n        c\.execute\(\"SELECT content, diagram_base64 FROM questions WHERE id=\?\", \(self\.current_lib_q_id,\)\)\n        row = c\.fetchone\(\); conn\.close\(\)\n        if row:\n            self\.export_bag\.append\(\{\"id\": self\.current_lib_q_id, \"content\": row\[0\], \"diagram\": row\[1\]\}\)",
    r"""        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        content, diagram = adapter.get_question(self.current_lib_q_id)
        if content:
            self.export_bag.append({"id": self.current_lib_q_id, "content": content, "diagram": diagram})""",
    missing_methods
)

missing_methods_patched = re.sub(
    r"        conn = sqlite3\.connect\(DB_NAME\); c = conn\.cursor\(\)\n        for q_id in question_ids:\n            if any\(item\['id'\] == q_id for item in self\.export_bag\): continue\n            c\.execute\(\"SELECT content, diagram_base64 FROM questions WHERE id=\?\", \(q_id,\)\)\n            row = c\.fetchone\(\)\n            if row:\n                self\.export_bag\.append\(\{\"id\": q_id, \"content\": row\[0\], \"diagram\": row\[1\]\}\)\n                added \+= 1\n        conn\.close\(\)",
    r"""        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        for q_id in question_ids:
            if any(item['id'] == q_id for item in self.export_bag): continue
            content, diagram = adapter.get_question(q_id)
            if content:
                self.export_bag.append({"id": q_id, "content": content, "diagram": diagram})
                added += 1""",
    missing_methods_patched
)

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove the trailing 'if __name__ == "__main__": ...' to append missing methods before it
content = re.sub(
    r"if __name__ == \"__main__\":\n    app = SmartQBApp\(\)\n    app\.mainloop\(\)(.|\n)*",
    "",
    content
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content + "\n" + missing_methods_patched + "\n")
