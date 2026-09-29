"""DuckDB loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class DuckDBLoader(BaseLoader):
    """Loader for DuckDB databases."""

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
        """Load DuckDB schema into FalkorDB graph."""
        try:
            import duckdb

            db_path = connection_url if connection_url and connection_url != ":memory:" else ":memory:"
            conn = duckdb.connect(db_path)
            cursor = conn.cursor()

            yield True, "Extracting table information..."
            entities = DuckDBLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = DuckDBLoader.extract_relationships(cursor)

            cursor.close()
            conn.close()

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_{db_path.replace('/', '_').replace('\\', '_').replace(':', '_')}"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name=db_path,
                db_url=connection_url,
            )

            yield True, f"DuckDB schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading DuckDB schema: %s", e)
            yield False, f"Failed to load DuckDB database schema: {str(e)}"

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT table_name, table_comment
            FROM information_schema.tables
            WHERE table_schema = 'main'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            table_comment = row[1] or ""
            columns_info = DuckDBLoader.extract_columns_info(cursor, table_name)
            foreign_keys = DuckDBLoader.extract_foreign_keys(cursor, table_name)

            entities[table_name] = {
                "description": table_comment if table_comment else f"Table: {table_name}",
                "columns": columns_info,
                "foreign_keys": foreign_keys,
                "col_descriptions": [col_info["description"] for col_info in columns_info.values()],
            }

        return entities

    @staticmethod
    def extract_columns_info(cursor, table_name: str) -> Dict[str, Any]:
        """Extract column information."""
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position;
        """, (table_name,))

        columns_info = {}
        for col in cursor.fetchall():
            col_name = col[0]
            data_type = col[1]
            is_nullable = col[2]
            column_default = col[3]

            description_parts = [f"Column {col_name} of type {data_type}"]
            if is_nullable == "NO":
                description_parts.append("(NOT NULL)")
            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            sample_values = DuckDBLoader.extract_sample_values_for_column(
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
    def extract_foreign_keys(cursor, table_name: str) -> List[Dict[str, str]]:
        """Extract foreign key information."""
        # DuckDB supports foreign keys but doesn't expose them via information_schema easily
        # This is a basic implementation
        return []

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        # Basic implementation - DuckDB foreign key info is limited
        return {}
