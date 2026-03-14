import sqlite3
import json
import numpy as np
from config import DB_NAME
from utils import logger
try:
    import torch
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# ==========================================
# 辅助工具 (向量搜索)
# ==========================================

def vector_search_db(ai_service, query_text, limit=10):
    query_vec = ai_service.get_embedding(query_text)
    if not query_vec: return []

    conn = None
    rows = []
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, content, embedding_json FROM questions WHERE embedding_json IS NOT NULL")
        rows = c.fetchall()
    except Exception as e:
        logger.error(f"Search DB Error: {e}")
        return []
    finally:
        if conn: conn.close()

    if not rows: return []

    ids = []
    contents = []
    vecs = []

    for r in rows:
        try:
            vec = json.loads(r[2])
            if len(vec) == 0: continue
            ids.append(r[0])
            contents.append(r[1])
            vecs.append(vec)
        except Exception as e:
            logger.warning(f"Vector parse error for id {r[0]}: {e}")
            continue

    if not vecs: return []

    scored = []

    if HAS_TORCH:
        try:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            q_tensor = torch.tensor(query_vec, dtype=torch.float32).unsqueeze(0).to(device)
            db_tensor = torch.tensor(vecs, dtype=torch.float32).to(device)

            sims = F.cosine_similarity(q_tensor, db_tensor).cpu().numpy()
            for i, sim in enumerate(sims):
                scored.append((float(sim), ids[i], contents[i]))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [{"id": r[1], "content": r[2][:100], "similarity": float(r[0])} for r in scored[:limit]]
        except Exception as e:
            logger.error(f"Torch search error: {e}, fallback to numpy.")

    # Numpy fallback
    try:
        q_vec_np = np.array(query_vec)
        db_np = np.array(vecs)

        q_norm = np.linalg.norm(q_vec_np)
        db_norms = np.linalg.norm(db_np, axis=1)

        valid_idx = (q_norm > 0) & (db_norms > 0)

        if np.any(valid_idx):
            sims = np.dot(db_np[valid_idx], q_vec_np) / (q_norm * db_norms[valid_idx])
            valid_ids = np.array(ids)[valid_idx]
            valid_contents = np.array(contents)[valid_idx]

            for i, sim in enumerate(sims):
                scored.append((float(sim), valid_ids[i], valid_contents[i]))
    except Exception as e:
        logger.error(f"Numpy search error: {e}")
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"id": r[1], "content": r[2][:100], "similarity": float(r[0])} for r in scored[:limit]]
