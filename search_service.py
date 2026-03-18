import json
import numpy as np
from config import DB_NAME
from utils import logger
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

        # LanceDB native vector search
        logger.info("Executing native LanceDB vector search...")
        results = table.search(query_vec).limit(limit).to_pandas()

        if results.empty:
            logger.info("No matching questions found in vector search.")
            return []

        ret = []
        for _, row in results.iterrows():
            sim = 1.0 - row['_distance'] if '_distance' in row else 0.0
            content = row['content']
            ret.append({
                "id": int(row['id']),
                "content": content[:100] if content else "",
                "similarity": float(sim)
            })

        logger.info(f"Vector search returned {len(ret)} results.")
        return ret
    except Exception as e:
        logger.error(f"LanceDB Search Error: {e}", exc_info=True)
        return []