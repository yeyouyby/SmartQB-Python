import db_manager
import sqlite3
import logging

logger = logging.getLogger(__name__)

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
        if ai_service and hasattr(ai_service, "expand_query"):
            query = ai_service.expand_query(query)

        # 1. Sparse Match (BM25 via FTS5)
        bm25_scores = []
        with self.db._lock:
            try:
                # Note: MATCH query string formatting is critical, simplistic for demo
                self.db.cursor.execute("""
                    SELECT id, bm25(fts_questions)
                    FROM fts_questions
                    WHERE fts_questions MATCH ?
                    ORDER BY bm25(fts_questions) LIMIT ?
                """, (query, limit))
                bm25_scores = self.db.cursor.fetchall()
            except Exception as e:
                # Check for standard FTS5 absence errors
                msg = str(e).lower()
                if isinstance(e, sqlite3.OperationalError) and ("no such table: fts_questions" in msg or "no such module: fts5" in msg):
                    bm25_scores = []
                    logger.warning(f"FTS5 not available or table missing, skipping sparse search: {msg}")
                else:
                    logger.error(f"FTS5 Sparse search failed unexpectedly: {msg}", exc_info=True)
                    raise

        # 2. Dense Match (Vector search via LanceDB)
        embedding = []
        if ai_service and hasattr(ai_service, "get_embedding"):
            # Use actual query embedding from AI service if provided
            try:
                embedding = ai_service.get_embedding(query)
            except Exception as e:
                logger.error(f"Error getting embedding from ai_service: {e}", exc_info=True)
                embedding = []

        vector_scores = []
        if embedding:
            # Normalize embedding dimension to match expected schema if needed
            if len(embedding) != 1536:
                if len(embedding) > 1536:
                    embedding = embedding[:1536]
                else:
                    embedding = list(embedding) + [0.0] * (1536 - len(embedding))

            try:
                table = self.db.lance_db.open_table("questions")
                res = table.search(embedding).limit(limit).to_list()
                vector_scores = [(item["id"], item["_distance"]) for item in res]
            except Exception as e:
                logger.error(f"LanceDB Dense Vector search failed: {e}", exc_info=True)

        # 3. Combine with RRF
        fused = self.reciprocal_rank_fusion(bm25_scores, vector_scores)

        # Enforce exact limit as RRF union may yield up to 2 * limit entries
        return fused[:limit]
