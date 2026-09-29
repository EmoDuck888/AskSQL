"""Schema graph operations for FalkorDB."""

import json
import logging
from typing import Any, Dict, List, Optional

from app.graphdb.client import get_falkordb

logger = logging.getLogger(__name__)


class SchemaGraphManager:
    """Manages database schema graphs in FalkorDB."""

    @staticmethod
    async def create_schema_graph(
        graph_id: str,
        entities: Dict[str, Any],
        relationships: Dict[str, List[Dict[str, str]]],
        db_name: str = "",
        db_url: str = "",
    ) -> None:
        """Create a schema graph in FalkorDB by delegating to graph_loader.

        Ensures embeddings and vector indexes are created so retrieval.py
        vector search works correctly.
        """
        # Collect FK columns so we can mark is_foreign_key correctly.
        fk_columns: set[tuple[str, str]] = set()
        for rel_list in relationships.values():
            for rel in rel_list:
                fk_columns.add((rel["from"], rel["source_column"]))

        tables: list[dict] = []
        for table_name, table_info in entities.items():
            columns: list[dict] = []
            for col_name, col_info in table_info.get("columns", {}).items():
                key = col_info.get("key", "NONE")
                is_pri = key in ("PRIMARY KEY", "PRI")
                is_fk = (table_name, col_name) in fk_columns
                columns.append({
                    "column_name": col_name,
                    "data_type": col_info.get("type", "unknown"),
                    "description": col_info.get("description", ""),
                    "is_primary_key": is_pri,
                    "is_foreign_key": is_fk,
                    "is_nullable": col_info.get("null", "YES") == "YES",
                    "sample_values": col_info.get("sample_values", []),
                })
            tables.append({
                "table_name": table_name,
                "description": table_info.get("description", f"Table: {table_name}"),
                "columns": columns,
            })

        relationships_list: list[dict] = []
        for rel_name, rel_list in relationships.items():
            for rel in rel_list:
                relationships_list.append({
                    "from": rel["from"],
                    "to": rel["to"],
                    "source_column": rel["source_column"],
                    "target_column": rel["target_column"],
                    "note": rel.get("note", ""),
                })

        from app.api.graph.graph_loader import load_schema_to_graph
        await load_schema_to_graph(
            graph_id=graph_id,
            db_name=db_name or graph_id,
            db_url=db_url,
            tables=tables,
            relationships=relationships_list,
        )

    @staticmethod
    async def get_schema_data(graph_id: str) -> Dict[str, Any]:
        """Get schema nodes and edges for visualization.

        Returns:
            Dictionary with 'nodes' and 'links' arrays.
        """
        falkordb = get_falkordb()
        graph = falkordb.select_graph(graph_id)

        # Get all tables with their columns
        result = await graph.query(
            """
            MATCH (t:Table)
            OPTIONAL MATCH (c:Column)-[:BELONGS_TO]->(t)
            RETURN t.name as name, collect({
                name: c.name,
                type: c.type,
                keyType: c.key_type,
                nullable: c.nullable
            }) as columns
            """
        )

        nodes = []
        node_id_map = {}
        for idx, row in enumerate(result.result_set):
            node_id = idx + 1
            node_id_map[row[0]] = node_id
            columns = [c for c in row[1] if c.get("name")]
            nodes.append({
                "id": str(node_id),
                "name": row[0],
                "columns": columns,
            })

        # Get all relationships
        rel_result = await graph.query(
            """
            MATCH (src:Column)-[:REFERENCES]->(tgt:Column)
            MATCH (src)-[:BELONGS_TO]->(st:Table)
            MATCH (tgt)-[:BELONGS_TO]->(tt:Table)
            RETURN st.name as source, tt.name as target
            """
        )

        links = []
        for row in rel_result.result_set:
            source_name = row[0]
            target_name = row[1]
            if source_name in node_id_map and target_name in node_id_map:
                links.append({
                    "source": node_id_map[source_name],
                    "target": node_id_map[target_name],
                })

        return {"nodes": nodes, "links": links}

    @staticmethod
    async def delete_schema_graph(graph_id: str) -> None:
        """Delete a schema graph."""
        falkordb = get_falkordb()
        try:
            graph = falkordb.select_graph(graph_id)
            await graph.delete()
        except Exception as e:
            logger.warning("Error deleting graph %s: %s", graph_id, e)

    @staticmethod
    async def list_graphs() -> List[str]:
        """List all graphs."""
        falkordb = get_falkordb()
        return await falkordb.list_graphs()
