"""Schema retrieval tools for the NL2SQL agent.

Wraps FalkorDB vector-search + graph-traversal retrieval as LangChain tools
so the agent can discover relevant tables/columns on demand.
"""
from __future__ import annotations

from langchain_core.tools import tool

from app.api.graph.retrieval import find_relevant_schema
from app.api.graph.falkordb_client import FalkorDBClient


@tool
async def find_relevant_schema_tool(user_query: str, graph_id: str = "") -> dict:
    """Find relevant tables and columns for a natural-language query.

    Performs LLM-mediated retrieval against the FalkorDB schema graph:
      1. Uses an LLM to generate semantic descriptions of target tables/columns.
      2. Vector-searches Table and Column embeddings in FalkorDB.
      3. Graph-traverses foreign-key relationships and shortest paths to expand
         the result set.

    Use this tool in Phase 1 / Step 1 when you need to discover which database
    schema elements are relevant to the user's question.  The returned
    ``schema_text`` can be fed directly into the Schema Linking / Query Plan
    steps.

    Args:
        user_query: The natural-language question to find schema for.
        graph_id:   Optional FalkorDB graph identifier.  When empty, the first
                    graph that actually contains Table nodes is used automatically
                    (memory graphs are skipped).

    Returns:
        A dictionary with keys:
        - ``tables``:        list of relevant table names
        - ``schema_text``:   human-readable schema description (ready for prompt injection)
        - ``table_count``:   number of tables found
        - ``query_method``:  always "llm_mediated_retrieval"
    """
    if not graph_id:
        graphs = await FalkorDBClient.list_graphs()
        if not graphs:
            return {
                "schema_text": "No database graph available. Please connect a database first.",
                "tables": [],
                "table_count": 0,
                "query_method": "llm_mediated_retrieval",
            }
        # 逐个查找第一个包含 Table 节点的 schema 图。
        # 不能无脑取 graphs[0]：list_graphs 按名字排序，记忆图谱
        # （如 default_xxx，存 Entity/Episodic 等记忆节点）可能排在最前，
        # 对它跑 schema 向量检索会直接报 "Attempted to access undefined attribute"。
        graph_id = ""
        for gid in graphs:
            try:
                g = FalkorDBClient.select_graph(gid)
                r = await g.query("MATCH (t:Table) RETURN count(t) LIMIT 1")
                if r.result_set and r.result_set[0][0] > 0:
                    graph_id = gid
                    break
            except Exception:
                continue
        if not graph_id:
            return {
                "schema_text": "No schema graph (with tables) available. Please connect a database and run schema discovery first.",
                "tables": [],
                "table_count": 0,
                "query_method": "llm_mediated_retrieval",
            }

    result = await find_relevant_schema(graph_id, user_query)
    return result


@tool
async def get_graph_list_tool() -> dict:
    """List all available FalkorDB schema graphs.

    Returns:
        Dictionary with ``graphs``: list of graph IDs.
    """
    graphs = await FalkorDBClient.list_graphs()
    return {"graphs": graphs}
