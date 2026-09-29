"""BigQuery loader for loading database schemas into FalkorDB graphs."""

import logging
from typing import AsyncGenerator, Dict, Any, List

from app.graphdb.schema_graph import SchemaGraphManager
from app.loaders.base_loader import BaseLoader

logger = logging.getLogger(__name__)


class BigQueryLoader(BaseLoader):
    """Loader for BigQuery databases."""

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        # BigQuery doesn't support direct cursor execution in the same way
        return []

    @staticmethod
    async def load(
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """Load BigQuery schema into FalkorDB graph."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
            import json

            params = BigQueryLoader._parse_url(connection_url)
            project_id = params.get("project_id", "")
            cred_file = params.get("credentials_file")

            if cred_file:
                with open(cred_file, "r") as f:
                    credentials = service_account.Credentials.from_service_account_info(
                        json.loads(f.read()),
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                client = bigquery.Client(project=project_id, credentials=credentials)
            else:
                client = bigquery.Client(project=project_id)

            dataset_id = params.get("dataset", "")

            yield True, "Extracting table information..."
            entities = BigQueryLoader.extract_tables_info(client, dataset_id)

            yield True, "Extracting relationship information..."
            relationships = {}

            yield True, "Loading data into graph..."
            graph_id = f"{prefix}_{project_id}"
            await SchemaGraphManager.create_schema_graph(
                graph_id=graph_id,
                entities=entities,
                relationships=relationships,
                db_name=project_id,
                db_url=connection_url,
            )

            yield True, f"BigQuery schema loaded successfully. Found {len(entities)} tables."

        except Exception as e:
            logger.error("Error loading BigQuery schema: %s", e)
            yield False, f"Failed to load BigQuery database schema: {str(e)}"

    @staticmethod
    def _parse_url(connection_url: str) -> Dict[str, str]:
        """Parse BigQuery connection parameters."""
        params = {}
        for part in connection_url.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
        return params

    @staticmethod
    def extract_tables_info(client, dataset_id: str) -> Dict[str, Any]:
        """Extract table and column information."""
        entities = {}

        if dataset_id:
            tables = client.list_tables(dataset_id)
        else:
            tables = []
            for dataset in client.list_datasets():
                tables.extend(client.list_tables(dataset.dataset_id))

        for table in tables:
            table_ref = client.get_table(table.reference)
            table_name = table_ref.table_id
            table_description = table_ref.description or ""

            columns_info = {}
            for field in table_ref.schema:
                columns_info[field.name] = {
                    "type": field.field_type,
                    "null": "YES" if field.is_nullable else "NO",
                    "key": "NONE",
                    "description": field.description or f"Column {field.name} of type {field.field_type}",
                    "default": None,
                    "sample_values": [],
                }

            entities[table_name] = {
                "description": table_description if table_description else f"Table: {table_name}",
                "columns": columns_info,
                "foreign_keys": [],
                "col_descriptions": [col_info["description"] for col_info in columns_info.values()],
            }

        return entities
