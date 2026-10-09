"""Tests for database query command."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from undatum.cmds.db_query import DatabaseQueryExecutor
from undatum.common.db_connection import DatabaseConnectionError


class TestDatabaseQueryExecutor:
    """Test DatabaseQueryExecutor class."""

    def test_init(self):
        """Test executor initialization."""
        executor = DatabaseQueryExecutor()
        assert executor is not None

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_jsonl_output(self, mock_parse_uri, mock_get_conn):
        """Test query with JSONL output."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice"), (2, "Bob")], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            output_path = tmp.name

        try:
            executor.query(
                "SELECT * FROM users",
                "sqlite://:memory:",
                output=output_path,
                output_format="jsonl",
            )

            # Verify query was executed
            mock_cursor.execute.assert_called_once_with("SELECT * FROM users")

            # Verify output file was created and has content
            assert os.path.exists(output_path)
            with open(output_path) as f:
                content = f.read()
                assert "Alice" in content
                assert "Bob" in content

            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_csv_output(self, mock_parse_uri, mock_get_conn):
        """Test query with CSV output."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice"), (2, "Bob")], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as tmp:
            output_path = tmp.name

        try:
            executor.query(
                "SELECT * FROM users", "sqlite://:memory:", output=output_path, output_format="csv"
            )

            # Verify output file was created
            assert os.path.exists(output_path)
            with open(output_path) as f:
                content = f.read()
                assert "id,name" in content
                assert "Alice" in content
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_parquet_output(self, mock_parse_uri, mock_get_conn):
        """Test query with Parquet output."""
        pd = pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice"), (2, "Bob")], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
            output_path = tmp.name

        try:
            executor.query(
                "SELECT * FROM users",
                "sqlite://:memory:",
                output=output_path,
                output_format="parquet",
            )

            df = pd.read_parquet(output_path)
            assert list(df.columns) == ["id", "name"]
            assert df["name"].tolist() == ["Alice", "Bob"]
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_stdout_output(self, mock_parse_uri, mock_get_conn):
        """Test query with stdout output."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchmany.side_effect = [[(1, "Alice")], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with patch("sys.stdout") as mock_stdout:
            executor.query(
                "SELECT * FROM users", "sqlite://:memory:", output=None, output_format="jsonl"
            )

            # Verify write was called on stdout
            assert mock_stdout.write.called

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_dict_rows(self, mock_parse_uri, mock_get_conn):
        """Test query with dictionary rows."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchmany.side_effect = [[{"id": 1, "name": "Alice"}], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            output_path = tmp.name

        try:
            executor.query(
                "SELECT * FROM users",
                "sqlite://:memory:",
                output=output_path,
                output_format="jsonl",
            )

            with open(output_path) as f:
                content = f.read()
                assert "Alice" in content
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_no_columns(self, mock_parse_uri, mock_get_conn):
        """Test query with no column description."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchmany.side_effect = [[(1, "Alice")], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            output_path = tmp.name

        try:
            executor.query(
                "SELECT * FROM users",
                "sqlite://:memory:",
                output=output_path,
                output_format="jsonl",
            )

            # Should infer column names from first row
            with open(output_path) as f:
                content = f.read()
                assert "column_0" in content or "column_1" in content
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_connection_error(self, mock_parse_uri):
        """Test query with connection error is wrapped in DatabaseError."""
        from undatum.common.errors import DatabaseError

        mock_parse_uri.side_effect = DatabaseConnectionError("Connection failed")

        executor = DatabaseQueryExecutor()

        with pytest.raises(DatabaseError, match="Invalid database URI"):
            executor.query("SELECT * FROM users", "invalid://uri", output_format="jsonl")

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_invalid_format(self, mock_parse_uri, mock_get_conn):
        """Test query with invalid output format."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        from undatum.common.errors import ValidationError

        with pytest.raises(ValidationError, match="Unsupported output format"):
            executor.query("SELECT * FROM users", "sqlite://:memory:", output_format="invalid")

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_postgresql_named_cursor(self, mock_parse_uri, mock_get_conn):
        """Test query with PostgreSQL named cursor."""
        mock_parse_uri.return_value = ("postgresql", {"host": "localhost"})

        mock_conn = MagicMock()
        mock_named_cursor = MagicMock()
        mock_named_cursor.description = [("id",), ("name",)]
        mock_named_cursor.fetchmany.side_effect = [[(1, "Alice")], []]

        mock_psycopg2 = MagicMock()
        mock_psycopg2.extras.RealDictCursor = MagicMock
        mock_conn.cursor.return_value = mock_named_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            output_path = tmp.name

        fake_modules = {"psycopg2": mock_psycopg2, "psycopg2.extras": mock_psycopg2.extras}
        try:
            with patch.dict(sys.modules, fake_modules):
                executor.query(
                    "SELECT * FROM users",
                    "postgresql://localhost/db",
                    output=output_path,
                    output_format="jsonl",
                )

            # Verify named cursor was used
            mock_conn.cursor.assert_called()
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("undatum.cmds.db_query.get_db_connection")
    @patch("undatum.cmds.db_query.parse_db_uri")
    def test_query_parquet_no_pandas(self, mock_parse_uri, mock_get_conn):
        """Test query with Parquet output when pandas is not available."""
        mock_parse_uri.return_value = ("sqlite", {"path": ":memory:"})

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        executor = DatabaseQueryExecutor()

        # A None entry in sys.modules makes "import pandas" raise ImportError.
        with patch.dict(sys.modules, {"pandas": None}), pytest.raises(ImportError):
            executor.query(
                "SELECT * FROM users",
                "sqlite://:memory:",
                output="test.parquet",
                output_format="parquet",
            )
