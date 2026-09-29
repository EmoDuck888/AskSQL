"""FastAPI main application for nl2sql."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

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


app = FastAPI(
    title="NL2SQL API",
    description="Enterprise natural language to SQL service",
    version="0.2.0",
    lifespan=lifespan,
)

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
