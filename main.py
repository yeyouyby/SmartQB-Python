import pyarrow as pa
from db_adapter import LanceDBAdapter
from utils import logger
from gui_app import SmartQBApp

from settings_manager import SettingsManager\n\ndef ensure_lancedb_tables():
    logger.info("Initializing LanceDB database and verifying core tables...")
    try:
        adapter = LanceDBAdapter()
        db = adapter.db

        try:
            db.open_table("questions")
            logger.info("Table 'questions' found.")
        except Exception:
            logger.info("Table 'questions' missing, creating it...")
            db.create_table(
                "questions",
                schema=pa.schema([
                    pa.field("id", pa.int64()),
                    pa.field("content", pa.string()),
                    pa.field("logic_descriptor", pa.string()),
                    pa.field("difficulty", pa.float64()),
                    pa.field("vector", pa.list_(pa.float32(), getattr(SettingsManager(), 'embedding_dimension', 1024))),
                    pa.field("diagram_base64", pa.string()),
                ]),
            )

        try:
            db.open_table("tags")
            logger.info("Table 'tags' found.")
        except Exception:
            logger.info("Table 'tags' missing, creating it...")
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
            logger.info("Table 'question_tags' missing, creating it...")
            db.create_table(
                "question_tags",
                schema=pa.schema([
                    pa.field("question_id", pa.int64()),
                    pa.field("tag_id", pa.int64()),
                ]),
            )
        logger.info("LanceDB initialization complete.")
    except Exception as e:
        logger.error(f"Failed to initialize LanceDB tables: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    # 启动 GUI 主程序
    ensure_lancedb_tables()
    logger.info("Starting GUI main loop...")
    app = SmartQBApp()
    app.mainloop()
    logger.info("SmartQB Pro V3 stopped.")
