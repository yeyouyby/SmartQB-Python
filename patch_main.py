import pyarrow as pa
from db_adapter import LanceDBAdapter
from utils import logger

def ensure_lancedb_tables():
    logger.info("Initializing LanceDB database and verifying core tables...")
    adapter = LanceDBAdapter()
    db = adapter.db

    try:
        db.open_table("questions")
        logger.info("Table 'questions' found.")
    except Exception:
        logger.warning("Table 'questions' missing, creating it...", exc_info=True)
        db.create_table(
            "questions",
            schema=pa.schema([
                pa.field("id", pa.int64()),
                pa.field("content", pa.string()),
                pa.field("logic_descriptor", pa.string()),
                pa.field("difficulty", pa.float64()),
                pa.field("vector", pa.list_(pa.float32(), 1536)),
                pa.field("diagram_base64", pa.string()),
            ]),
        )

    try:
        db.open_table("tags")
        logger.info("Table 'tags' found.")
    except Exception:
        logger.warning("Table 'tags' missing, creating it...", exc_info=True)
        db.create_table(
            "tags",
            schema=pa.schema([
                pa.field("id", pa.int64()),
                pa.field("name", pa.string()),
            ]),
        )

    try:
        db.open_table("question_tags")
        logger.info("Table 'question_tags' found.")
    except Exception:
        logger.warning("Table 'question_tags' missing, creating it...", exc_info=True)
        db.create_table(
            "question_tags",
            schema=pa.schema([
                pa.field("question_id", pa.int64()),
                pa.field("tag_id", pa.int64()),
            ]),
        )
    logger.info("LanceDB initialization complete.")

if __name__ == "__main__":
    from gui_app import SmartQBApp
    ensure_lancedb_tables()
    logger.info("Starting GUI main loop...")
    app = SmartQBApp()
    app.mainloop()
    logger.info("SmartQB Pro V3 stopped.")
