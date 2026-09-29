"""PostgreSQL loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

import psycopg2
import psycopg2.extras

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class PostgresLoader(BaseLoader):
    """Loader for PostgreSQL databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        # PostgreSQL does not allow ORDER BY expressions not in SELECT when DISTINCT is used.
        # Use GROUP BY instead of DISTINCT to keep the random ordering valid.
        query = f"""
            SELECT "{col_name}"
            FROM "{table_name}"
            WHERE "{col_name}" IS NOT NULL
            GROUP BY "{col_name}"
            ORDER BY RANDOM()
            LIMIT %s;
        """
        cursor.execute(query, (sample_size,))
        sample_results = cursor.fetchall()
        return [row[col_name] for row in sample_results if row[col_name] is not None]

    @staticmethod
    def _parse_postgres_url(connection_url: str) -> Dict[str, Any]:
        """Parse PostgreSQL connection URL."""
        import urllib.parse
        parsed = urllib.parse.urlparse(connection_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": urllib.parse.unquote(parsed.username or ""),
            "password": urllib.parse.unquote(parsed.password or ""),
            "database": parsed.path.lstrip("/").split("/")[0] if parsed.path else "",
        }

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load PostgreSQL schema into FalkorDB graph."""
        conn = None
        try:
            conn_params = PostgresLoader._parse_postgres_url(connection_url)
            conn = psycopg2.connect(**conn_params)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                db_name = conn_params["database"]

                yield True, "Extracting table information..."
                entities = PostgresLoader.extract_tables_info(cursor, db_name)

                yield True, "Extracting relationship information..."
                relationships = PostgresLoader.extract_relationships(cursor, db_name)

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_{db_name}"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name=db_name,
                db_url=connection_url,
            )

            yield True, f"PostgreSQL schema loaded successfully. Found {len(entities)} tables."

        except psycopg2.Error as e:
            logger.error("PostgreSQL connection error: %s", e)
            yield False, f"Failed to connect to PostgreSQL database: {str(e)}"
        except Exception as e:
            logger.error("Error loading PostgreSQL schema: %s", e)
            yield False, f"Failed to load PostgreSQL database schema: {str(e)}"
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def extract_tables_info(cursor, db_name: str) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT table_name, obj_description(
                (quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass
            ) as table_comment
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()

        for table_info in tables:
            table_name = table_info["table_name"]
            table_comment = table_info["table_comment"] or ""
            columns_info = PostgresLoader.extract_columns_info(cursor, table_name)
            foreign_keys = PostgresLoader.extract_foreign_keys(cursor, table_name)
            table_description = table_comment if table_comment else f"Table: {table_name}"
            col_descriptions = [col_info["description"] for col_info in columns_info.values()]

            entities[table_name] = {
                "description": table_description,
                "columns": columns_info,
                "foreign_keys": foreign_keys,
                "col_descriptions": col_descriptions,
            }

        return entities

    @staticmethod
    def extract_columns_info(cursor, table_name: str) -> Dict[str, Any]:
        """Extract column information."""
        cursor.execute("""
            SELECT
                c.column_name, c.data_type, c.is_nullable,
                c.column_default, c.ordinal_position,
                col_description(
                    (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                    c.ordinal_position
                ) as column_comment,
                CASE WHEN pk.column_name IS NOT NULL THEN 'PRI' ELSE '' END as column_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = %s
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_name = %s
            ORDER BY c.ordinal_position;
        """, (table_name, table_name))

        columns_info = {}
        for col_info in cursor.fetchall():
            col_name = col_info["column_name"]
            data_type = col_info["data_type"]
            is_nullable = col_info["is_nullable"]
            column_default = col_info["column_default"]
            column_key = col_info["column_key"]
            column_comment = col_info["column_comment"] or ""

            if column_key == "PRI":
                key_type = "PRIMARY KEY"
            else:
                key_type = "NONE"

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

            sample_values = PostgresLoader.extract_sample_values_for_column(
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
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS referenced_table_name,
                ccu.column_name AS referenced_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = %s;
        """, (table_name,))

        foreign_keys = []
        for fk_info in cursor.fetchall():
            foreign_keys.append({
                "constraint_name": fk_info["constraint_name"],
                "column": fk_info["column_name"],
                "referenced_table": fk_info["referenced_table_name"],
                "referenced_column": fk_info["referenced_column_name"],
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(cursor, db_name: str) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        cursor.execute("""
            SELECT
                tc.constraint_name,
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS referenced_table_name,
                ccu.column_name AS referenced_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY';
        """)

        relationships = {}
        for rel_info in cursor.fetchall():
            constraint_name = rel_info["constraint_name"]
            if constraint_name not in relationships:
                relationships[constraint_name] = []
            relationships[constraint_name].append({
                "from": rel_info["table_name"],
                "to": rel_info["referenced_table_name"],
                "source_column": rel_info["column_name"],
                "target_column": rel_info["referenced_column_name"],
                "note": f"Foreign key: {constraint_name}",
            })

        return relationships
