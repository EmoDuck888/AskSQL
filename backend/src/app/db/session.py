"""SQLAlchemy async session management."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Default management database path
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "manage.db"
MANAGE_DB_URL = os.getenv("MANAGE_DB_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# Ensure directory exists
if MANAGE_DB_URL.startswith("sqlite+"):
    db_path = MANAGE_DB_URL.replace("sqlite+aiosqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    MANAGE_DB_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    """Verify the management database is reachable.

    Schema creation/migration is owned by Alembic (see backend/migrations);
    run `uv run alembic upgrade head` before starting the app. This function
    only checks connectivity so a missing or unreachable database fails
    fast at startup instead of mid-request.
    """
    async with engine.connect():
        pass


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    async with AsyncSessionLocal() as session:
        yield session
