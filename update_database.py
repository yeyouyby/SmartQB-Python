import os

with open("database.py", "r", encoding="utf-8") as f:
    content = f.read()

new_content = content + """
import lancedb

def get_db():
    return lancedb.connect("smartqb_lancedb")
"""

with open("database.py", "w", encoding="utf-8") as f:
    f.write(new_content)
