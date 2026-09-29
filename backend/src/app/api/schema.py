"""Schema management routes."""
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.database import DBConnection
from app.graphdb.client import get_falkordb

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Schema"])


@router.get("/schema/{connection_id}/discover")
async def discover_schema(connection_id: int):
    """Discover schema for a connection.

    TODO: Implement schema discovery using existing loaders.
    For now, returns a placeholder response.
    """
    return {"status": "pending", "message": "Schema discovery not yet implemented"}


@router.get("/schema/{connection_id}/metadata")
async def get_schema_metadata(connection_id: int):
    """Get schema metadata for a connection from its FalkorDB graph."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DBConnection).where(DBConnection.id == connection_id)
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise HTTPException(status_code=404, detail="Connection not found")
        if not conn.falkordb_graph_id:
            return []

    try:
        falkordb = get_falkordb()
        graph = falkordb.select_graph(conn.falkordb_graph_id)

        result = await graph.query(
            """
            MATCH (t:Table)
            OPTIONAL MATCH (c:Column)-[:BELONGS_TO]->(t)
            RETURN t.name as table_name,
                   t.description as description,
                   collect({
                       name: c.name,
                       data_type: c.type,
                       description: c.description,
                       key_type: c.key_type,
                       nullable: c.nullable
                   }) as columns
            ORDER BY t.name
            """
        )

        tables = []
        for idx, row in enumerate(result.result_set):
            table_name = row[0]
            table_desc = row[1] or ""
            cols = row[2] or []

            columns = []
            for cidx, col in enumerate(cols):
                if not col.get("name"):
                    continue
                columns.append({
                    "id": cidx + 1,
                    "column_name": col["name"],
                    "data_type": col.get("data_type", "unknown"),
                    "description": col.get("description", ""),
                    "table_id": idx + 1,
                    "table_name": table_name,
                })

            tables.append({
                "id": idx + 1,
                "table_name": table_name,
                "description": table_desc,
                "columns": columns,
            })

        return tables
    except Exception as e:
        logger.error("Error getting schema metadata for connection %s: %s", connection_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schema/{connection_id}/publish")
async def publish_schema(connection_id: int, data: dict):
    """Publish schema for a connection.

    TODO: Implement schema publishing.
    """
    return {"status": "pending", "message": "Schema publish not yet implemented"}
