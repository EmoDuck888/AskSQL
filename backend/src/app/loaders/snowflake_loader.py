"""Snowflake loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class SnowflakeLoader(BaseLoader):
    """Loader for Snowflake databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT "{col_name}"
            FROM "{table_name}"
            WHERE "{col_name}" IS NOT NULL
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
        """Load Snowflake schema into FalkorDB graph."""
        try:
            import snowflake.connector

            # Parse connection_url as JSON-like params or simple key=value pairs
            # Expected format: account=xxx;user=xxx;password=xxx;database=xxx
            params = SnowflakeLoader._parse_url(connection_url)
            conn = snowflake.connector.connect(**params)
            cursor = conn.cursor()

            db_name = params.get("database", "")

            yield True, "Extracting table information..."
            entities = SnowflakeLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = SnowflakeLoader.extract_relationships(cursor)

            cursor.close()
            conn.close()

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_{db_name}"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name=db_name,
                db_url=connection_url,
            )

            yield True, f"Snowflake schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading Snowflake schema: %s", e)
            yield False, f"Failed to load Snowflake database schema: {str(e)}"

    @staticmethod
    def _parse_url(connection_url: str) -> Dict[str, str]:
        """Parse Snowflake connection parameters from URL string."""
        params = {}
        for part in connection_url.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
        return params

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT TABLE_NAME, COMMENT
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME;
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            table_comment = row[1] or ""
            columns_info = SnowflakeLoader.extract_columns_info(cursor, table_name)

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
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION;
        """, (table_name,))

        columns_info = {}
        for col in cursor.fetchall():
            col_name = col[0]
            data_type = col[1]
            is_nullable = col[2]
            column_default = col[3]
            column_comment = col[4] or ""

            description_parts = []
            if column_comment:
                description_parts.append(column_comment)
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")
            if is_nullable == "NO":
                description_parts.append("(NOT NULL)")
            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            sample_values = SnowflakeLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
            )

            columns_info[col_name] = {
                "type": data_type,
                "null": is_nullable,
                "key": "NONE",
                "description": " ".join(description_parts),
                "default": column_default,
                "sample_values": sample_values,
            }

        return columns_info

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        # Snowflake foreign key info can be queried from INFORMATION_SCHEMA
        return {}
