"""FastAPI main application for nl2sql."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

# slowapi 限流：默认每 IP 30 次/分钟，盖住所有接口（重点是 LLM 调用类），
# 防止公开部署后接口被刷、LLM 余额被盗用。
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

# Load environment variables from .env file
# Try multiple common locations so .env is found regardless of cwd.
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_script_dir = os.path.dirname(os.path.abspath(__file__))
env_paths = [
    os.path.join(_script_dir, ".env"),                 # same dir as main.py
    os.path.join(_project_root, "backend", "src", "app", ".env"),
    os.path.join(_project_root, ".env"),
    os.path.join(os.getcwd(), ".env"),
]
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        break
else:
    load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import init_db
from app.graphdb.client import get_falkordb
from app.api.connections import router as connections_router
from app.api.database import router as database_router
from app.api.graphs import router as graphs_router
from app.api.schema import router as schema_router
from app.api.settings import router as settings_router
from app.api.hybrid_qa import router as hybrid_qa_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting up nl2sql API...")
    await init_db()
    logger.info("Management database initialized.")

    # Pre-initialize FalkorDB so connection issues are caught at startup
    try:
        falkordb = get_falkordb()
        _ = falkordb.db  # trigger lazy connection
        logger.info("FalkorDB connection initialized.")
    except Exception as e:
        logger.warning("FalkorDB not available at startup: %s", e)

    # Pre-initialize embedding backend (used by memory + retrieval)
    try:
        from app.api.embeddings import get_embedding_backend
        _ = get_embedding_backend()
        logger.info("Embedding backend initialized.")
    except Exception as e:
        logger.warning("Embedding backend not available at startup: %s", e)

    yield
    logger.info("Shutting down nl2sql API...")


# API 文档路径由环境变量控制：
#   默认 /docs（本地开发方便）；
#   生产环境 .env 里设 DOCS_PATH=/docs-<随机串> 藏到不易扫描的路径，
#   或直接 DOCS_PATH= （空值）完全关闭文档。
# 公开部署时把 Swagger 留在默认路径等于把接口说明书挂在门外的墙上。
_docs_path = os.getenv("DOCS_PATH", "/docs") or None

limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

app = FastAPI(
    title="NL2SQL API",
    description="Enterprise natural language to SQL service",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=_docs_path,
    redoc_url=None,
    openapi_url=f"{_docs_path}/openapi.json" if _docs_path else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# default_limits 需要 SlowAPIMiddleware 才生效
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:80",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Register routers
app.include_router(connections_router, prefix="/api")
app.include_router(database_router, prefix="/api")
app.include_router(graphs_router, prefix="/api")
app.include_router(schema_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(hybrid_qa_router, prefix="/api")
