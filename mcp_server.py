import os
import json
import sys
import sqlite3
import re
from mcp.server.fastmcp import FastMCP
from pyside_app.search_service import HybridSearcher
from algorithms.simulated_annealing import SimulatedAnnealingExamBuilder
import db_manager
from pyside_app.export_service import ExportService

# Create an MCP server
mcp = FastMCP("SmartQB-QT-MCP")

# Keep a single instance per process
_db_instance = None

def get_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = db_manager.dbManager()
    return _db_instance

@mcp.tool()
def sqb_hybrid_search(query: str, limit: int = 5) -> str:
    """
    Search the question bank using hybrid search (BM25 + LanceDB Vector).
    Returns the top matching questions.
    """
    try:
        searcher = HybridSearcher()
        results = searcher.search(query, limit)

        # In a real impl, we'd fetch full markdown from LanceDB or SQLite
        # using the returned IDs. Here we simulate the return.
        formatted_results = []
        for doc_id, score in results:
            formatted_results.append(f"Question ID: {doc_id}, Score: {score:.2f}")

        return "Search Results:\n" + "\n".join(formatted_results) if formatted_results else "No results found."
    except Exception as e:
        return f"Error executing search: {str(e)}"
    finally:
        searcher.db.close()

@mcp.tool()
def sqb_sql_query(sql_string: str) -> str:
    """
    Execute a read-only SQL query against the SmartQB SQLite metadata database.
    Can be used to check exam bags, groups, or settings.
    """
    sql_upper = sql_string.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for safety."

    # Restrict to safe tables. Disallow settings/api_keys
    forbidden_tables = ["settings", "api_keys"]
    for ft in forbidden_tables:
        if ft.upper() in sql_upper:
            return f"Error: Access to the '{ft}' table is strictly forbidden."

    db = get_db()
    with db._lock:
        try:
            db.cursor.execute(sql_string)
            rows = db.cursor.fetchall()

            if not rows:
                return "Query executed successfully. 0 rows returned."

            return json.dumps(rows, ensure_ascii=False, indent=2)
        except sqlite3.Error as e:
            return f"Database error: {str(e)}"

@mcp.tool()
def sqb_generate_exam_sa(target_score: int, target_difficulty: float) -> str:
    """
    Generate an exam using Simulated Annealing based on target constraints.
    """
    try:
        # Mocking question pool. In real impl, fetch from DB.
        pool = [{"id": i, "score": 5, "difficulty": 0.5 + (i%5)*0.1} for i in range(100)]

        builder = SimulatedAnnealingExamBuilder(pool, target_score, target_difficulty)
        best_state = builder.build_exam(initial_temp=50.0, max_iterations=500)

        selected_ids = [q["id"] for q in best_state]
        final_score = sum(q["score"] for q in best_state)
        final_diff = sum(q["difficulty"] for q in best_state) / len(best_state) if best_state else 0

        return f"Generated exam with {len(selected_ids)} questions.\nTotal Score: {final_score}, Average Difficulty: {final_diff:.2f}\nSelected IDs: {selected_ids}"
    except Exception as e:
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
        return f"Export failed: {str(e)}"

if __name__ == "__main__":
    # Start the FastMCP server, exposing tools via stdio to Claude Desktop
    mcp.run(transport='stdio')
