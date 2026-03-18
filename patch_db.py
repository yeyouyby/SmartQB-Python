with open("db_adapter.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

# Add config import if missing
if "from config import DB_NAME" not in content:
    content = content.replace("import lancedb", "import lancedb\nfrom config import DB_NAME")

# Add connection logging
if "logger.info(\"Connected to LanceDB at\"" not in content:
    content = content.replace(
        "def get_db(): return lancedb.connect('smartqb_lancedb')",
        "def get_db():\n    logger.info(f\"Connecting to LanceDB database: 'smartqb_lancedb'\")\n    return lancedb.connect('smartqb_lancedb')"
    )

with open("db_adapter.py", "w", encoding="utf-8") as f:
    f.write(content)
