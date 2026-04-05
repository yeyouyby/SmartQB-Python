import re

with open("gui/components/question_block.py", "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(r"^import os\n", "", content, flags=re.MULTILINE)

with open("gui/components/question_block.py", "w", encoding="utf-8") as f:
    f.write(content)
