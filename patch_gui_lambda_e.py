import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace `lambda: messagebox.showerror("错误", f"数据库保存失败: {e}")`
# with `lambda err=e: messagebox.showerror("错误", f"数据库保存失败: {err}")`
content = re.sub(
    r"lambda: messagebox\.showerror\(\"错误\", f\"数据库保存失败: {e}\"\)",
    r"lambda err=e: messagebox.showerror(\"错误\", f\"数据库保存失败: {err}\")",
    content
)

# Replace other occurrences of `e` in lambdas if there are any
# Find instances of `lambda: messagebox.showerror(..., ..., {e} ...)`
# We can do it broadly for messagebox calls containing {e} inside a lambda without err=e
content = re.sub(
    r"lambda: messagebox\.([a-z]+)\((.*?\s*f\".*?\{e\}.*?\")\)",
    r"lambda err=e: messagebox.\1(\2)".replace("{e}", "{err}"),
    content
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
