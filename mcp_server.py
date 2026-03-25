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

    # Using strict whitelist of allowed tables for sql queries to be bulletproof
    allowed_tables = {"exam_bags", "exam_groups", "question_map", "fts_questions", "questions", "sqlite_sequence"}
    tables: set = set()
    for statement in sqlparse.parse(sql_string):
        _extract_tables(statement.tokens, tables)

    for table in tables:
        if table not in allowed_tables:
            return f"Error: Access to the '{table}' table is strictly forbidden. Allowed tables are: {', '.join(allowed_tables)}."
    return None

@mcp.tool()
def sqb_hybrid_search(query: str, limit: int = 5) -> str:
    """
    Search the question bank using hybrid search (BM25 + LanceDB Vector).
    Returns the top matching questions.
    """
    try:
        searcher = HybridSearcher(db_instance=get_db())
        results = searcher.search(query, limit)

        formatted_results = []
        for doc_id, score in results:
            formatted_results.append(f"Question ID: {doc_id}, Score: {score:.2f}")

        return "Search Results:\n" + "\n".join(formatted_results) if formatted_results else "No results found."
    except Exception as e:
        logger.error(f"Error executing search: {e}", exc_info=True)
        return f"Error executing search: {str(e)}"

@mcp.tool()
def sqb_sql_query(sql_string: str) -> str:
    """
    Execute a read-only SQL query against the SmartQB SQLite metadata database.
    Can be used to check exam_bags, exam_groups, or question_map.
    """
    validation_err = _validate_sql(sql_string)
    if validation_err:
        return validation_err

    db = get_db()
    with db._lock:
        try:
            # Enforce a maximum row limit for SELECT queries to protect the server.
            max_rows = 500

            # Normalize SQL
            sql_upper = sql_string.strip().upper()
            stripped_sql = sql_string.rstrip().rstrip(";")

            # Replace existing limit with max_rows using regex (handling LIMIT X OFFSET Y, LIMIT Y, X, etc)
            limit_pattern = r'(?i)\bLIMIT\s+\d+(?:\s*(?:OFFSET|,)\s*\d+)?'
            if re.search(limit_pattern, stripped_sql):
                bounded_sql = re.sub(limit_pattern, f'LIMIT {max_rows}', stripped_sql) + ";"
            else:
                bounded_sql = f"{stripped_sql} LIMIT {max_rows};"

            db.cursor.execute(bounded_sql)
            # Fetch up to max_rows + 1 to detect if truncation occurred
            rows = db.cursor.fetchmany(max_rows + 1)

            if not rows:
                return "Query executed successfully. 0 rows returned."

            note = ""
            if len(rows) > max_rows:
                rows = rows[:max_rows]
                note = f"\n\nNote: Result truncated to the first {max_rows} rows."

            return json.dumps(rows, ensure_ascii=False, indent=2) + note
        except sqlite3.Error as e:
            logger.error(f"Database error executing SQL: {e}", exc_info=True)
            return f"Database error: {str(e)}"

@mcp.tool()
def sqb_generate_exam_sa(target_score: int, target_difficulty: float) -> str:
    """
    Generate an exam using Simulated Annealing based on target constraints.
    """
    try:
        # Fetch real question pool from LanceDB
        db = get_db()
        pool = db.get_all_questions_for_sa()

        if not pool:
            return "Error: Database is empty. Cannot generate exam."

        builder = SimulatedAnnealingExamBuilder(pool, target_score, target_difficulty)
        best_state = builder.build_exam(initial_temp=50.0, max_iterations=500)

        selected_ids = [q["id"] for q in best_state]
        final_score = sum(q.get("score", 0) for q in best_state)
        final_diff = sum(q.get("difficulty", 0.5) for q in best_state) / len(best_state) if best_state else 0

        return f"Generated exam with {len(selected_ids)} questions.\nTotal Score: {final_score}, Average Difficulty: {final_diff:.2f}\nSelected IDs: {selected_ids}"
    except Exception as e:
        logger.error(f"Error generating exam: {e}", exc_info=True)
        return f"Error generating exam: {str(e)}"

@mcp.tool()
def sqb_export_paper(bag_id: int, template_name: str = "resources/templates/default.docx") -> str:
    """
    Export an exam bag to a Word document using the specified template.
    """
    # Prevent path traversal vulnerabilities by restricting to specific path
    app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
    templates_dir = os.path.join(app_root, "resources", "templates")

    base_name = os.path.basename(template_name)
    if not base_name.endswith('.docx'):
        base_name += '.docx'
    resolved_path = os.path.abspath(os.path.join(templates_dir, base_name))

    if not resolved_path.startswith(templates_dir):
        return "Error: Invalid template path."

    try:
        exporter = ExportService(template_path=resolved_path)

        # Fetch real exam bag markdown
        db = get_db()
        real_content = db.get_exam_bag_markdown(bag_id)
        if not real_content:
            return f"Error: Exam Bag with ID {bag_id} does not exist or could not be loaded."

        out_path = f"export_{bag_id}.docx"
        exporter.render_markdown_to_docx(real_content, out_path)
        return f"Successfully exported Exam Bag {bag_id} using template '{base_name}'. File saved to '{out_path}'."
    except ValueError as ve:
        return f"Export template error: {str(ve)}"
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return f"Export failed: {str(e)}"

if __name__ == "__main__":
    # Start the FastMCP server, exposing tools via stdio to Claude Desktop
    mcp.run(transport='stdio')
