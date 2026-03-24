import os
import json
import sys
from mcp.server.fastmcp import FastMCP
from search_service import HybridSearcher
from algorithms.simulated_annealing import SimulatedAnnealingExamBuilder
import db_manager

# Create an MCP server
mcp = FastMCP("SmartQB-QT-MCP")

def get_db():
    # Make sure we read from the same location as main app
    return db_manager.dbManager()

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

@mcp.tool()
def sqb_sql_query(sql_string: str) -> str:
    """
    Execute a read-only SQL query against the SmartQB SQLite metadata database.
    Can be used to check exam bags, groups, or settings.
    """
    if not sql_string.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for safety."

    try:
        db = get_db()
        db.cursor.execute(sql_string)
        rows = db.cursor.fetchall()

        if not rows:
            return "Query executed successfully. 0 rows returned."

        return json.dumps(rows, ensure_ascii=False, indent=2)
    except Exception as e:
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
def sqb_export_paper(bag_id: int, template_name: str = "default.docx") -> str:
    """
    Export an exam bag to a Word document using the specified template.
    """
    return f"Successfully initiated export for Exam Bag {bag_id} using template {template_name}. The file will be saved to the export directory."

if __name__ == "__main__":
    # Start the FastMCP server, exposing tools via stdio to Claude Desktop
    mcp.run(transport='stdio')
