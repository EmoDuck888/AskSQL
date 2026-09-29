"""Base loader module providing abstract base class for data loaders."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Any, TYPE_CHECKING


class BaseLoader(ABC):
    """Abstract base class for data loaders."""

    @staticmethod
    @abstractmethod
    async def load(
        _graph_id: str, _connection_url: str, _db=None
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """
        Load the graph data into the database.
        This method must be implemented by any subclass.
        """
        if TYPE_CHECKING:
            yield True, ""

    @staticmethod
    @abstractmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Execute query to get random sample values for a column.

        Args:
            cursor: Database cursor
            table_name: Name of the table
            col_name: Name of the column
            sample_size: Number of random samples to retrieve (default: 3)

        Returns:
            List of sample values
        """

    @classmethod
    def extract_sample_values_for_column(
        cls, cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Extract random sample values for a column.

        Args:
            cursor: Database cursor
            table_name: Name of the table
            col_name: Name of the column
            sample_size: Number of random samples to retrieve (default: 3)

        Returns:
            List of sample values (converted to strings), or empty list
        """
        sample_values = cls._execute_sample_query(cursor, table_name, col_name, sample_size)

        if sample_values:
            first_val = sample_values[0]
            if isinstance(first_val, (str, int, float)):
                return [str(v) for v in sample_values]

        return []
