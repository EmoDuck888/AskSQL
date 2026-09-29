"""Database connection management routes."""
import logging
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.database import DBConnection, BusinessMetric

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Connections"])


# Map of database type -> default port
DB_DEFAULT_PORTS = {
    "mysql": 3306,
    "postgresql": 5432,
    "sqlite": None,
    "bigquery": None,
    "clickhouse": 8123,
    "duckdb": None,
    "mssql": 1433,
    "oracle": 1521,
    "presto": 443,
    "snowflake": None,
}


class ConnectionCreate(BaseModel):
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    connection_url: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    connection_url: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


class ConnectionResponse(BaseModel):
    id: int
    name: str
    db_type: str
    host: Optional[str]
    port: Optional[int]
    database_name: Optional[str]
    username: Optional[str]
    connection_url: Optional[str]
    extra_params: Optional[Dict[str, Any]]
    falkordb_graph_id: Optional[str]
    status: str
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


@router.get("/connections", response_model=List[ConnectionResponse])
async def list_connections(session: AsyncSession = Depends(get_session)):
    """List all database connections."""
    result = await session.execute(select(DBConnection).order_by(DBConnection.created_at.desc()))
    connections = result.scalars().all()
    return [conn.to_dict() for conn in connections]


@router.post("/connections", response_model=ConnectionResponse)
async def create_connection(
    data: ConnectionCreate, session: AsyncSession = Depends(get_session)
):
    """Create a new database connection."""
    conn = DBConnection(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        username=data.username,
        connection_url=data.connection_url,
        extra_params=data.extra_params,
        status="pending",
    )
    if data.password:
        conn.set_password(data.password)

    session.add(conn)
    await session.commit()
    await session.refresh(conn)
    return conn.to_dict()


@router.get("/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: int, session: AsyncSession = Depends(get_session)
):
    """Get a single connection."""
    result = await session.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn.to_dict()


@router.put("/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: int,
    data: ConnectionUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a connection."""
    result = await session.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if data.name is not None:
        conn.name = data.name
    if data.host is not None:
        conn.host = data.host
    if data.port is not None:
        conn.port = data.port
    if data.database_name is not None:
        conn.database_name = data.database_name
    if data.username is not None:
        conn.username = data.username
    if data.password is not None:
        conn.set_password(data.password)
    if data.connection_url is not None:
        conn.connection_url = data.connection_url
    if data.extra_params is not None:
        conn.extra_params = data.extra_params

    await session.commit()
    await session.refresh(conn)
    return conn.to_dict()


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int, session: AsyncSession = Depends(get_session)
):
    """Delete a connection and its FalkorDB graph."""
    result = await session.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Delete FalkorDB graph if exists
    if conn.falkordb_graph_id:
        from app.graphdb.schema_graph import SchemaGraphManager
        try:
            await SchemaGraphManager.delete_schema_graph(conn.falkordb_graph_id)
        except Exception as e:
            logger.warning("Failed to delete FalkorDB graph: %s", e)

    await session.delete(conn)
    await session.commit()
    return {"success": True, "message": "Connection deleted"}


def _build_connection_url(conn: DBConnection) -> Optional[str]:
    """Build connection URL from connection fields, falling back to stored URL."""
    from urllib.parse import quote

    try:
        password = conn.get_password() or ""
    except Exception as e:
        logger.warning("Failed to decrypt password for connection %s: %s", conn.id, e)
        password = ""

    db_type = conn.db_type.lower()

    # Prefer building from explicit fields (keeps behaviour consistent with test_connection)
    # Fall back to conn.connection_url only when fields are missing.
    if db_type == "mysql":
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"mysql://{user}:{pw}@{host}:{conn.port or 3306}/{conn.database_name or ''}"
    elif db_type in ("postgresql", "postgres"):
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"postgresql://{user}:{pw}@{host}:{conn.port or 5432}/{conn.database_name or ''}"
    elif db_type == "sqlite":
        return conn.database_name or conn.connection_url or ""
    elif db_type == "clickhouse":
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"clickhouse://{user}:{pw}@{host}:{conn.port or 8123}/{conn.database_name or ''}"
    elif db_type == "presto":
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"presto://{user}:{pw}@{host}:{conn.port or 443}/{conn.database_name or ''}"
    elif db_type == "duckdb":
        return conn.database_name or conn.connection_url or ":memory:"
    elif db_type == "mssql":
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"mssql://{user}:{pw}@{host}:{conn.port or 1433}/{conn.database_name or ''}"
    elif db_type == "oracle":
        host = conn.host or "localhost"
        user = quote(conn.username or "", safe="")
        pw = quote(password, safe="")
        return f"oracle://{user}:{pw}@{host}:{conn.port or 1521}/{conn.database_name or ''}"
    elif db_type == "snowflake":
        return conn.connection_url
    elif db_type == "bigquery":
        return conn.connection_url
    elif db_type == "snowflake":
        return conn.connection_url
    elif db_type == "bigquery":
        return conn.connection_url
    return conn.connection_url


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: int, session: AsyncSession = Depends(get_session)
):
    """Test a database connection."""
    result = await session.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    db_type = conn.db_type.lower()
    try:
        password = conn.get_password() or ""
    except Exception as e:
        logger.warning("Failed to decrypt password: %s", e)
        password = ""

    try:
        if db_type == "mysql":
            import pymysql
            params = {
                "host": conn.host or "localhost",
                "port": conn.port or 3306,
                "user": conn.username or "",
                "password": password,
                "database": conn.database_name or "",
            }
            test_conn = pymysql.connect(**params)
            test_conn.close()

        elif db_type in ("postgresql", "postgres"):
            import psycopg2
            params = {
                "host": conn.host or "localhost",
                "port": conn.port or 5432,
                "user": conn.username or "",
                "password": password,
                "database": conn.database_name or "",
            }
            test_conn = psycopg2.connect(**params)
            try:
                with test_conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                test_conn.close()

        elif db_type == "sqlite":
            import sqlite3
            db_path = conn.connection_url or conn.database_name or ""
            test_conn = sqlite3.connect(db_path)
            test_conn.close()

        elif db_type == "duckdb":
            import duckdb
            db_path = conn.connection_url or conn.database_name or ":memory:"
            test_conn = duckdb.connect(db_path)
            test_conn.close()

        elif db_type == "snowflake":
            import snowflake.connector
            params = {
                "user": conn.username or "",
                "account": (conn.extra_params or {}).get("account", ""),
                "password": password,
            }
            if conn.database_name:
                params["database"] = conn.database_name
            warehouse = (conn.extra_params or {}).get("warehouse")
            if warehouse:
                params["warehouse"] = warehouse
            role = (conn.extra_params or {}).get("role")
            if role:
                params["role"] = role
            test_conn = snowflake.connector.connect(**params)
            test_conn.close()

        elif db_type == "mssql":
            import pyodbc
            conn_str = conn.connection_url or (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={conn.host or 'localhost'},{conn.port or 1433};"
                f"DATABASE={conn.database_name or ''};"
                f"UID={conn.username or ''};PWD={password}"
            )
            test_conn = pyodbc.connect(conn_str)
            test_conn.close()

        elif db_type == "oracle":
            import oracledb
            dsn = conn.connection_url or f"{conn.host or 'localhost'}:{conn.port or 1521}/{conn.database_name or ''}"
            test_conn = oracledb.connect(
                user=conn.username or "",
                password=password,
                dsn=dsn,
            )
            test_conn.close()

        elif db_type == "clickhouse":
            import clickhouse_connect
            client = clickhouse_connect.get_client(
                host=conn.host or "localhost",
                port=conn.port or 8123,
                username=conn.username or "",
                password=password,
                database=conn.database_name or "",
            )
            client.close()

        elif db_type == "bigquery":
            from google.cloud import bigquery
            project_id = (conn.extra_params or {}).get("project_id", conn.database_name or "")
            cred_file = (conn.extra_params or {}).get("credentials_file")
            if cred_file:
                from google.oauth2 import service_account
                import json
                with open(cred_file, "r") as f:
                    credentials = service_account.Credentials.from_service_account_info(
                        json.loads(f.read()),
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                client = bigquery.Client(project=project_id, credentials=credentials)
            else:
                client = bigquery.Client(project=project_id)
            # Run a simple query to verify connection
            client.query("SELECT 1").result()

        elif db_type == "presto":
            from pyhive import presto
            connection = presto.Connection(
                host=conn.host or "localhost",
                port=conn.port or 443,
                username=conn.username or "",
                password=password,
                catalog=(conn.extra_params or {}).get("catalog", "hive"),
                schema=conn.database_name or "default",
            )
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            connection.close()

        else:
            return {"status": "error", "message": f"Unsupported db_type: {conn.db_type}"}

        return {"status": "success", "message": "Connection successful"}
    except Exception as e:
        logger.exception("Connection test failed")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Schema discovery & save to FalkorDB
# ---------------------------------------------------------------------------

def _generate_graph_id(conn: DBConnection) -> str:
    """Generate FalkorDB graph ID matching loader conventions."""
    prefix = "user"
    db_type = conn.db_type.lower()
    url = _build_connection_url(conn) or ""

    if db_type == "sqlite":
        return f"{prefix}_{url.replace('/', '_').replace('\\', '_').replace(':', '_')}"
    elif db_type in ("mysql", "postgresql", "postgres", "clickhouse", "snowflake", "bigquery"):
        # Extract database name from URL
        if "/" in url:
            db_name = url.rsplit("/", 1)[-1]
            if "?" in db_name:
                db_name = db_name.split("?")[0]
            return f"{prefix}_{db_name}"
        return f"{prefix}_{db_type}"
    elif db_type == "duckdb":
        return f"{prefix}_{url.replace('/', '_').replace('\\', '_').replace(':', '_')}"
    else:
        return f"{prefix}_{db_type}"


@router.post("/connections/{connection_id}/discover-and-save")
async def discover_and_save_schema(
    connection_id: int, session: AsyncSession = Depends(get_session)
):
    """Discover schema from the connected database and save it to FalkorDB."""
    result = await session.execute(
        select(DBConnection).where(DBConnection.id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    conn.status = "loading"
    await session.commit()

    db_type = conn.db_type.lower()
    url = _build_connection_url(conn)
    if not url:
        conn.status = "error"
        await session.commit()
        raise HTTPException(status_code=400, detail="Cannot build connection URL")

    # Lazy imports to avoid startup overhead
    loader_cls = None
    try:
        if db_type == "mysql":
            from app.loaders.mysql_loader import MySQLLoader as loader_cls
        elif db_type in ("postgresql", "postgres"):
            from app.loaders.postgres_loader import PostgresLoader as loader_cls
        elif db_type == "sqlite":
            from app.loaders.sqlite_loader import SQLiteLoader as loader_cls
        elif db_type == "duckdb":
            from app.loaders.duckdb_loader import DuckDBLoader as loader_cls
        elif db_type == "snowflake":
            from app.loaders.snowflake_loader import SnowflakeLoader as loader_cls
        elif db_type == "mssql":
            from app.loaders.mssql_loader import MSSQLLoader as loader_cls
        elif db_type == "oracle":
            from app.loaders.oracle_loader import OracleLoader as loader_cls
        elif db_type == "clickhouse":
            from app.loaders.clickhouse_loader import ClickHouseLoader as loader_cls
        elif db_type == "bigquery":
            from app.loaders.bigquery_loader import BigQueryLoader as loader_cls
        elif db_type == "presto":
            from app.loaders.presto_loader import PrestoLoader as loader_cls
    except ImportError as e:
        logger.error("Failed to import loader for %s: %s", db_type, e)
        conn.status = "error"
        await session.commit()
        raise HTTPException(status_code=500, detail=f"Database driver not installed for {db_type}: {str(e)}")

    if not loader_cls:
        conn.status = "error"
        await session.commit()
        raise HTTPException(status_code=400, detail=f"Unsupported db_type: {db_type}")

    steps = []
    graph_id = _generate_graph_id(conn)

    try:
        async for success, msg in loader_cls.load("user", url):
            steps.append({"success": success, "message": msg})
            if not success:
                conn.status = "error"
                await session.commit()
                return {
                    "status": "error",
                    "message": msg,
                    "steps": steps,
                }

        conn.falkordb_graph_id = graph_id
        conn.status = "active"
        await session.commit()
        await session.refresh(conn)

        return {
            "status": "success",
            "message": "Schema discovered and saved successfully",
            "graph_id": graph_id,
            "steps": steps,
            "connection": conn.to_dict(),
        }
    except ConnectionError as e:
        logger.exception("FalkorDB connection failed during schema discovery")
        conn.status = "error"
        await session.commit()
        raise HTTPException(status_code=503, detail=f"FalkorDB unavailable: {str(e)}")
    except Exception as e:
        logger.exception("Schema discovery failed")
        conn.status = "error"
        await session.commit()
        raise HTTPException(status_code=500, detail=f"Schema discovery failed: {str(e)}")


# ---------------------------------------------------------------------------
# Business Metrics
# ---------------------------------------------------------------------------

class BusinessMetricCreate(BaseModel):
    name: str
    formula: str
    related_table: Optional[str] = None
    filter_condition: Optional[str] = None
    description: Optional[str] = None


class BusinessMetricUpdate(BaseModel):
    name: Optional[str] = None
    formula: Optional[str] = None
    related_table: Optional[str] = None
    filter_condition: Optional[str] = None
    description: Optional[str] = None


class BusinessMetricResponse(BaseModel):
    id: int
    connection_id: int
    name: str
    formula: str
    related_table: Optional[str]
    filter_condition: Optional[str]
    description: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/connections/{connection_id}/business-metrics", response_model=List[BusinessMetricResponse])
async def list_business_metrics(
    connection_id: int, session: AsyncSession = Depends(get_session)
):
    """List all business metrics for a connection."""
    result = await session.execute(
        select(BusinessMetric).where(BusinessMetric.connection_id == connection_id)
    )
    metrics = result.scalars().all()
    return [m.to_dict() for m in metrics]


@router.post("/connections/{connection_id}/business-metrics", response_model=BusinessMetricResponse)
async def create_business_metric(
    connection_id: int,
    data: BusinessMetricCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a business metric for a connection."""
    metric = BusinessMetric(
        connection_id=connection_id,
        name=data.name,
        formula=data.formula,
        related_table=data.related_table,
        filter_condition=data.filter_condition,
        description=data.description,
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return metric.to_dict()


@router.put("/connections/{connection_id}/business-metrics/{metric_id}", response_model=BusinessMetricResponse)
async def update_business_metric(
    connection_id: int,
    metric_id: int,
    data: BusinessMetricUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a business metric."""
    result = await session.execute(
        select(BusinessMetric).where(
            BusinessMetric.id == metric_id,
            BusinessMetric.connection_id == connection_id,
        )
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")

    if data.name is not None:
        metric.name = data.name
    if data.formula is not None:
        metric.formula = data.formula
    if data.related_table is not None:
        metric.related_table = data.related_table
    if data.filter_condition is not None:
        metric.filter_condition = data.filter_condition
    if data.description is not None:
        metric.description = data.description

    await session.commit()
    await session.refresh(metric)
    return metric.to_dict()


@router.delete("/connections/{connection_id}/business-metrics/{metric_id}")
async def delete_business_metric(
    connection_id: int,
    metric_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a business metric."""
    result = await session.execute(
        select(BusinessMetric).where(
            BusinessMetric.id == metric_id,
            BusinessMetric.connection_id == connection_id,
        )
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")

    await session.delete(metric)
    await session.commit()
    return {"success": True, "message": "Metric deleted"}
