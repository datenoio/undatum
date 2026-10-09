"""MongoDB ingester backend."""

import logging
import time

from pymongo import MongoClient

from .base import INITIAL_RETRY_DELAY, MAX_RETRIES

logger = logging.getLogger(__name__)


class MongoIngester:
    """MongoDB data ingester.

    Handles bulk ingestion of documents to MongoDB with retry logic
    and error handling. Uses connection pooling via MongoClient.

    Args:
        uri: MongoDB connection URI
        db: Database name
        table: Collection name
        do_drop: If True, drop the collection before ingestion (default: False)
        timeout: Connection timeout in seconds (None uses default)
    """

    def __init__(self, uri, db, table, do_drop=False, timeout=None):
        # Use connection pooling (MongoClient manages pool automatically)
        if timeout and timeout > 0:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout * 1000)
        else:
            self.client = MongoClient(uri)
        self.db = self.client[db]
        if do_drop:
            self.db[table].drop()
        self.coll = self.db[table]

    def ingest(self, batch):
        """Ingest batch of documents to MongoDB with retry logic."""
        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                result = self.coll.insert_many(
                    batch, ordered=False
                )  # ordered=False for better error handling
                return result
            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"MongoDB insert_many failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    # On final failure, try to identify which documents failed
                    logger.error(f"MongoDB insert_many failed after {MAX_RETRIES} attempts: {e}")
                    # Try inserting one by one to identify problematic documents
                    failed_docs = []
                    for doc in batch:
                        try:
                            self.coll.insert_one(doc)
                        except Exception as doc_error:
                            failed_docs.append({"doc": doc, "error": str(doc_error)})
                            logger.error(f"Failed to insert document: {doc_error}")
                    if failed_docs:
                        logger.warning(
                            f"Failed to insert {len(failed_docs)} out of {len(batch)} documents"
                        )
                    raise last_exception from None
