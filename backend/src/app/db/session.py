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
    """Initialize the management database tables."""
    from app.models.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    async with AsyncSessionLocal() as session:
        yield session
