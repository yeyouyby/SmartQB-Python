import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the raw string syntax warning
content = content.replace("marker_pattern = re.compile(r'\\[\\[\\{ima_dont_del_(\\d+)\\}\\]\\]')", "marker_pattern = re.compile(r'\\[\\[\\{ima_dont_del_(\\d+)\\}\\]\\]')")

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
