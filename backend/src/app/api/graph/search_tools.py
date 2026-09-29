"""图检索工具（FalkorDB 图 + 向量），供 Agent 调用。"""

from app.api.graph.falkordb_client import FalkorDBClient
from app.api.graph.retrieval import find_relevant_schema

async def search_schema(user_query: str, graph_id: str = "", history: list[str] | None = None) -> dict:
    if not graph_id:
        graphs = await FalkorDBClient.list_graphs()
        if not graphs: return {"schema_text": "No database graph available", "tables": []}
        graph_id = graphs[0]
    return await find_relevant_schema(graph_id, user_query, history or [])

async def get_db_schema_ddl(graph_id: str) -> str:
    from app.api.graphs import get_graph_data
    data = await get_graph_data(graph_id)
    lines = []
    for node in data.get("nodes", []):
        lines.append(f"CREATE TABLE {node['name']} (")
        for col in node.get("columns", []):
            nullable = "NOT NULL" if col.get("nullable") == "False" else ""
            pk = "PRIMARY KEY" if col.get("keyType") == "PRI" else ""
            parts = [col.get("columnName", "?"), col.get("dataType", "TEXT"), nullable, pk]
            lines.append("  " + " ".join(p for p in parts if p).rstrip() + ",")
        lines.append(");\n")
    return "\n".join(lines)

async def get_join_paths(graph_id: str, table1: str, table2: str) -> list[dict]:
    g = FalkorDBClient.select_graph(graph_id)
    r = await g.query("""MATCH p=allShortestPaths((:Table {name:$t1})-[*..4]-(:Table {name:$t2}))
       RETURN [n IN nodes(p) WHERE 'Table' IN labels(n) | n.name] AS path, length(p) AS depth
       ORDER BY depth LIMIT 3""", {"t1": table1, "t2": table2})
    return [{"path": row[0], "depth": row[1]} for row in r.result_set]