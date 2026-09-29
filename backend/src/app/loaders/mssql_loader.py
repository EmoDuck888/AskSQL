"""MSSQL loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class MSSQLLoader(BaseLoader):
    """Loader for Microsoft SQL Server databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT TOP ({sample_size}) [{col_name}]
            FROM [{table_name}]
            WHERE [{col_name}] IS NOT NULL;
        """
        cursor.execute(query)
        return [row[0] for row in cursor.fetchall() if row[0] is not None]

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load MSSQL schema into FalkorDB graph."""
        try:
            import pyodbc

            conn = pyodbc.connect(connection_url)
            cursor = conn.cursor()

            yield True, "Extracting table information..."
            entities = MSSQLLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = MSSQLLoader.extract_relationships(cursor)

            cursor.close()
            conn.close()

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_mssql"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name="mssql",
                db_url=connection_url,
            )

            yield True, f"MSSQL schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading MSSQL schema: %s", e)
            yield False, f"Failed to load MSSQL database schema: {str(e)}"

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT TABLE_NAME, EP.value AS TableDescription
            FROM INFORMATION_SCHEMA.TABLES T
            LEFT JOIN sys.extended_properties EP
                ON EP.major_id = OBJECT_ID(T.TABLE_SCHEMA + '.' + T.TABLE_NAME)
                AND EP.minor_id = 0 AND EP.class = 1
            WHERE T.TABLE_TYPE = 'BASE TABLE'
            ORDER BY T.TABLE_NAME;
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            table_comment = row[1] or ""
            columns_info = MSSQLLoader.extract_columns_info(cursor, table_name)
            foreign_keys = MSSQLLoader.extract_foreign_keys(cursor, table_name)

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
            SELECT
                C.COLUMN_NAME, C.DATA_TYPE, C.IS_NULLABLE,
                C.COLUMN_DEFAULT,
                CASE WHEN PK.COLUMN_NAME IS NOT NULL THEN 'PRI' ELSE '' END AS COLUMN_KEY,
                EP.value AS ColumnComment
            FROM INFORMATION_SCHEMA.COLUMNS C
            LEFT JOIN (
                SELECT ku.COLUMN_NAME, ku.TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                    ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ) PK ON C.COLUMN_NAME = PK.COLUMN_NAME AND C.TABLE_NAME = PK.TABLE_NAME
            LEFT JOIN sys.extended_properties EP
                ON EP.major_id = OBJECT_ID(C.TABLE_SCHEMA + '.' + C.TABLE_NAME)
                AND EP.minor_id = C.ORDINAL_POSITION AND EP.class = 1
            WHERE C.TABLE_NAME = ?
            ORDER BY C.ORDINAL_POSITION;
        """, (table_name,))

        columns_info = {}
        for col in cursor.fetchall():
            col_name = col[0]
            data_type = col[1]
            is_nullable = col[2]
            column_default = col[3]
            column_key = col[4]
            column_comment = col[5] or ""

            key_type = "PRIMARY KEY" if column_key == "PRI" else "NONE"

            description_parts = []
            if column_comment:
                description_parts.append(column_comment)
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")
            if key_type != "NONE":
                description_parts.append(f"({key_type})")
            if is_nullable == "NO":
                description_parts.append("(NOT NULL)")
            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            sample_values = MSSQLLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
            )

            columns_info[col_name] = {
                "type": data_type,
                "null": is_nullable,
                "key": key_type,
                "description": " ".join(description_parts),
                "default": column_default,
                "sample_values": sample_values,
            }

        return columns_info

    @staticmethod
    def extract_foreign_keys(cursor, table_name: str) -> List[Dict[str, str]]:
        """Extract foreign key information."""
        cursor.execute("""
            SELECT
                fk.name AS constraint_name,
                c.name AS column_name,
                rt.name AS referenced_table,
                rc.name AS referenced_column
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns c ON fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id
            JOIN sys.tables pt ON fk.parent_object_id = pt.object_id
            JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
            JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
            WHERE pt.name = ?;
        """, (table_name,))

        foreign_keys = []
        for row in cursor.fetchall():
            foreign_keys.append({
                "constraint_name": row[0],
                "column": row[1],
                "referenced_table": row[2],
                "referenced_column": row[3],
            })
        return foreign_keys

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        cursor.execute("""
            SELECT
                fk.name AS constraint_name,
                pt.name AS table_name,
                c.name AS column_name,
                rt.name AS referenced_table,
                rc.name AS referenced_column
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns c ON fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id
            JOIN sys.tables pt ON fk.parent_object_id = pt.object_id
            JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
            JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id;
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
