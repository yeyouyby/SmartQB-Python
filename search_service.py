# search_service.py
import sqlite3
import json
import numpy as np
from config import DB_NAME

# ==========================================
# 辅助工具 (向量搜索)
# ==========================================

def vector_search_db(ai_service, query_text, limit=10):
    query_vec = ai_service.get_embedding(query_text)
    if not query_vec: return []
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, content, embedding_json FROM questions WHERE embedding_json IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    
    scored = []
    q_vec_np = np.array(query_vec)
    for r in rows:
        try:
            vec = np.array(json.loads(r[2]))
            if np.linalg.norm(q_vec_np) == 0 or np.linalg.norm(vec) == 0:
                continue
            sim = np.dot(q_vec_np, vec) / (np.linalg.norm(q_vec_np) * np.linalg.norm(vec))
            scored.append((sim, r[0], r[1]))
        except Exception:
            continue
        
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"id": r[1], "content": r[2][:100], "similarity": float(r[0])} for r in scored[:limit]]