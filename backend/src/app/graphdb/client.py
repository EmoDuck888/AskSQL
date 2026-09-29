"""FalkorDB connection management."""

import os
import logging
from typing import Optional

from falkordb.asyncio import FalkorDB
from redis.asyncio import BlockingConnectionPool

logger = logging.getLogger(__name__)


class FalkorDBClient:
    """Manages FalkorDB connection lifecycle."""

    _instance: Optional["FalkorDBClient"] = None
    _db: Optional[FalkorDB] = None
    _pool: Optional[BlockingConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def db(self) -> FalkorDB:
        """Get FalkorDB client, lazily initialized."""
        if self._db is None:
            self._db = self._create_connection()
        return self._db

    def _create_connection(self) -> FalkorDB:
        """Create FalkorDB connection."""
        url = os.getenv("FALKORDB_URL")

        if url:
            # Convert falkor:// to redis:// for redis-py compatibility
            if url.startswith("falkor://"):
                url = "redis://" + url[9:]
            try:
                self._pool = BlockingConnectionPool.from_url(
                    url, decode_responses=True
                )
                return FalkorDB(connection_pool=self._pool)
            except Exception as e:
                raise ConnectionError(f"Failed to connect to FalkorDB: {e}") from e

        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", "6379"))

        try:
            return FalkorDB(host=host, port=port)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to FalkorDB at {host}:{port}: {e}") from e

    def select_graph(self, graph_id: str):
        """Select a graph by ID."""
        return self.db.select_graph(graph_id)

    async def list_graphs(self) -> list[str]:
        """List all available graphs."""
        return await self.db.list_graphs()

    async def delete_graph(self, graph_id: str) -> None:
        """Delete a graph."""
        graph = self.select_graph(graph_id)
        await graph.delete()


# Global singleton
_falkordb_client: Optional[FalkorDBClient] = None


def get_falkordb() -> FalkorDBClient:
    """Get the global FalkorDB client singleton."""
    global _falkordb_client
    if _falkordb_client is None:
        _falkordb_client = FalkorDBClient()
    return _falkordb_client
