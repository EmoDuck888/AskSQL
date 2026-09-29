"""Database loaders for schema extraction and graph loading."""

from app.loaders.base_loader import BaseLoader
from app.loaders.mysql_loader import MySQLLoader
from app.loaders.postgres_loader import PostgresLoader
from app.loaders.sqlite_loader import SQLiteLoader
from app.loaders.duckdb_loader import DuckDBLoader
from app.loaders.snowflake_loader import SnowflakeLoader
from app.loaders.mssql_loader import MSSQLLoader
from app.loaders.oracle_loader import OracleLoader
from app.loaders.clickhouse_loader import ClickHouseLoader
from app.loaders.bigquery_loader import BigQueryLoader
from app.loaders.presto_loader import PrestoLoader

__all__ = [
    "BaseLoader",
    "MySQLLoader",
    "PostgresLoader",
    "SQLiteLoader",
    "DuckDBLoader",
    "SnowflakeLoader",
    "MSSQLLoader",
    "OracleLoader",
    "ClickHouseLoader",
    "BigQueryLoader",
    "PrestoLoader",
]
