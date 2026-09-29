"""Oracle loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class OracleLoader(BaseLoader):
    """Loader for Oracle databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT "{col_name}"
            FROM "{table_name}"
            WHERE "{col_name}" IS NOT NULL
            AND ROWNUM <= {sample_size}
        """
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall() if row[0] is not None]

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load Oracle schema into FalkorDB graph."""
        try:
            import oracledb

            # Expected: user=xxx;password=xxx;dsn=host:port/SID
            params = OracleLoader._parse_url(connection_url)
            conn = oracledb.connect(**params)
            cursor = conn.cursor()

            yield True, "Extracting table information..."
            entities = OracleLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = OracleLoader.extract_relationships(cursor)

            cursor.close()
            conn.close()

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_oracle"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name="oracle",
                db_url=connection_url,
            )

            yield True, f"Oracle schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading Oracle schema: %s", e)
            yield False, f"Failed to load Oracle database schema: {str(e)}"

    @staticmethod
    def _parse_url(connection_url: str) -> Dict[str, str]:
        """Parse Oracle connection parameters."""
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
            SELECT table_name, comments
            FROM user_tab_comments
            WHERE table_type = 'TABLE'
            ORDER BY table_name
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            table_comment = row[1] or ""
            columns_info = OracleLoader.extract_columns_info(cursor, table_name)

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
            SELECT
                col.column_name,
                col.data_type,
                col.nullable,
                col.data_default,
                comm.comments
            FROM user_tab_columns col
            LEFT JOIN user_col_comments comm
                ON col.table_name = comm.table_name
                AND col.column_name = comm.column_name
            WHERE col.table_name = :table_name
            ORDER BY col.column_id
        """, {"table_name": table_name.upper()})

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
            if is_nullable == "N":
                description_parts.append("(NOT NULL)")
            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            sample_values = OracleLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
            )

            columns_info[col_name] = {
                "type": data_type,
                "null": "NO" if is_nullable == "N" else "YES",
                "key": "NONE",
                "description": " ".join(description_parts),
                "default": str(column_default) if column_default is not None else None,
                "sample_values": sample_values,
            }

        return columns_info

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        cursor.execute("""
            SELECT
                uc.constraint_name,
                uc.table_name,
                ucc.column_name,
                ruc.table_name AS referenced_table,
                rcc.column_name AS referenced_column
            FROM user_constraints uc
            JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name
            JOIN user_constraints ruc ON uc.r_constraint_name = ruc.constraint_name
            JOIN user_cons_columns rcc ON ruc.constraint_name = rcc.constraint_name
                AND ucc.position = rcc.position
            WHERE uc.constraint_type = 'R'
        """)

        relationships = {}
        for row in cursor.fetchall():
            constraint_name = row[0]
            if constraint_name not in relationships:
                relationships[constraint_name] = []
            relationships[constraint_name].append({
                "from": row[1],
                "to": row[3],
                "source_column": row[2],
                "target_column": row[4],
                "note": f"Foreign key: {constraint_name}",
            })

        return relationships
