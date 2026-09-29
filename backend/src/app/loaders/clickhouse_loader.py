"""ClickHouse loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class ClickHouseLoader(BaseLoader):
    """Loader for ClickHouse databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT `{col_name}`
            FROM `{table_name}`
            WHERE `{col_name}` IS NOT NULL
            LIMIT {sample_size};
        """
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall() if row[0] is not None]

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load ClickHouse schema into FalkorDB graph."""
        try:
            import clickhouse_connect

            # Parse URL: clickhouse://user:password@host:port/database
            params = ClickHouseLoader._parse_url(connection_url)
            client = clickhouse_connect.get_client(**params)
            cursor = client

            db_name = params.get("database", "")

            yield True, "Extracting table information..."
            entities = ClickHouseLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = ClickHouseLoader.extract_relationships(cursor)

            client.close()

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_{db_name}"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name=db_name,
                db_url=connection_url,
            )

            yield True, f"ClickHouse schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading ClickHouse schema: %s", e)
            yield False, f"Failed to load ClickHouse database schema: {str(e)}"

    @staticmethod
    def _parse_url(connection_url: str) -> Dict[str, Any]:
        """Parse ClickHouse connection URL."""
        from urllib.parse import urlparse, unquote
        parsed = urlparse(connection_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 8123,
            "username": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": parsed.path.lstrip("/") if parsed.path else "",
        }

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        result = cursor.query("""
            SELECT name, comment
            FROM system.tables
            WHERE database = currentDatabase()
            AND engine NOT IN ('View', 'MaterializedView')
            ORDER BY name;
        """)

        for row in result.result_rows:
            table_name = row[0]
            table_comment = row[1] or ""
            columns_info = ClickHouseLoader.extract_columns_info(cursor, table_name)

            entities[table_name] = {
                "description": table_comment if table_comment else f"Table: {table_name}",
                "columns": columns_info,
                "foreign_keys": [],
                "col_descriptions": [col_info["description"] for col_info in columns_info.values()],
            }

        return entities

    @staticmethod
    def extract_columns_info(cursor, table_name: str) -> Dict[str, Any]:
        """Extract column information."""
        result = cursor.query(f"""
            SELECT name, type, default_kind, default_expression, comment
            FROM system.columns
            WHERE database = currentDatabase()
            AND table = '{table_name}'
            ORDER BY position;
        """)

        columns_info = {}
        for row in result.result_rows:
            col_name = row[0]
            data_type = row[1]
            default_kind = row[2] or ""
            default_expr = row[3] or ""
            column_comment = row[4] or ""

            description_parts = []
            if column_comment:
                description_parts.append(column_comment)
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")

            sample_values = ClickHouseLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
            )

            columns_info[col_name] = {
                "type": data_type,
                "null": "YES",
                "key": "NONE",
                "description": " ".join(description_parts),
                "default": default_expr if default_expr else None,
                "sample_values": sample_values,
            }

        return columns_info

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        return {}
