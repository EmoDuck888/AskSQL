"""Stream database connection routes."""
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.database import DBConnection
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

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Database Connection"])

MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"


class DatabaseConnectionRequest(BaseModel):
    url: str
    connection_id: int | None = None


# Map of db_type to loader class
LOADER_MAP = {
    "mysql": MySQLLoader,
    "postgresql": PostgresLoader,
    "postgres": PostgresLoader,
    "sqlite": SQLiteLoader,
    "duckdb": DuckDBLoader,
    "snowflake": SnowflakeLoader,
    "mssql": MSSQLLoader,
    "oracle": OracleLoader,
    "clickhouse": ClickHouseLoader,
    "bigquery": BigQueryLoader,
    "presto": PrestoLoader,
}


def detect_db_type(url: str) -> str:
    """Detect database type from connection URL."""
    url_lower = url.lower()
    if url_lower.startswith("mysql://"):
        return "mysql"
    elif url_lower.startswith(("postgresql://", "postgres://")):
        return "postgresql"
    elif url_lower.startswith("sqlite://") or url_lower.endswith(".db") or url_lower.endswith(".sqlite"):
        return "sqlite"
    elif url_lower.startswith("duckdb://") or url_lower.endswith(".duckdb"):
        return "duckdb"
    elif url_lower.startswith("clickhouse://"):
        return "clickhouse"
    elif "account=" in url_lower and "user=" in url_lower:
        # Snowflake connection string pattern
        return "snowflake"
    elif url_lower.startswith("presto://"):
        return "presto"
    elif "driver=" in url_lower and "server=" in url_lower:
        # MSSQL ODBC connection string
        return "mssql"
    elif url_lower.startswith("bigquery://") or "project_id=" in url_lower:
        return "bigquery"
    elif "dsn=" in url_lower or "host=" in url_lower and "sid=" in url_lower:
        # Oracle connection string
        return "oracle"
    else:
        return "unknown"


async def load_database_stream(
    url: str, db_type: str | None = None, prefix: str = "user"
) -> AsyncGenerator[str, None]:
    """Stream database loading progress."""

    def _serialize(data: dict) -> str:
        return json.dumps(data) + MESSAGE_DELIMITER

    # Step 1: Start
    yield _serialize({
        "type": "reasoning_step",
        "message": "Step 1: Starting database connection",
    })

    # Step 2: Detect type
    detected_type = db_type or detect_db_type(url)
    loader_cls = LOADER_MAP.get(detected_type)

    if not loader_cls:
        yield _serialize({
            "type": "error",
            "message": f"Unsupported database type: {detected_type}. Supported types: {', '.join(LOADER_MAP.keys())}",
        })
        return

    yield _serialize({
        "type": "reasoning_step",
        "message": f"Step 2: Detected database type: {detected_type}. Attempting to load schema...",
    })

    # Step 3: Load schema
    step_counter = 2
    try:
        async for success, message in loader_cls.load(prefix, url):
            if success:
                step_counter += 1
                yield _serialize({
                    "type": "reasoning_step",
                    "message": f"Step {step_counter}: {message}",
                })
            else:
                yield _serialize({
                    "type": "error",
                    "message": message,
                })
                return

        yield _serialize({
            "type": "final_result",
            "success": True,
            "message": "Database connected and schema loaded successfully",
        })
    except Exception as e:
        logger.exception("Error loading database: %s", e)
        yield _serialize({
            "type": "error",
            "message": f"Internal server error during database connection: {str(e)}",
        })


@router.post("/database", tags=["mcp_tool"])
async def connect_database(
    request: DatabaseConnectionRequest,
    session: AsyncSession = Depends(get_session),
):
    """Connect to a database and load its schema into FalkorDB.
    Streams progress as JSON separated by MESSAGE_DELIMITER.
    """
    # Update connection status if connection_id provided
    db_type = None
    if request.connection_id:
        result = await session.execute(
            select(DBConnection).where(DBConnection.id == request.connection_id)
        )
        conn = result.scalar_one_or_none()
        if conn:
            conn.status = "pending"
            await session.commit()
            db_type = conn.db_type

    async def generate():
        async for chunk in load_database_stream(request.url, db_type=db_type):
            yield chunk

    return StreamingResponse(generate(), media_type="application/json")
