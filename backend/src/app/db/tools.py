"""
本地直接调用的 SQL 工具集。

将 server.py 中封装的 MCP 工具以原生函数/对象形式暴露，
供 Agent 直接调用（无需走 MCP 协议）。

与 MCP 方式并存：
- MCP 方式：启动 server.py，通过 mcp 客户端访问
- 本地方式：直接 import 本模块中的 tools 列表使用
"""
from typing import Any, Dict, Optional

import pandas as pd
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from sqlalchemy import select

from app.db.config import McpSqlConfig
from app.db.session import AsyncSessionLocal
from app.db.sql_runner import RunSqlToolArgs, ToolContext
from app.models.database import DBConnection

# Mapping of database type names to their runner classes.
_RUNNER_REGISTRY: Dict[str, str] = {
    "bigquery": "app.db.engine.bigquery.sql_runner.BigQueryRunner",
    "clickhouse": "app.db.engine.clickhouse.sql_runner.ClickHouseRunner",
    "duckdb": "app.db.engine.duckdb.sql_runner.DuckDBRunner",
    "hive": "app.db.engine.hive.sql_runner.HiveRunner",
    "mssql": "app.db.engine.mssql.sql_runner.MSSQLRunner",
    "mysql": "app.db.engine.mysql.sql_runner.MySQLRunner",
    "oracle": "app.db.engine.oracle.sql_runner.OracleRunner",
    "postgres": "app.db.engine.postgres.sql_runner.PostgresRunner",
    "presto": "app.db.engine.presto.sql_runner.PrestoRunner",
    "snowflake": "app.db.engine.snowflake.sql_runner.SnowflakeRunner",
    "sqlite": "app.db.engine.sqlite.sql_runner.SqliteRunner",
}


# 数据库类型别名映射（用户界面常用名称 -> 内部注册名称）
_DB_TYPE_ALIASES: Dict[str, str] = {
    "postgresql": "postgres",
}


def _load_runner_class(db_type: str):
    """Dynamically import the SqlRunner class for the given database type."""
    import importlib

    db_type = db_type.lower()
    db_type = _DB_TYPE_ALIASES.get(db_type, db_type)

    class_path = _RUNNER_REGISTRY.get(db_type)
    if class_path is None:
        supported = ", ".join(_RUNNER_REGISTRY.keys())
        raise ValueError(
            f"Unsupported db_type: {db_type!r}. Supported: {supported}"
        )

    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _build_tool_context() -> ToolContext:
    """Build a minimal ToolContext for runner invocation."""
    return ToolContext.model_construct(
        user="user_001",
        metadata={},
    )


def _df_to_result(df: pd.DataFrame) -> Dict[str, Any]:
    """Convert a pandas DataFrame to a JSON-serializable dict."""
    return {
        "columns": list(df.columns),
        "rows": df.to_dict(orient="records"),
        "row_count": len(df),
    }


class SqlToolKit:
    """本地 SQL 工具集，直接调用底层 Runner，不走 MCP 协议。"""

    def __init__(self, config: Optional[McpSqlConfig] = None):
        self._config = config or McpSqlConfig.from_env()
        self._runner = None
        self._context = _build_tool_context()

    def _get_runner(self):
        """Lazy-load the SqlRunner instance."""
        if self._runner is None:
            runner_cls = _load_runner_class(self._config.db_type)
            self._runner = runner_cls(**self._config.config)
        return self._runner

    async def run_sql(self, sql: str) -> Dict[str, Any]:
        """Execute a SQL query against the configured database."""
        runner = self._get_runner()
        args = RunSqlToolArgs(sql=sql)
        df = await runner.run_sql(args, self._context)
        return _df_to_result(df)

    def get_db_info(self) -> Dict[str, Any]:
        """Return information about the currently configured database."""
        return {
            "db_type": self._config.db_type,
            "config_keys": list(self._config.config.keys()),
        }


# 默认实例（基于环境变量配置）
_sql_toolkit = SqlToolKit()

# 按 connection_id 缓存的 SqlToolKit 实例
_toolkit_cache: Dict[int, SqlToolKit] = {}


def _build_config_from_connection(conn: DBConnection) -> McpSqlConfig:
    """从 DBConnection 模型构建 McpSqlConfig。"""
    db_type = conn.db_type.lower()
    db_type = _DB_TYPE_ALIASES.get(db_type, db_type)
    extra: Dict[str, Any] = dict(conn.extra_params or {})

    if db_type in ("sqlite", "duckdb"):
        path = conn.database_name or extra.pop("database_path", "")
        if not path and conn.connection_url:
            if conn.connection_url.startswith("sqlite:///"):
                path = conn.connection_url[10:]
        if not path:
            raise ValueError(f"database_name or connection_url required for {db_type}")
        config: Dict[str, Any] = {"database_path": path}
        config.update(extra)
        return McpSqlConfig(db_type=db_type, config=config)

    config = {
        "host": conn.host,
        "port": conn.port,
        "database": conn.database_name,
        "user": conn.username,
        "password": conn.get_password(),
    }
    config = {k: v for k, v in config.items() if v is not None}
    config.update(extra)
    return McpSqlConfig(db_type=db_type, config=config)


async def _get_toolkit(runtime: ToolRuntime) -> SqlToolKit:
    """根据 runtime.context 中的 connection_id 获取对应的 SqlToolKit。"""
    ctx = runtime.context
    if isinstance(ctx, dict):
        connection_id = ctx.get("connection_id")
    else:
        connection_id = getattr(ctx, "connection_id", None)

    if connection_id is None:
        return _sql_toolkit

    if connection_id in _toolkit_cache:
        return _toolkit_cache[connection_id]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DBConnection).where(DBConnection.id == connection_id)
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise ValueError(f"Database connection {connection_id} not found")

        config = _build_config_from_connection(conn)
        toolkit = SqlToolKit(config=config)
        _toolkit_cache[connection_id] = toolkit
        return toolkit


@tool
async def run_sql(sql: str, runtime: ToolRuntime) -> Dict[str, Any]:
    """Execute a SQL query against the configured database.

    Args:
        sql: The SQL query to execute.

    Returns:
        A dictionary with columns, rows, and row_count.
    """
    toolkit = await _get_toolkit(runtime)
    return await toolkit.run_sql(sql)


@tool
async def get_db_info(runtime: ToolRuntime) -> Dict[str, Any]:
    """Return information about the currently configured database."""
    toolkit = await _get_toolkit(runtime)
    return toolkit.get_db_info()


# 供 Agent 直接导入使用的工具列表
tools = [run_sql, get_db_info]
