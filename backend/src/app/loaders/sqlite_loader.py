"""SQLite loader for loading database schemas into FalkorDB graphs."""

import logging
import sqlite3
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class SQLiteLoader(BaseLoader):
    """Loader for SQLite databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT "{col_name}"
            FROM "{table_name}"
            WHERE "{col_name}" IS NOT NULL
            LIMIT ?;
        """
        cursor.execute(query, (sample_size,))
        return [row[0] for row in cursor.fetchall() if row[0] is not None]

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load SQLite schema into FalkorDB graph."""
        try:
            db_path = connection_url
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            yield True, "Extracting table information..."
            entities = SQLiteLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            relationships = SQLiteLoader.extract_relationships(cursor)

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

            yield True, f"SQLite schema loaded successfully. Found {len(entities)} tables."

        except sqlite3.Error as e:
            logger.error("SQLite connection error: %s", e)
            yield False, f"Failed to connect to SQLite database: {str(e)}"
        except Exception as e:
            logger.error("Error loading SQLite schema: %s", e)
            yield False, f"Failed to load SQLite database schema: {str(e)}"

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            columns_info = SQLiteLoader.extract_columns_info(cursor, table_name)
            foreign_keys = SQLiteLoader.extract_foreign_keys(cursor, table_name)

            entities[table_name] = {
                "description": f"Table: {table_name}",
                "columns": columns_info,
                "foreign_keys": foreign_keys,
                "col_descriptions": [col_info["description"] for col_info in columns_info.values()],
            }

        return entities

    @staticmethod
    def extract_columns_info(cursor, table_name: str) -> Dict[str, Any]:
        """Extract column information."""
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns_info = {}

        for col in cursor.fetchall():
            col_name = col[1]
            data_type = col[2]
            not_null = col[3]
            default_val = col[4]
            pk = col[5]

            key_type = "PRIMARY KEY" if pk else "NONE"

            description_parts = [f"Column {col_name} of type {data_type}"]
            if key_type != "NONE":
                description_parts.append(f"({key_type})")
            if not_null:
                description_parts.append("(NOT NULL)")
            if default_val is not None:
                description_parts.append(f"(Default: {default_val})")

            sample_values = SQLiteLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
            )

            columns_info[col_name] = {
                "type": data_type,
                "null": "NO" if not_null else "YES",
                "key": key_type,
                "description": " ".join(description_parts),
                "default": default_val,
                "sample_values": sample_values,
            }

        return columns_info

    @staticmethod
    def extract_foreign_keys(cursor, table_name: str) -> List[Dict[str, str]]:
        """Extract foreign key information."""
        cursor.execute(f'PRAGMA foreign_key_list("{table_name}")')
        foreign_keys = []
        for fk in cursor.fetchall():
            foreign_keys.append({
                "constraint_name": f"fk_{table_name}_{fk[3]}",
                "column": fk[3],
                "referenced_table": fk[2],
                "referenced_column": fk[4],
            })
        return foreign_keys

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        relationships = {}

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
        """)

        for row in cursor.fetchall():
            table_name = row[0]
            cursor.execute(f'PRAGMA foreign_key_list("{table_name}")')
            for fk in cursor.fetchall():
                constraint_name = f"fk_{table_name}_{fk[3]}"
                if constraint_name not in relationships:
                    relationships[constraint_name] = []
                relationships[constraint_name].append({
                    "from": table_name,
                    "to": fk[2],
                    "source_column": fk[3],
                    "target_column": fk[4],
                    "note": f"Foreign key: {constraint_name}",
                })

        return relationships
