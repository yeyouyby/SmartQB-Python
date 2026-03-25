with open("gui_app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "); return" in line:
        indent = len(line) - len(line.lstrip())
        lines[i] = line.replace("); return", ")\n" + " " * indent + "return")

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
