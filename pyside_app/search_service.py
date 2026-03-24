import db_manager
import numpy as np

class HybridSearcher:
    def __init__(self, lancedb_dir="smartqb_lancedb", sqlite_db="smartqb.db"):
        self.db = db_manager.dbManager(lancedb_dir, sqlite_db)

    def reciprocal_rank_fusion(self, bm25_results, vector_results, k=60):
        # Calculate RRF score for both rank lists.
        # {id: score, ...}
        rrf_scores = {}

        # We assume bm25_results is [(id, score), ...]
        for rank, (doc_id, _) in enumerate(bm25_results, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

        for rank, (doc_id, _) in enumerate(vector_results, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

        # Sort by score descending
        fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return fused

    def search(self, query: str, limit: int = 10, ai_service=None):
        if ai_service:
            query = ai_service.expand_query(query)

        # 1. Sparse Match (BM25 via FTS5)
        bm25_scores = []
        try:
            # Note: MATCH query string formatting is critical, simplistic for demo
            self.db.cursor.execute("""
                SELECT id, bm25(fts_questions)
                FROM fts_questions
                WHERE fts_questions MATCH ?
                ORDER BY bm25(fts_questions) LIMIT ?
            """, (query, limit))
            bm25_scores = self.db.cursor.fetchall()
        except Exception:
            # Fallback if no full text search exists
            pass

        # 2. Dense Match (Vector search via LanceDB)
        # Assuming we have an embedder that takes the query and returns 1536 float32s
        mock_embedding = [0.1] * 1536
        vector_scores = []
        try:
            table = self.db.lance_db.open_table("questions")
            res = table.search(mock_embedding).limit(limit).to_list()
            vector_scores = [(item["id"], item["_distance"]) for item in res]
        except Exception:
            pass

        # 3. Combine with RRF
        return self.reciprocal_rank_fusion(bm25_scores, vector_scores)
