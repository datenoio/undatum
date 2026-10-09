"""Elasticsearch ingester backend."""

import logging
import time

from ...common.errors import DependencyError
from .base import INITIAL_RETRY_DELAY, MAX_RETRIES, BasicIngester

try:
    from elasticsearch import Elasticsearch
except ImportError:  # optional: pip install "undatum[elastic]"
    Elasticsearch = None

logger = logging.getLogger(__name__)


class ElasticIngester(BasicIngester):
    """Elasticsearch data ingester.

    Handles bulk ingestion of documents to Elasticsearch with retry logic
    and error handling. Uses connection pooling via Elasticsearch client.

    Args:
        uri: Elasticsearch connection URI
        api_key: API key for authentication
        search_index: Index name where documents will be indexed
        document_id: Field name in documents to use as document ID (default: "id")
        timeout: Request timeout in seconds (default: 60)
        verify_certs: Verify the server TLS certificate (default: True)
        ca_certs: Path to a CA bundle for self-signed or private CAs
        pipeline: Optional ingest pipeline name applied to every document
    """

    def __init__(
        self,
        uri: str,
        api_key: str,
        search_index: str,
        document_id: str = "id",
        timeout: int = 60,
        verify_certs: bool = True,
        ca_certs: str | None = None,
        pipeline: str | None = None,
    ):
        if not verify_certs:
            logger.warning("TLS certificate verification is disabled for %s (--insecure)", uri)
        client_kwargs = {
            "api_key": api_key,
            "verify_certs": verify_certs,
            "request_timeout": timeout,
            "max_retries": 10,
            "retry_on_timeout": True,
        }
        if ca_certs:
            client_kwargs["ca_certs"] = ca_certs
        if not verify_certs:
            client_kwargs["ssl_show_warn"] = False
        if Elasticsearch is None:
            raise DependencyError(
                "elasticsearch",
                feature="Elasticsearch ingestion",
                install_command='pip install "undatum[elastic]"',
            )
        self.client = Elasticsearch(uri, **client_kwargs)
        self._index = search_index
        self._item_id = document_id
        self._pipeline = pipeline

    def ingest(self, batch):
        """Ingest batch of documents to Elasticsearch with retry logic."""
        documents = []
        failed_docs = []

        # Build bulk operation documents, handling missing document IDs
        for doc in batch:
            if self._item_id not in doc:
                failed_docs.append(
                    {
                        "doc": doc,
                        "error": f"Missing required field '{self._item_id}' for document ID",
                    }
                )
                logger.warning(f"Document missing required field '{self._item_id}': {doc}")
                continue
            documents.append({"index": {"_index": self._index, "_id": doc[self._item_id]}})
            documents.append(doc)

        if not documents:
            if failed_docs:
                logger.error(
                    f"All {len(batch)} documents in batch failed validation (missing '{self._item_id}' field)"
                )
            return None

        # Retry logic with exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                bulk_kwargs = {"operations": documents}
                if self._pipeline:
                    bulk_kwargs["pipeline"] = self._pipeline
                result = self.client.bulk(**bulk_kwargs)
                if result.get("errors"):
                    # Count and log individual errors from bulk response
                    error_items = [
                        r for r in result.get("items", []) if "error" in r.get("index", {})
                    ]
                    if error_items:
                        logger.warning(
                            f"Elasticsearch bulk operation had {len(error_items)} errors out of {len(batch)} documents"
                        )
                        for item in error_items[:5]:  # Log first 5 errors
                            error_info = item.get("index", {}).get("error", {})
                            logger.warning(f"  Error: {error_info}")
                return result
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"Elasticsearch bulk operation failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"Elasticsearch bulk operation failed after {MAX_RETRIES} attempts: {e}"
                    )
                    raise
