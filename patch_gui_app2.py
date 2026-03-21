import re
with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(r"r'\[\[\{ima_dont_del_(\d+_\d+)\}\]\]'", r"r'\[\[\{ima_dont_del_(\\d+_\\d+)\}\]\]'")

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
