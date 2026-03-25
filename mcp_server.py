import os
import json
import sys
import sqlite3
import re
import threading
import logging
import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Parenthesis
from sqlparse.tokens import Keyword, DML
from mcp.server.fastmcp import FastMCP
from pyside_app.search_service import HybridSearcher
from algorithms.simulated_annealing import SimulatedAnnealingExamBuilder
import db_manager
from pyside_app.export_service import ExportService

logger = logging.getLogger(__name__)

# Create an MCP server
mcp = FastMCP("SmartQB-QT-MCP")

# Keep a single instance per process
_db_instance = None
_db_lock = threading.Lock()

def get_db():
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = db_manager.dbManager()
    return _db_instance

def _extract_tables(tokens, tables: set):
    """Recursively extract all referenced table names from sqlparse token list."""
    from_seen = False
    for token in tokens:
        # Detect FROM / JOIN keywords (any variant)
        if token.ttype is Keyword and token.normalized.upper() in (
            'FROM', 'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN',
            'FULL JOIN', 'CROSS JOIN', 'LEFT OUTER JOIN', 'RIGHT OUTER JOIN'
        ):
            from_seen = True
            continue

        if from_seen:
            if isinstance(token, Identifier):
                name = token.get_real_name()
                if name:
                    tables.add(name.lower())
                # recurse into subqueries inside this identifier
                for sub in token.tokens:
                    if isinstance(sub, Parenthesis):
                        _extract_tables(sub.tokens, tables)
                from_seen = False

            elif isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    if isinstance(identifier, Identifier):
                        name = identifier.get_real_name()
                        if name:
                            tables.add(name.lower())
                from_seen = False

            elif isinstance(token, Parenthesis):
                # Subquery directly after FROM
                _extract_tables(token.tokens, tables)
                from_seen = False

        # Always recurse into compound tokens
        if hasattr(token, 'tokens'):
            _extract_tables(token.tokens, tables)

def _validate_sql(sql_string: str) -> str | None:
    """Returns an error string if the query is unsafe, else None."""
    if not sql_string.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for safety."

    forbidden = {"settings", "api_keys"}
    tables: set = set()
    for statement in sqlparse.parse(sql_string):
        _extract_tables(statement.tokens, tables)

    for table in tables:
        if table in forbidden:
            return f"Error: Access to the '{table}' table is strictly forbidden."
    return None

@mcp.tool()
def sqb_hybrid_search(query: str, limit: int = 5) -> str:
    """
    Search the question bank using hybrid search (BM25 + LanceDB Vector).
    Returns the top matching questions.
    """
    try:
        # Pass the global shared DB instance to prevent reconnect leaks
        searcher = HybridSearcher(db_instance=get_db())
        results = searcher.search(query, limit)

        # In a real impl, we'd fetch full markdown from LanceDB or SQLite
        # using the returned IDs. Here we simulate the return.
        formatted_results = []
        for doc_id, score in results:
            formatted_results.append(f"Question ID: {doc_id}, Score: {score:.2f}")

        return "Search Results:\n" + "\n".join(formatted_results) if formatted_results else "No results found."
    except Exception as e:
        logger.error(f"Error executing search: {e}", exc_info=True)
        return f"Error executing search: {str(e)}"
    # Do NOT close the db here because it's a shared singleton retrieved via get_db().

@mcp.tool()
def sqb_sql_query(sql_string: str) -> str:
    """
    Execute a read-only SQL query against the SmartQB SQLite metadata database.
    Can be used to check exam bags, groups, or settings.
    """
    validation_err = _validate_sql(sql_string)
    if validation_err:
        return validation_err

    db = get_db()
    with db._lock:
        try:
            # Enforce a maximum row limit for SELECT queries to protect the server.
            max_rows = 500
            bounded_sql = sql_string
            sql_upper = sql_string.strip().upper()

            if sql_upper.lstrip().startswith("SELECT") and " LIMIT " not in sql_upper:
                # Remove any trailing semicolon so we can safely append LIMIT.
                stripped_sql = sql_string.rstrip().rstrip(";")
                bounded_sql = f"{stripped_sql} LIMIT {max_rows};"

            db.cursor.execute(bounded_sql)
            rows = db.cursor.fetchall()

            if not rows:
                return "Query executed successfully. 0 rows returned."

            note = ""
            if sql_upper.lstrip().startswith("SELECT") and len(rows) >= max_rows:
                note = f"\n\nNote: Result truncated to the first {max_rows} rows."

            return json.dumps(rows, ensure_ascii=False, indent=2) + note
        except sqlite3.Error as e:
            logger.error(f"Database error executing SQL: {e}", exc_info=True)
            return f"Database error: {str(e)}"

@mcp.tool()
def sqb_generate_exam_sa(target_score: int, target_difficulty: float) -> str:
    """
    Generate an exam using Simulated Annealing based on target constraints.
    NOTE: Currently uses a mocked question pool for demonstration.
    """
    try:
        # Mocking question pool. In real impl, fetch from DB.
        pool = [{"id": i, "score": 5, "difficulty": 0.5 + (i%5)*0.1} for i in range(100)]

        builder = SimulatedAnnealingExamBuilder(pool, target_score, target_difficulty)
        best_state = builder.build_exam(initial_temp=50.0, max_iterations=500)

        selected_ids = [q["id"] for q in best_state]
        final_score = sum(q["score"] for q in best_state)
        final_diff = sum(q["difficulty"] for q in best_state) / len(best_state) if best_state else 0

        return f"[MOCK DATA WARNING] Generated mock exam with {len(selected_ids)} questions.\nTotal Score: {final_score}, Average Difficulty: {final_diff:.2f}\nSelected IDs: {selected_ids}"
    except Exception as e:
        logger.error(f"Error generating exam: {e}", exc_info=True)
        return f"Error generating exam: {str(e)}"

@mcp.tool()
def sqb_export_paper(bag_id: int, template_name: str = "resources/templates/default.docx") -> str:
    """
    Export an exam bag to a Word document using the specified template.
    """
    try:
        exporter = ExportService(template_path=template_name)
        # Assuming we fetch content markdown from LanceDB using bag_id.
        # Here we render a dummy content.
        mock_content = f"# Mock Exam Bag {bag_id}\n\nContent for {bag_id} generated via export service."
        out_path = f"export_{bag_id}.docx"
        exporter.render_markdown_to_docx(mock_content, out_path)
        return f"Successfully exported Exam Bag {bag_id} using template '{template_name}'. File saved to '{out_path}'."
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return f"Export failed: {str(e)}"

if __name__ == "__main__":
    # Start the FastMCP server, exposing tools via stdio to Claude Desktop
    mcp.run(transport='stdio')
