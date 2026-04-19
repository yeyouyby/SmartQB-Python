import pyarrow as pa
from utils import logger, pad_or_truncate_vector
from db_adapter import LanceDBAdapter

# ==========================================
# 辅助工具 (向量搜索)
# ==========================================


def vector_search_db(ai_service, query_text, limit=10):
    logger.info(f"Starting vector search for query: '{query_text}' (limit={limit})")
    query_vec = ai_service.get_embedding(query_text)
    if not query_vec:
        logger.warning("Failed to generate embedding for vector search.")
        return []

    try:
        db = LanceDBAdapter()
        # Direct access to db.db.open_table was causing issues with unified adapter usage.
        # We now use db.q_table which handles the internal initialization.
        table = db.q_table

        if table is None:
            logger.error("LanceDB questions table is missing or failed to initialize.")
            return []

        # Pad or truncate the vector to match the table's vector dimension
        target_dim = db.embedding_dimension
        try:
            schema = table.schema
            if schema and "vector" in schema.names:
                vector_type = schema.field("vector").type
                if pa.types.is_fixed_size_list(vector_type):
                    target_dim = vector_type.list_size
        except Exception as e:
            logger.warning(
                f"Could not get target vector dimension from schema: {e}", exc_info=True
            )

        query_vec = pad_or_truncate_vector(query_vec, target_dim)

        # LanceDB native vector search
        logger.info("Executing native LanceDB vector search...")
        results = table.search(query_vec).limit(limit).to_list()

        if not results:
            logger.info("No matching questions found in vector search.")
            return []

        ret = []
        for row in results:
            sim = 1.0 - row["_distance"] if "_distance" in row else 0.0
            content = row["content_md"]
            ret.append(
                {
                    "id": int(row["snowflake_id"]),
                    "content": content[:100] if content else "",
                    "similarity": float(sim),
                }
            )

        logger.info(f"Vector search returned {len(ret)} results.")
        return ret
    except Exception as e:
        logger.error(f"LanceDB Search Error: {e}", exc_info=True)
        return []
