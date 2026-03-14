import re

with open("document_service.py", "r", encoding="utf-8") as f:
    text = f.read()

# Fix literal newlines in list comprehensions and dictionaries
text = re.sub(r'\"text\": \"\n\s*\"\.', '"text": "\\\\n".', text)
text = re.sub(r'full_text = \"\n\"\.', 'full_text = "\\\\n".', text)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(text)
