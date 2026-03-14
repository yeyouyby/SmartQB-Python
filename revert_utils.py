with open("utils.py", "r", encoding="utf-8") as f:
    text = f.read()

# Make sure only one copy of utils.py content is there, remove duplication if present.
if text.count("import logging") > 2:
    pass # Wait, let's just make sure it looks fine.
