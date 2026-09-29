"""Graph management and NL2SQL query routes for FalkorDB schemas."""
import json
import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.graphdb.schema_graph import SchemaGraphManager
from app.api.graph.falkordb_client import FalkorDBClient
from app.graphdb.client import get_falkordb
from app.db.session import AsyncSessionLocal
from app.models.database import DBConnection
from sqlalchemy import select

# ---------------------------------------------------------------------------
# 共享件（原 query_engine.py，随传统查询页一并迁移至此）
# ---------------------------------------------------------------------------

# 流式事件分隔符
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"


async def get_user_rules(graph_id: str) -> str:
    """Return user-defined rules stored in the graph."""
    g = FalkorDBClient.select_graph(graph_id)
    r = await g.query("MATCH (d:Database) RETURN d.user_rules")
    if r.result_set and r.result_set[0][0]:
        return r.result_set[0][0]
    return ""


async def set_user_rules(graph_id: str, user_rules: str) -> None:
    """Store user-defined rules in the graph."""
    g = FalkorDBClient.select_graph(graph_id)
    await g.query(
        "MERGE (d:Database) SET d.user_rules = $user_rules",
        {"user_rules": user_rules},
    )

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Graphs & Databases"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class UserRulesRequest(BaseModel):
    user_rules: str


class NodeUpdateRequest(BaseModel):
    business_name: str | None = None
    synonyms: str | None = None
    enum_descriptions: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Existing graph-management endpoints
# ---------------------------------------------------------------------------

@router.get("/graphs", tags=["mcp_tool"])
async def list_graphs():
    """List all schema graphs registered in DBConnection.

    Returns only schema graphs (not memory graphs) with their connection names
    so the frontend can display human-friendly labels.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DBConnection).where(DBConnection.falkordb_graph_id.isnot(None))
            )
            connections = result.scalars().all()

            graphs = [
                {
                    "id": conn.falkordb_graph_id,
                    "name": conn.name,
                    "db_type": conn.db_type,
                    "connection_id": conn.id,
                }
                for conn in connections
            ]
            return JSONResponse(content=graphs)
    except Exception as e:
        logger.error("Error listing graphs: %s", e)
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.get("/graphs/{graph_id}/data", tags=["mcp_tool"])
async def get_graph_data(graph_id: str):
    """Return all nodes and edges for the specified database schema."""
    try:
        schema = await SchemaGraphManager.get_schema_data(graph_id)
        return JSONResponse(content=schema)
    except Exception as e:
        logger.error("Error getting graph data: %s", e)
        return JSONResponse(
            content={"error": "Failed to retrieve database schema"},
            status_code=500,
        )


@router.delete("/graphs/{graph_id}")
async def delete_graph(graph_id: str):
    """Delete the specified schema graph and clear its DBConnection reference."""
    try:
        await SchemaGraphManager.delete_schema_graph(graph_id)

        # Also clear falkordb_graph_id from DBConnection so the graph no longer
        # appears in the list.
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(DBConnection).where(DBConnection.falkordb_graph_id == graph_id)
            )
            conn = result.scalar_one_or_none()
            if conn:
                conn.falkordb_graph_id = None
                conn.status = "pending"
                await session.commit()

        return JSONResponse(content={"success": True, "message": "Graph deleted"})
    except Exception as e:
        logger.error("Error deleting graph: %s", e)
        return JSONResponse(
            content={"error": "Failed to delete graph"},
            status_code=500,
        )


@router.get("/graphs/{graph_id}/schema-detail")
async def get_schema_detail(graph_id: str):
    """Return detailed schema nodes with semantic model attributes.

    Includes Table/Column business_name, synonyms, enum_descriptions.
    """
    try:
        falkordb = get_falkordb()
        graph = falkordb.select_graph(graph_id)

        result = await graph.query(
            """
            MATCH (t:Table)
            OPTIONAL MATCH (c:Column)-[:BELONGS_TO]->(t)
            RETURN t.name as table_name,
                   t.description as table_description,
                   t.business_name as table_business_name,
                   t.synonyms as table_synonyms,
                   collect({
                       name: c.name,
                       type: c.type,
                       description: c.description,
                       business_name: c.business_name,
                       synonyms: c.synonyms,
                       enum_descriptions: c.enum_descriptions,
                       key_type: c.key_type,
                       nullable: c.nullable
                   }) as columns
            ORDER BY t.name
            """
        )

        tables = []
        for row in result.result_set:
            cols = [
                {
                    "name": c["name"],
                    "type": c.get("type", ""),
                    "description": c.get("description", ""),
                    "business_name": c.get("business_name", ""),
                    "synonyms": c.get("synonyms", ""),
                    "enum_descriptions": c.get("enum_descriptions", ""),
                    "key_type": c.get("key_type", ""),
                    "nullable": c.get("nullable", ""),
                }
                for c in row[4]
                if c.get("name")
            ]
            tables.append({
                "name": row[0],
                "description": row[1] or "",
                "business_name": row[2] or "",
                "synonyms": row[3] or "",
                "columns": cols,
            })

        return JSONResponse(content={"tables": tables})
    except Exception as e:
        logger.error("Error getting schema detail: %s", e)
        return JSONResponse(
            content={"error": "Failed to retrieve schema detail"},
            status_code=500,
        )


@router.put("/graphs/{graph_id}/nodes/{node_type}/{node_name}")
async def update_node(graph_id: str, node_type: str, node_name: str, request: NodeUpdateRequest):
    """Update a Table or Column node with semantic model attributes.

    Re-generates embedding after property update so vector search reflects
    business names and synonyms.
    """
    if node_type not in ("Table", "Column"):
        raise HTTPException(status_code=400, detail="node_type must be 'Table' or 'Column'")

    try:
        from app.api.embeddings import get_embedding_backend
        backend = get_embedding_backend()
        falkordb = get_falkordb()
        graph = falkordb.select_graph(graph_id)

        # Build update Cypher
        set_clauses = []
        params: dict[str, Any] = {"name": node_name}

        if request.business_name is not None:
            set_clauses.append("n.business_name = $business_name")
            params["business_name"] = request.business_name
        if request.synonyms is not None:
            set_clauses.append("n.synonyms = $synonyms")
            params["synonyms"] = request.synonyms
        if request.enum_descriptions is not None:
            set_clauses.append("n.enum_descriptions = $enum_descriptions")
            params["enum_descriptions"] = request.enum_descriptions
        if request.description is not None:
            set_clauses.append("n.description = $description")
            params["description"] = request.description

        if not set_clauses:
            return JSONResponse(content={"success": True, "message": "No changes"})

        set_clauses.append("n.updated_at = timestamp()")

        await graph.query(
            f"""MATCH (n:{node_type} {{name: $name}}) SET {', '.join(set_clauses)}""",
            params,
        )

        # Re-generate embedding
        if node_type == "Table":
            desc = f"Table: {node_name}."
            if request.business_name:
                desc += f" Business name: {request.business_name}."
            if request.synonyms:
                desc += f" Synonyms: {request.synonyms}."
            if request.description:
                desc += f" Description: {request.description}."
            embedding = backend.embed([desc])
            await graph.query(
                "MATCH (n:Table {name: $name}) SET n.embedding = vecf32($e)",
                {"name": node_name, "e": embedding[0]},
            )
        else:
            # For Column, need table_name for context
            res = await graph.query(
                "MATCH (n:Column {name: $name})-[:BELONGS_TO]->(t:Table) RETURN t.name, n.type, n.description",
                {"name": node_name},
            )
            if res.result_set:
                table_name, col_type, col_desc = res.result_set[0]
            else:
                table_name, col_type, col_desc = "", "unknown", ""
            desc = f"Column: {table_name}.{node_name}. Type: {col_type or 'unknown'}."
            if request.business_name:
                desc += f" Business name: {request.business_name}."
            if request.synonyms:
                desc += f" Synonyms: {request.synonyms}."
            if request.description:
                desc += f" Description: {request.description}."
            embedding = backend.embed([desc])
            await graph.query(
                "MATCH (n:Column {name: $name}) SET n.embedding = vecf32($e)",
                {"name": node_name, "e": embedding[0]},
            )

        return JSONResponse(content={"success": True, "message": "Node updated"})
    except Exception as e:
        logger.error("Error updating node: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graphs/{graph_id}/refresh")
async def refresh_schema(graph_id: str):
    """Refresh schema from the underlying database.

    TODO: Trigger loader re-run for the graph's source DB.
    For now returns a streaming placeholder.
    """
    async def generate():
        yield json.dumps(
            {"type": "reasoning_step", "message": "Starting schema refresh..."},
            ensure_ascii=False,
        ) + MESSAGE_DELIMITER

        # In a full implementation, look up the DBConnection by graph_id
        # and re-run the appropriate loader.
        yield json.dumps(
            {
                "type": "schema_refresh",
                "message": "Schema refresh scheduled (not yet implemented).",
                "success": True,
            },
            ensure_ascii=False,
        ) + MESSAGE_DELIMITER

    return StreamingResponse(generate(), media_type="application/json")


# ---------------------------------------------------------------------------
# Memory graph visualization endpoint
# ---------------------------------------------------------------------------

@router.get("/graphs/{graph_id}/memory", tags=["mcp_tool"])
async def get_memory_graph_data(graph_id: str):
    """Return memory graph nodes and edges for visualization.

    Queries the Graphiti-backed memory graph (database name = group_id) and
    returns Entity, Query, Episodic nodes and their relationships.
    """
    try:
        user_id = "default"
        group_id = f"{user_id}_{graph_id}"
        # Graphiti uses group_id as the FalkorDB database name.
        memory_db_name = group_id

        graph = FalkorDBClient.select_graph(memory_db_name)

        # Get all nodes belonging to this group
        nodes_result = await graph.query(
            """
            MATCH (n)
            WHERE n.group_id = $group_id
               OR n.group_id IS NULL
               OR n.group_id = '_'
            RETURN
                id(n) as node_id,
                labels(n) as labels,
                properties(n) as props
            """,
            {"group_id": group_id},
        )

        nodes = []
        node_ids = set()
        for row in nodes_result.result_set:
            internal_id = row[0]
            labels = row[1] or []
            props = row[2] or {}
            node_ids.add(internal_id)

            label_set = set(labels)
            if "Query" in label_set:
                node_type = "query"
                display_name = props.get("question", "Query")
                if len(display_name) > 40:
                    display_name = display_name[:40] + "..."
            elif "Episodic" in label_set:
                node_type = "episode"
                display_name = props.get("name", "Episode")
                if len(display_name) > 40:
                    display_name = display_name[:40] + "..."
            elif "Entity" in label_set:
                node_type = "entity"
                display_name = props.get("name", "Entity")
            else:
                node_type = (labels[0] if labels else "unknown").lower()
                display_name = props.get("name", node_type)

            # Sanitize properties: drop embeddings / large lists
            safe_props: dict[str, Any] = {}
            for k, v in props.items():
                if k in ("embeddings", "name_embedding", "embedding"):
                    continue
                if isinstance(v, list):
                    continue
                if isinstance(v, str) and len(v) > 200:
                    safe_props[k] = v[:200] + "..."
                else:
                    safe_props[k] = v

            nodes.append(
                {
                    "id": str(internal_id),
                    "name": display_name,
                    "type": node_type,
                    "labels": labels,
                    "properties": safe_props,
                }
            )

        if not node_ids:
            return JSONResponse(content={"nodes": [], "edges": []})

        # Get relationships between nodes in this subgraph
        edges_result = await graph.query(
            """
            MATCH (a)-[r]->(b)
            WHERE (a.group_id = $group_id OR a.group_id IS NULL OR a.group_id = '_')
              AND (b.group_id = $group_id OR b.group_id IS NULL OR b.group_id = '_')
            RETURN
                id(a) as source,
                id(b) as target,
                type(r) as rel_type,
                properties(r) as props
            """,
            {"group_id": group_id},
        )

        edges = []
        for row in edges_result.result_set:
            edges.append(
                {
                    "source": str(row[0]),
                    "target": str(row[1]),
                    "type": row[2],
                    "properties": row[3] or {},
                }
            )

        return JSONResponse(content={"nodes": nodes, "edges": edges})
    except Exception as e:
        logger.error("Error getting memory graph data: %s", e, exc_info=True)
        return JSONResponse(
            content={
                "error": "Failed to retrieve memory graph data",
                "details": str(e),
            },
            status_code=500,
        )


@router.delete("/graphs/{graph_id}/memory-nodes/{node_id}")
async def delete_memory_node(graph_id: str, node_id: str):
    """Delete a single node from the memory graph (Graphiti/FalkorDB).

    Only affects the memory graph (group_id = {user_id}_{graph_id}),
    never the schema graph.
    """
    try:
        user_id = "default"
        group_id = f"{user_id}_{graph_id}"
        memory_db_name = group_id

        graph = FalkorDBClient.select_graph(memory_db_name)

        # FalkorDB internal IDs are integers
        await graph.query(
            "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n",
            {"node_id": int(node_id)},
        )

        return JSONResponse(content={"success": True, "message": "Node deleted"})
    except Exception as e:
        logger.error("Error deleting memory node: %s", e, exc_info=True)
        return JSONResponse(
            content={"error": "Failed to delete memory node", "details": str(e)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# User rules endpoints
# ---------------------------------------------------------------------------

@router.get("/graphs/{graph_id}/user-rules")
async def read_user_rules(graph_id: str):
    """Get user-defined SQL rules for this graph."""
    try:
        rules = await get_user_rules(graph_id)
        return {"user_rules": rules}
    except Exception as e:
        logger.error("Error reading user rules: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/graphs/{graph_id}/user-rules")
async def update_user_rules(graph_id: str, request: UserRulesRequest):
    """Set user-defined SQL rules for this graph."""
    try:
        await set_user_rules(graph_id, request.user_rules)
        return {"success": True, "message": "User rules updated"}
    except Exception as e:
        logger.error("Error updating user rules: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
