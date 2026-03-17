import re

with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add from utils import logger at the top after from openai import OpenAI
content = re.sub(
    r"(from openai import OpenAI)",
    r"\1\nfrom utils import logger",
    content
)

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)
