"""MySQL loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

import pymysql
from pymysql.cursors import DictCursor

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class MySQLLoader(BaseLoader):
    """Loader for MySQL databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        query = f"""
            SELECT DISTINCT `{col_name}`
            FROM `{table_name}`
            WHERE `{col_name}` IS NOT NULL
            ORDER BY RAND()
            LIMIT %s;
        """
        cursor.execute(query, (sample_size,))
        sample_results = cursor.fetchall()
        return [row[col_name] for row in sample_results if row[col_name] is not None]

    @staticmethod
    def _parse_mysql_url(connection_url: str) -> Dict[str, Any]:
        """Parse MySQL connection URL."""
        from urllib.parse import unquote

        if connection_url.startswith("mysql://"):
            url = connection_url[8:]
        else:
            raise ValueError("Invalid MySQL URL format")

        if "@" not in url:
            raise ValueError("MySQL URL must include username and host")

        credentials, host_db = url.split("@", 1)

        if ":" in credentials:
            username, password = credentials.split(":", 1)
        else:
            username = credentials
            password = ""

        if "/" not in host_db:
            raise ValueError("MySQL URL must include database name")

        host_port, database = host_db.split("/", 1)
        if "?" in database:
            database = database.split("?")[0]

        if ":" in host_port:
            host, port = host_port.split(":", 1)
            port = int(port)
        else:
            host = host_port
            port = 3306

        return {
            "host": host,
            "port": port,
            "user": unquote(username),
            "password": unquote(password),
            "database": database,
        }

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load MySQL schema into FalkorDB graph."""
        try:
            conn_params = MySQLLoader._parse_mysql_url(connection_url)
            conn = pymysql.connect(**conn_params)
            cursor = conn.cursor(DictCursor)
            db_name = conn_params["database"]

            yield True, "Extracting table information..."
            entities = MySQLLoader.extract_tables_info(cursor, db_name)

            yield True, "Extracting relationship information..."
            relationships = MySQLLoader.extract_relationships(cursor, db_name)

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

            yield True, f"MySQL schema loaded successfully. Found {len(entities)} tables."

        except pymysql.MySQLError as e:
            logger.error("MySQL connection error: %s", e)
            yield False, "Failed to connect to MySQL database"
        except Exception as e:
            logger.error("Error loading MySQL schema: %s", e)
            yield False, f"Failed to load MySQL database schema: {str(e)}"

    @staticmethod
    def extract_tables_info(cursor, db_name: str) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        cursor.execute("""
            SELECT table_name, table_comment
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """, (db_name,))

        tables = cursor.fetchall()

        for table_info in tables:
            table_name = table_info["TABLE_NAME"]
            table_comment = table_info["TABLE_COMMENT"]
            columns_info = MySQLLoader.extract_columns_info(cursor, db_name, table_name)
            foreign_keys = MySQLLoader.extract_foreign_keys(cursor, db_name, table_name)
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
    def extract_columns_info(cursor, db_name: str, table_name: str) -> Dict[str, Any]:
        """Extract column information."""
        cursor.execute("""
            SELECT
                column_name, data_type, is_nullable,
                column_default, column_key, column_comment
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, (db_name, table_name))

        columns_info = {}
        for col_info in cursor.fetchall():
            col_name = col_info["COLUMN_NAME"]
            data_type = col_info["DATA_TYPE"]
            is_nullable = col_info["IS_NULLABLE"]
            column_default = col_info["COLUMN_DEFAULT"]
            column_key = col_info["COLUMN_KEY"]
            column_comment = col_info["COLUMN_COMMENT"]

            if column_key == "PRI":
                key_type = "PRIMARY KEY"
            elif column_key == "MUL":
                key_type = "FOREIGN KEY"
            elif column_key == "UNI":
                key_type = "UNIQUE KEY"
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

            sample_values = MySQLLoader.extract_sample_values_for_column(
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
    def extract_foreign_keys(cursor, db_name: str, table_name: str) -> List[Dict[str, str]]:
        """Extract foreign key information."""
        cursor.execute("""
            SELECT
                constraint_name, column_name,
                referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND table_name = %s
            AND referenced_table_name IS NOT NULL
            ORDER BY constraint_name, ordinal_position;
        """, (db_name, table_name))

        foreign_keys = []
        for fk_info in cursor.fetchall():
            foreign_keys.append({
                "constraint_name": fk_info["CONSTRAINT_NAME"],
                "column": fk_info["COLUMN_NAME"],
                "referenced_table": fk_info["REFERENCED_TABLE_NAME"],
                "referenced_column": fk_info["REFERENCED_COLUMN_NAME"],
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(cursor, db_name: str) -> Dict[str, List[Dict[str, str]]]:
        """Extract all relationship information."""
        cursor.execute("""
            SELECT
                table_name, constraint_name, column_name,
                referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND referenced_table_name IS NOT NULL
            ORDER BY table_name, constraint_name;
        """, (db_name,))

        relationships = {}
        for rel_info in cursor.fetchall():
            constraint_name = rel_info["CONSTRAINT_NAME"]
            if constraint_name not in relationships:
                relationships[constraint_name] = []
            relationships[constraint_name].append({
                "from": rel_info["TABLE_NAME"],
                "to": rel_info["REFERENCED_TABLE_NAME"],
                "source_column": rel_info["COLUMN_NAME"],
                "target_column": rel_info["REFERENCED_COLUMN_NAME"],
                "note": f"Foreign key: {constraint_name}",
            })

        return relationships
