import json
import numpy as np
from config import DB_NAME
from utils import logger
from db_adapter import LanceDBAdapter

# ==========================================
# 辅助工具 (向量搜索)
# ==========================================

def vector_search_db(ai_service, query_text, limit=10):
    query_vec = ai_service.get_embedding(query_text)
    if not query_vec: return []

    try:
        db = LanceDBAdapter()
        table = db.db.open_table("questions")

        # LanceDB native vector search
        results = table.search(query_vec).limit(limit).to_pandas()

        if results.empty:
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

        return ret
    except Exception as e:
        logger.error(f"LanceDB Search Error: {e}", exc_info=True)
        return []
