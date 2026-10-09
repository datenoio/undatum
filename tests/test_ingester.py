"""Tests for database ingestion functionality."""

from unittest.mock import MagicMock, patch

import pytest

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_JSONL = (
    '{"id": "1", "name": "Alice", "age": 30}\n'
    '{"id": "2", "name": "Bob", "age": 25}\n'
    '{"id": "3", "name": "Charlie", "age": 35}\n'
)
SAMPLE_CSV = "id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n"

# Mock dependencies that may not be installed
try:
    from undatum.cmds.ingester import (
        DEFAULT_BATCH_SIZE,
        INITIAL_RETRY_DELAY,
        MAX_RETRIES,
        BasicIngester,
        ElasticIngester,
        Ingester,
        MongoIngester,
    )

    # Try to import PostgresIngester (may not be available if psycopg2 not installed)
    try:
        from undatum.cmds.ingester import PSYCOPG2_AVAILABLE, PostgresIngester

        POSTGRES_AVAILABLE = PSYCOPG2_AVAILABLE
    except (ImportError, AttributeError):
        POSTGRES_AVAILABLE = False
        PostgresIngester = None

    # Try to import MySQLIngester (may not be available if pymysql not installed)
    try:
        from undatum.cmds.ingester import PYMYSQL_AVAILABLE, MySQLIngester

        MYSQL_AVAILABLE = PYMYSQL_AVAILABLE
    except (ImportError, AttributeError):
        MYSQL_AVAILABLE = False
        MySQLIngester = None

    # SQLiteIngester is always available (sqlite3 is built-in)
    try:
        from undatum.cmds.ingester import SQLiteIngester

        SQLITE_AVAILABLE = True
    except (ImportError, AttributeError):
        SQLITE_AVAILABLE = False
        SQLiteIngester = None
except ImportError as e:
    pytest.skip(f"Required dependencies not available: {e}", allow_module_level=True)


class TestBasicIngester:
    """Test BasicIngester base class."""

    def test_basic_ingester_init(self):
        """Test BasicIngester initialization."""
        ingester = BasicIngester()
        assert ingester is not None

    def test_basic_ingester_ingest_not_implemented(self):
        """Test that ingest() raises NotImplementedError."""
        ingester = BasicIngester()
        with pytest.raises(NotImplementedError):
            ingester.ingest([])


class TestMongoIngester:
    """Test MongoIngester class."""

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    def test_mongo_ingester_init(self, mock_mongo_client):
        """Test MongoIngester initialization."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        ingester = MongoIngester("mongodb://localhost:27017", "testdb", "testcoll")

        assert ingester.client == mock_client
        assert ingester.db == mock_db
        assert ingester.coll == mock_coll
        mock_mongo_client.assert_called_once()

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    def test_mongo_ingester_init_with_timeout(self, mock_mongo_client):
        """Test MongoIngester initialization with timeout."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        MongoIngester("mongodb://localhost:27017", "testdb", "testcoll", timeout=30)

        mock_mongo_client.assert_called_once_with(
            "mongodb://localhost:27017", serverSelectionTimeoutMS=30000
        )

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    def test_mongo_ingester_init_with_drop(self, mock_mongo_client):
        """Test MongoIngester initialization with drop option."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        MongoIngester("mongodb://localhost:27017", "testdb", "testcoll", do_drop=True)

        mock_coll.drop.assert_called_once()

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    def test_mongo_ingester_ingest_success(self, mock_mongo_client):
        """Test successful MongoDB ingestion."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_result = MagicMock()
        mock_coll.insert_many.return_value = mock_result
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        ingester = MongoIngester("mongodb://localhost:27017", "testdb", "testcoll")
        batch = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        result = ingester.ingest(batch)

        mock_coll.insert_many.assert_called_once_with(batch, ordered=False)
        assert result == mock_result

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    @patch("undatum.cmds.ingester.mongo.time.sleep")
    def test_mongo_ingester_ingest_retry_success(self, mock_sleep, mock_mongo_client):
        """Test MongoDB ingestion with retry after transient failure."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_result = MagicMock()

        # First call fails, second succeeds
        mock_coll.insert_many.side_effect = [Exception("Connection error"), mock_result]
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        ingester = MongoIngester("mongodb://localhost:27017", "testdb", "testcoll")
        batch = [{"id": 1, "name": "Alice"}]

        result = ingester.ingest(batch)

        assert mock_coll.insert_many.call_count == 2
        mock_sleep.assert_called_once_with(INITIAL_RETRY_DELAY)
        assert result == mock_result

    @patch("undatum.cmds.ingester.mongo.MongoClient")
    @patch("undatum.cmds.ingester.mongo.time.sleep")
    def test_mongo_ingester_ingest_retry_exhausted(self, mock_sleep, mock_mongo_client):
        """Test MongoDB ingestion with all retries exhausted."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_coll = MagicMock()

        # All retries fail
        mock_coll.insert_many.side_effect = Exception("Connection error")
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_coll
        mock_mongo_client.return_value = mock_client

        ingester = MongoIngester("mongodb://localhost:27017", "testdb", "testcoll")
        batch = [{"id": 1, "name": "Alice"}]

        with pytest.raises(Exception, match="Connection error"):
            ingester.ingest(batch)

        assert mock_coll.insert_many.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1


class TestElasticIngester:
    """Test ElasticIngester class."""

    @patch("undatum.cmds.ingester.elastic.Elasticsearch")
    def test_elastic_ingester_init(self, mock_elasticsearch):
        """Test ElasticIngester initialization."""
        mock_client = MagicMock()
        mock_elasticsearch.return_value = mock_client

        ingester = ElasticIngester("https://localhost:9200", "api_key", "test_index", "id", 60)

        assert ingester.client == mock_client
        assert ingester._index == "test_index"
        assert ingester._item_id == "id"
        mock_elasticsearch.assert_called_once()

    @patch("undatum.cmds.ingester.elastic.Elasticsearch")
    def test_elastic_ingester_ingest_success(self, mock_elasticsearch):
        """Test successful Elasticsearch ingestion."""
        mock_client = MagicMock()
        mock_result = {"errors": False, "items": []}
        mock_client.bulk.return_value = mock_result
        mock_elasticsearch.return_value = mock_client

        ingester = ElasticIngester("https://localhost:9200", "api_key", "test_index", "id")
        batch = [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

        result = ingester.ingest(batch)

        assert mock_client.bulk.call_count == 1
        assert result == mock_result

    @patch("undatum.cmds.ingester.elastic.Elasticsearch")
    def test_elastic_ingester_ingest_missing_doc_id(self, mock_elasticsearch):
        """Test Elasticsearch ingestion with missing document ID field."""
        mock_client = MagicMock()
        mock_elasticsearch.return_value = mock_client

        ingester = ElasticIngester("https://localhost:9200", "api_key", "test_index", "id")
        batch = [{"name": "Alice"}, {"id": "2", "name": "Bob"}]  # First doc missing 'id'

        ingester.ingest(batch)

        # Should only process document with 'id' field
        assert mock_client.bulk.call_count == 1
        # Check that only one document was included
        call_args = mock_client.bulk.call_args
        operations = call_args[1]["operations"]
        assert len([op for op in operations if "index" in op]) == 1

    @patch("undatum.cmds.ingester.elastic.Elasticsearch")
    @patch("undatum.cmds.ingester.elastic.time.sleep")
    def test_elastic_ingester_ingest_retry_success(self, mock_sleep, mock_elasticsearch):
        """Test Elasticsearch ingestion with retry after transient failure."""
        mock_client = MagicMock()
        mock_result = {"errors": False, "items": []}

        # First call fails, second succeeds
        mock_client.bulk.side_effect = [Exception("Connection error"), mock_result]
        mock_elasticsearch.return_value = mock_client

        ingester = ElasticIngester("https://localhost:9200", "api_key", "test_index", "id")
        batch = [{"id": "1", "name": "Alice"}]

        result = ingester.ingest(batch)

        assert mock_client.bulk.call_count == 2
        mock_sleep.assert_called_once_with(INITIAL_RETRY_DELAY)
        assert result == mock_result

    @patch("undatum.cmds.ingester.elastic.Elasticsearch")
    def test_elastic_ingester_ingest_with_errors(self, mock_elasticsearch):
        """Test Elasticsearch ingestion with some errors in bulk response."""
        mock_client = MagicMock()
        mock_result = {
            "errors": True,
            "items": [
                {"index": {"_id": "1", "status": 200}},
                {
                    "index": {
                        "_id": "2",
                        "status": 200,
                        "error": {"type": "mapper_parsing_exception"},
                    }
                },
            ],
        }
        mock_client.bulk.return_value = mock_result
        mock_elasticsearch.return_value = mock_client

        ingester = ElasticIngester("https://localhost:9200", "api_key", "test_index", "id")
        batch = [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]

        result = ingester.ingest(batch)

        assert result == mock_result
        mock_client.bulk.assert_called_once()


class TestIngester:
    """Test Ingester main class."""

    def test_ingester_init_default_batch_size(self):
        """Test Ingester initialization with default batch size."""
        ingester = Ingester()
        assert ingester.batch_size == DEFAULT_BATCH_SIZE

    def test_ingester_init_custom_batch_size(self):
        """Test Ingester initialization with custom batch size."""
        ingester = Ingester(batch_size=5000)
        assert ingester.batch_size == 5000

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_mongodb_basic(self, mock_mongo_ingester_class, sample_jsonl_file):
        """Test basic MongoDB ingestion."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
            {"id": "3", "name": "Charlie"},
        ]

        ingester = Ingester(batch_size=2)
        options = {"dbtype": "mongodb", "drop": False, "skip": None, "totals": False}

        ingester.ingest_single(
            sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
        )

        # Should process 3 records in 2 batches (2 + 1)
        assert mock_processor.ingest.call_count == 2

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_flatten_nested(self, mock_mongo_ingester_class, tmp_path):
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}
        src = tmp_path / "nested.jsonl"
        src.write_text(
            '{"name": "TJK", "capital_city": {"lat": 38.56, "lon": 68.77}}\n',
            encoding="utf8",
        )
        Ingester(batch_size=10).ingest_single(
            str(src),
            "mongodb://localhost:27017",
            "testdb",
            "testcoll",
            {
                "dbtype": "mongodb",
                "flatten_nested": True,
                "drop": False,
                "skip": None,
                "totals": False,
            },
        )
        rows = []
        for call in mock_processor.ingest.call_args_list:
            rows.extend(call[0][0])
        assert rows
        assert rows[0]["capital_city.lat"] == 38.56
        assert rows[0]["name"] == "TJK"

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_mongodb_with_drop(self, mock_mongo_ingester_class, sample_jsonl_file):
        """Test MongoDB ingestion with drop option."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "mongodb",
            "drop": True,  # Fixed: was 'dro[]'
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
        )

        # Verify drop was called (collection.drop() is called in MongoIngester.__init__)
        mock_mongo_ingester_class.assert_called_once()
        call_kwargs = mock_mongo_ingester_class.call_args[1]
        assert call_kwargs["do_drop"] is True

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_mongodb_with_timeout(self, mock_mongo_ingester_class, sample_jsonl_file):
        """Test MongoDB ingestion with timeout option."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {"dbtype": "mongodb", "drop": False, "skip": None, "totals": False, "timeout": 30}

        ingester.ingest_single(
            sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
        )

        # Verify timeout was passed
        call_kwargs = mock_mongo_ingester_class.call_args[1]
        assert call_kwargs["timeout"] == 30

    @patch("undatum.cmds.ingester.core.ElasticIngester")
    def test_ingest_single_elasticsearch_basic(
        self, mock_elastic_ingester_class, sample_jsonl_file
    ):
        """Test basic Elasticsearch ingestion."""
        mock_processor = MagicMock()
        mock_elastic_ingester_class.return_value = mock_processor
        mock_processor.client.info.return_value = {"version": {"number": "8.0"}}

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]

        ingester = Ingester()
        options = {
            "dbtype": "elasticsearch",
            "api_key": "test_key",
            "doc_id": "id",
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file, "https://localhost:9200", "testdb", "test_index", options
        )

        assert mock_processor.ingest.call_count >= 1

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_with_skip(self, mock_mongo_ingester_class, sample_jsonl_file):
        """Test ingestion with skip option."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
            {"id": "3", "name": "Charlie"},
        ]

        ingester = Ingester()
        options = {
            "dbtype": "mongodb",
            "drop": False,
            "skip": 1,  # Skip first record
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
        )

        # Should process 2 records (skipped first one)
        assert mock_processor.ingest.call_count >= 1

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_batch_failure_continues(
        self, mock_mongo_ingester_class, sample_jsonl_file
    ):
        """Test that ingestion continues after batch failure."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.return_value = {"version": "5.0"}

        # First batch fails, second succeeds
        mock_processor.ingest.side_effect = [Exception("Batch error"), None]

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
            {"id": "3", "name": "Charlie"},
        ]

        ingester = Ingester(batch_size=2)
        options = {"dbtype": "mongodb", "drop": False, "skip": None, "totals": False}

        # Later batches are still loaded; the failure is reported at the end (exit code 3).
        from undatum.common.errors import DatabaseError

        with pytest.raises(DatabaseError, match="rows were not loaded"):
            ingester.ingest_single(
                sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
            )

        # Should have attempted both batches
        assert mock_processor.ingest.call_count == 2

    @patch("undatum.cmds.ingester.core.MongoIngester")
    def test_ingest_single_connection_validation_failure(
        self, mock_mongo_ingester_class, sample_jsonl_file
    ):
        """Test that connection validation failure raises error."""
        mock_processor = MagicMock()
        mock_mongo_ingester_class.return_value = mock_processor
        mock_processor.client.server_info.side_effect = Exception("Connection failed")

        MagicMock()

        ingester = Ingester()
        options = {"dbtype": "mongodb", "drop": False, "skip": None, "totals": False}

        with pytest.raises(Exception, match="Connection failed"):
            ingester.ingest_single(
                sample_jsonl_file, "mongodb://localhost:27017", "testdb", "testcoll", options
            )

    def test_ingest_single_unsupported_dbtype(self, sample_jsonl_file):
        """Test that unsupported database type raises ValidationError."""
        from undatum.common.errors import ValidationError

        ingester = Ingester()
        options = {"dbtype": "unsupported", "drop": False}

        with pytest.raises(ValidationError, match="Unsupported database type"):
            ingester.ingest_single(sample_jsonl_file, "uri://test", "testdb", "testcoll", options)

    @patch("undatum.cmds.ingester.Ingester.ingest_single")
    def test_ingest_multiple_files(self, mock_ingest_single):
        """Test ingestion of multiple files."""
        ingester = Ingester()
        files = ["file1.jsonl", "file2.jsonl", "file3.jsonl"]
        options = {"dbtype": "mongodb"}

        ingester.ingest(files, "mongodb://localhost:27017", "testdb", "testcoll", options)

        assert mock_ingest_single.call_count == 3
        for file in files:
            mock_ingest_single.assert_any_call(
                file, "mongodb://localhost:27017", "testdb", "testcoll", options
            )


class TestDuckDBIngester:
    """Test DuckDBIngester class."""

    def test_duckdb_ingester_init_file(self):
        """Test DuckDBIngester initialization with file database."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable")

        assert ingester.table == "testtable"
        assert ingester.mode == "append"
        assert ingester.is_memory is True
        ingester.close()

    def test_duckdb_ingester_init_with_mode(self):
        """Test DuckDBIngester initialization with mode."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable", mode="upsert", upsert_key="id")

        assert ingester.mode == "upsert"
        assert ingester.upsert_key == "id"
        ingester.close()

    def test_duckdb_ingester_init_with_create_table(self):
        """Test DuckDBIngester initialization with create_table."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable", create_table=True)

        assert ingester.create_table is True
        ingester.close()

    def test_duckdb_ingester_parse_uri(self):
        """Test DuckDB URI parsing."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "test")

        # Test various URI formats
        assert ingester._parse_uri("duckdb:///path/to/db.db") == "path/to/db.db"
        assert ingester._parse_uri("duckdb:///:memory:") == ":memory:"
        assert ingester._parse_uri("duckdb://:memory:") == ":memory:"

        ingester.close()

    def test_duckdb_ingester_schema_inference(self):
        """Test DuckDB schema inference."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "test")

        batch = [
            {"id": 1, "name": "Alice", "age": 30, "active": True},
            {"id": 2, "name": "Bob", "age": 25, "active": False},
        ]

        schema = ingester._infer_schema(batch)

        assert len(schema) == 4
        schema_dict = dict(schema)
        assert "id" in schema_dict
        assert "name" in schema_dict
        assert "age" in schema_dict
        assert "active" in schema_dict
        assert schema_dict["active"] == "BOOLEAN"
        assert schema_dict["id"] == "BIGINT"

        ingester.close()

    def test_duckdb_ingester_create_table(self):
        """Test DuckDB table creation."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable", create_table=True)

        batch = [{"id": 1, "name": "Alice"}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Verify table exists
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        assert result[0] == 0  # Table exists but is empty

        ingester.close()

    def test_duckdb_ingester_insert_batch(self):
        """Test DuckDB batch insertion."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable", create_table=True)

        # Create table first
        batch = [{"id": 1, "name": "Alice"}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Insert batch
        ingester._insert_batch(batch)

        # Verify data
        result = ingester.conn.execute("SELECT * FROM testtable").fetchall()
        assert len(result) == 1
        assert result[0][0] == 1  # id
        assert result[0][1] == "Alice"  # name

        ingester.close()

    def test_duckdb_ingester_upsert(self):
        """Test DuckDB upsert operations."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester(
            "duckdb:///:memory:", "testtable", mode="upsert", upsert_key="id", create_table=True
        )

        # Create table first
        batch = [{"id": 1, "name": "Alice", "age": 30}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Insert initial record
        ingester._insert_batch(batch)

        # Upsert with same id but different name
        batch2 = [{"id": 1, "name": "Alice Updated", "age": 31}]
        ingester._insert_with_upsert(batch2)

        # Verify update
        result = ingester.conn.execute("SELECT * FROM testtable WHERE id = 1").fetchone()
        assert result[1] == "Alice Updated"  # name updated
        assert result[2] == 31  # age updated

        ingester.close()

    def test_duckdb_ingester_ingest_with_create_table(self):
        """Test DuckDB ingestion with auto-create table."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester("duckdb:///:memory:", "testtable", create_table=True)

        batch = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        ingester.ingest(batch)

        # Verify data
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        assert result[0] == 2

        ingester.close()

    def test_duckdb_ingester_replace_mode(self):
        """Test DuckDB replace mode."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester(
            "duckdb:///:memory:", "testtable", mode="replace", create_table=True
        )

        # First batch
        batch1 = [{"id": 1, "name": "Alice"}]
        ingester.ingest(batch1)

        # Second batch (should replace)
        batch2 = [{"id": 2, "name": "Bob"}]
        ingester.ingest(batch2)

        # Verify only second batch exists (replace mode deletes on first batch)
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        # In replace mode, first batch is deleted, then second batch is inserted
        assert result[0] == 1

        ingester.close()

    def test_duckdb_ingester_appender(self):
        """Test DuckDB Appender API."""
        from undatum.cmds.ingester import DuckDBIngester

        ingester = DuckDBIngester(
            "duckdb:///:memory:", "testtable", use_appender=True, create_table=True
        )

        # Create table first
        batch = [{"id": 1, "name": "Alice"}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Use appender
        ingester._use_appender(batch)

        # Close appender
        if ingester._appender:
            ingester._appender.close()

        # Verify data
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        assert result[0] == 1

        ingester.close()


class TestIngesterDuckDB:
    """Test Ingester class with DuckDB."""

    def test_ingest_single_duckdb_basic(self, sample_jsonl_file):
        """Test basic DuckDB ingestion."""
        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]

        ingester = Ingester()
        options = {
            "dbtype": "duckdb",
            "mode": "append",
            "create_table": False,
            "skip": None,
            "totals": False,
        }

        # The table does not exist and create_table is off: every row fails, which is an error.
        from undatum.common.errors import DatabaseError

        with pytest.raises(DatabaseError, match="rows were not loaded"):
            ingester.ingest_single(
                sample_jsonl_file, "duckdb:///:memory:", "testdb", "testtable", options
            )

    def test_ingest_single_duckdb_with_create_table(self, sample_jsonl_file):
        """Test DuckDB ingestion with auto-create table."""
        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "duckdb",
            "mode": "append",
            "create_table": True,
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file, "duckdb:///:memory:", "testdb", "testtable", options
        )

        # Verify no exceptions


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="psycopg2 not available")
class TestPostgresIngester:
    """Test PostgresIngester class."""

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    def test_postgres_ingester_init(self, mock_pool_class):
        """Test PostgresIngester initialization."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable"
        )

        assert ingester.table == "testtable"
        assert ingester.mode == "append"
        mock_pool_class.assert_called_once()

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    def test_postgres_ingester_init_with_mode(self, mock_pool_class):
        """Test PostgresIngester initialization with mode."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb",
            "testdb",
            "testtable",
            mode="upsert",
            upsert_key="id",
        )

        assert ingester.mode == "upsert"
        assert ingester.upsert_key == "id"

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    def test_postgres_ingester_init_with_create_table(self, mock_pool_class):
        """Test PostgresIngester initialization with create_table."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable", create_table=True
        )

        assert ingester.create_table is True

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    @patch("undatum.cmds.ingester.PostgresIngester._get_connection")
    @patch("undatum.cmds.ingester.PostgresIngester._put_connection")
    def test_postgres_ingester_copy_from(self, mock_put_conn, mock_get_conn, mock_pool_class):
        """Test PostgreSQL COPY FROM bulk loading."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable"
        )
        ingester._table_columns = ["id", "name"]

        batch = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        ingester._copy_from_csv(batch, mock_conn)

        mock_cursor.copy_expert.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_put_conn.assert_called_once_with(mock_conn)

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    @patch("undatum.cmds.ingester.PostgresIngester._get_connection")
    @patch("undatum.cmds.ingester.PostgresIngester._put_connection")
    def test_postgres_ingester_upsert(self, mock_put_conn, mock_get_conn, mock_pool_class):
        """Test PostgreSQL upsert with INSERT ... ON CONFLICT."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb",
            "testdb",
            "testtable",
            mode="upsert",
            upsert_key="id",
        )

        batch = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        ingester._insert_with_upsert(batch, mock_conn)

        from undatum.cmds.ingester import execute_values

        execute_values.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    @patch("undatum.cmds.ingester.PostgresIngester._get_connection")
    @patch("undatum.cmds.ingester.PostgresIngester._put_connection")
    def test_postgres_ingester_schema_inference(
        self, mock_put_conn, mock_get_conn, mock_pool_class
    ):
        """Test PostgreSQL schema inference."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable"
        )

        batch = [
            {"id": 1, "name": "Alice", "age": 30, "active": True},
            {"id": 2, "name": "Bob", "age": 25, "active": False},
        ]

        schema = ingester._infer_schema(batch)

        assert len(schema) == 4
        schema_dict = dict(schema)
        assert "id" in schema_dict
        assert "name" in schema_dict
        assert "age" in schema_dict
        assert "active" in schema_dict
        assert schema_dict["active"] == "BOOLEAN"

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    def test_postgres_ingester_parse_uri(self, mock_pool_class):
        """Test PostgreSQL URI parsing."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        ingester = PostgresIngester(
            "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable"
        )

        params = ingester._parse_uri("postgresql://user:pass@localhost:5432/mydb")
        assert params["user"] == "user"
        assert params["password"] == "pass"
        assert params["host"] == "localhost"
        assert params["port"] == 5432
        assert params["database"] == "mydb"

    @patch("undatum.cmds.ingester.postgres.pool.ThreadedConnectionPool")
    def test_postgres_ingester_missing_psycopg2(self, mock_pool_class):
        """Test that ImportError is raised when psycopg2 is not available."""
        # Temporarily set PSYCOPG2_AVAILABLE to False
        from undatum.cmds import ingester

        original_value = ingester.PSYCOPG2_AVAILABLE
        ingester.PSYCOPG2_AVAILABLE = False

        try:
            with pytest.raises(ImportError, match="psycopg2 is required"):
                PostgresIngester(
                    "postgresql://user:pass@localhost:5432/testdb", "testdb", "testtable"
                )
        finally:
            ingester.PSYCOPG2_AVAILABLE = original_value


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="psycopg2 not available")
class TestIngesterPostgreSQL:
    """Test Ingester class with PostgreSQL."""

    @patch("undatum.cmds.ingester.core.PostgresIngester")
    def test_ingest_single_postgresql_basic(self, mock_postgres_ingester_class, sample_jsonl_file):
        """Test basic PostgreSQL ingestion."""
        mock_processor = MagicMock()
        mock_postgres_ingester_class.return_value = mock_processor

        # Mock connection pool methods
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_processor._get_connection.return_value = mock_conn
        mock_processor._put_connection = MagicMock()

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]

        ingester = Ingester()
        options = {
            "dbtype": "postgresql",
            "mode": "append",
            "create_table": False,
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file,
            "postgresql://user:pass@localhost:5432/testdb",
            "testdb",
            "testtable",
            options,
        )

        assert mock_postgres_ingester_class.called
        call_kwargs = mock_postgres_ingester_class.call_args[1]
        assert call_kwargs["db"] == "testdb"
        assert call_kwargs["table"] == "testtable"
        assert call_kwargs["mode"] == "append"

    @patch("undatum.cmds.ingester.core.PostgresIngester")
    def test_ingest_single_postgresql_with_create_table(
        self, mock_postgres_ingester_class, sample_jsonl_file
    ):
        """Test PostgreSQL ingestion with auto-create table."""
        mock_processor = MagicMock()
        mock_postgres_ingester_class.return_value = mock_processor

        # Mock connection pool methods
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_processor._get_connection.return_value = mock_conn
        mock_processor._put_connection = MagicMock()

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "postgresql",
            "mode": "append",
            "create_table": True,
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file,
            "postgresql://user:pass@localhost:5432/testdb",
            "testdb",
            "testtable",
            options,
        )

        call_kwargs = mock_postgres_ingester_class.call_args[1]
        assert call_kwargs["create_table"] is True

    @patch("undatum.cmds.ingester.core.PostgresIngester")
    def test_ingest_single_postgresql_with_upsert(
        self, mock_postgres_ingester_class, sample_jsonl_file
    ):
        """Test PostgreSQL ingestion with upsert mode."""
        mock_processor = MagicMock()
        mock_postgres_ingester_class.return_value = mock_processor

        # Mock connection pool methods
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_processor._get_connection.return_value = mock_conn
        mock_processor._put_connection = MagicMock()

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "postgresql",
            "mode": "upsert",
            "upsert_key": "id",
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file,
            "postgresql://user:pass@localhost:5432/testdb",
            "testdb",
            "testtable",
            options,
        )

        call_kwargs = mock_postgres_ingester_class.call_args[1]
        assert call_kwargs["mode"] == "upsert"
        assert call_kwargs["upsert_key"] == "id"


@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="pymysql not available")
class TestMySQLIngester:
    """Test MySQLIngester class."""

    @patch("undatum.cmds.ingester.mysql_backend.pymysql.connect")
    def test_mysql_ingester_init(self, mock_connect):
        """Test MySQLIngester initialization."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        ingester = MySQLIngester("mysql://user:pass@localhost:3306/testdb", "testdb", "testtable")

        assert ingester.table == "testtable"
        assert ingester.mode == "append"
        ingester.close()

    @patch("undatum.cmds.ingester.mysql_backend.pymysql.connect")
    def test_mysql_ingester_init_with_mode(self, mock_connect):
        """Test MySQLIngester initialization with mode."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        ingester = MySQLIngester(
            "mysql://user:pass@localhost:3306/testdb",
            "testdb",
            "testtable",
            mode="upsert",
            upsert_key="id",
        )

        assert ingester.mode == "upsert"
        assert ingester.upsert_key == "id"
        ingester.close()

    @patch("undatum.cmds.ingester.mysql_backend.pymysql.connect")
    def test_mysql_ingester_parse_uri(self, mock_connect):
        """Test MySQL URI parsing."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        ingester = MySQLIngester("mysql://user:pass@localhost:3306/testdb", "testdb", "test")

        params = ingester._parse_uri("mysql://user:pass@localhost:3306/mydb")
        assert params["user"] == "user"
        assert params["password"] == "pass"
        assert params["host"] == "localhost"
        assert params["port"] == 3306
        assert params["database"] == "mydb"

        ingester.close()

    @patch("undatum.cmds.ingester.mysql_backend.pymysql.connect")
    def test_mysql_ingester_missing_pymysql(self, mock_connect):
        """Test that ImportError is raised when pymysql is not available."""
        from undatum.cmds import ingester

        original_value = ingester.PYMYSQL_AVAILABLE
        ingester.PYMYSQL_AVAILABLE = False

        try:
            with pytest.raises(ImportError, match="pymysql is required"):
                MySQLIngester("mysql://user:pass@localhost:3306/testdb", "testdb", "testtable")
        finally:
            ingester.PYMYSQL_AVAILABLE = original_value


class TestSQLiteIngester:
    """Test SQLiteIngester class."""

    def test_sqlite_ingester_init_file(self):
        """Test SQLiteIngester initialization with file database."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "testtable")

        assert ingester.table == "testtable"
        assert ingester.mode == "append"
        assert ingester.is_memory is True
        ingester.close()

    def test_sqlite_ingester_init_with_mode(self):
        """Test SQLiteIngester initialization with mode."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "testtable", mode="upsert", upsert_key="id")

        assert ingester.mode == "upsert"
        assert ingester.upsert_key == "id"
        ingester.close()

    def test_sqlite_ingester_parse_uri(self):
        """Test SQLite URI parsing."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "test")

        # Test various URI formats
        assert ingester._parse_uri("sqlite:///path/to/db.db") == "path/to/db.db"
        assert ingester._parse_uri("sqlite:///:memory:") == ":memory:"
        assert ingester._parse_uri("sqlite://:memory:") == ":memory:"

        ingester.close()

    def test_sqlite_ingester_schema_inference(self):
        """Test SQLite schema inference."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "test")

        batch = [
            {"id": 1, "name": "Alice", "age": 30, "active": True},
            {"id": 2, "name": "Bob", "age": 25, "active": False},
        ]

        schema = ingester._infer_schema(batch)

        assert len(schema) == 4
        schema_dict = dict(schema)
        assert "id" in schema_dict
        assert "name" in schema_dict
        assert "age" in schema_dict
        assert "active" in schema_dict
        assert schema_dict["active"] == "INTEGER"  # SQLite uses INTEGER for booleans
        assert schema_dict["id"] == "INTEGER"

        ingester.close()

    def test_sqlite_ingester_create_table(self):
        """Test SQLite table creation."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "testtable", create_table=True)

        batch = [{"id": 1, "name": "Alice"}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Verify table exists
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        assert result[0] == 0  # Table exists but is empty

        ingester.close()

    def test_sqlite_ingester_insert_batch(self):
        """Test SQLite batch insertion."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "testtable", create_table=True)

        # Create table first
        batch = [{"id": 1, "name": "Alice"}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Insert batch
        ingester._insert_batch(batch)

        # Verify data
        result = ingester.conn.execute("SELECT * FROM testtable").fetchall()
        assert len(result) == 1
        assert result[0][0] == 1  # id
        assert result[0][1] == "Alice"  # name

        ingester.close()

    def test_sqlite_ingester_upsert(self):
        """Test SQLite upsert operations."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester(
            "sqlite:///:memory:", "testtable", mode="upsert", upsert_key="id", create_table=True
        )

        # Create table first
        batch = [{"id": 1, "name": "Alice", "age": 30}]
        schema = ingester._infer_schema(batch)
        ingester._create_table(schema)

        # Insert initial record
        ingester._insert_batch(batch)

        # Upsert with same id but different name
        batch2 = [{"id": 1, "name": "Alice Updated", "age": 31}]
        ingester._insert_with_upsert(batch2)

        # Verify update
        result = ingester.conn.execute("SELECT * FROM testtable WHERE id = 1").fetchone()
        assert result[1] == "Alice Updated"  # name updated
        assert result[2] == 31  # age updated

        ingester.close()

    def test_sqlite_ingester_ingest_with_create_table(self):
        """Test SQLite ingestion with auto-create table."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester("sqlite:///:memory:", "testtable", create_table=True)

        batch = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        ingester.ingest(batch)

        # Verify data
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        assert result[0] == 2

        ingester.close()

    def test_sqlite_ingester_replace_mode(self):
        """Test SQLite replace mode."""
        from undatum.cmds.ingester import SQLiteIngester

        ingester = SQLiteIngester(
            "sqlite:///:memory:", "testtable", mode="replace", create_table=True
        )

        # First batch
        batch1 = [{"id": 1, "name": "Alice"}]
        ingester.ingest(batch1)

        # Second batch (should replace)
        batch2 = [{"id": 2, "name": "Bob"}]
        ingester.ingest(batch2)

        # Verify only second batch exists (replace mode deletes on first batch)
        result = ingester.conn.execute("SELECT COUNT(*) FROM testtable").fetchone()
        # In replace mode, first batch is deleted, then second batch is inserted
        assert result[0] == 1

        ingester.close()

    def test_sqlite_ingester_file_database(self, tmp_path):
        """Test SQLite ingestion against a real file database URI."""
        import sqlite3

        from undatum.cmds.ingester import SQLiteIngester

        db_path = tmp_path / "people.db"
        ingester = SQLiteIngester(f"sqlite:///{db_path}", "people", create_table=True)
        ingester.ingest([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
        ingester.close()

        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT id, name FROM people ORDER BY id").fetchall()
        finally:
            conn.close()
        assert rows == [(1, "Alice"), (2, "Bob")]


@pytest.mark.skipif(not MYSQL_AVAILABLE, reason="pymysql not available")
class TestIngesterMySQL:
    """Test Ingester class with MySQL."""

    @patch("undatum.cmds.ingester.mysql_backend.pymysql.connect")
    def test_ingest_single_mysql_basic(self, mock_connect, sample_jsonl_file):
        """Test basic MySQL ingestion."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "mysql",
            "mode": "append",
            "create_table": False,
            "skip": None,
            "totals": False,
        }

        ingester.ingest_single(
            sample_jsonl_file,
            "mysql://user:pass@localhost:3306/testdb",
            "testdb",
            "testtable",
            options,
        )

        # Verify connection was created
        assert mock_connect.called


class TestIngesterSQLite:
    """Test Ingester class with SQLite."""

    def test_ingest_single_sqlite_basic(self, sample_jsonl_file):
        """Test basic SQLite ingestion."""
        mock_iterable = MagicMock()
        mock_iterable.__iter__.return_value = [{"id": "1", "name": "Alice"}]

        ingester = Ingester()
        options = {
            "dbtype": "sqlite",
            "mode": "append",
            "create_table": False,
            "skip": None,
            "totals": False,
        }

        # The table does not exist and create_table is off: every row fails, which is an error.
        from undatum.common.errors import DatabaseError

        with pytest.raises(DatabaseError, match="rows were not loaded"):
            ingester.ingest_single(
                sample_jsonl_file, "sqlite:///:memory:", "testdb", "testtable", options
            )
