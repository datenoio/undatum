"""Tests for DuckDB configuration utilities."""

import os
import tempfile

import duckdb
import pytest

from undatum.common.duckdb_config import (
    EXTENSION_DIR_ENV,
    create_duckdb_connection,
    duckdb_connection,
    get_duckdb_config_from_options,
    load_extension,
    parse_memory_size,
)
from undatum.common.errors import ConfigurationError


class TestParseMemorySize:
    """Test parse_memory_size function."""

    def test_parse_memory_size_gb(self):
        """Test parsing GB memory size."""
        assert parse_memory_size("4GB") == 4 * 1024**3
        assert parse_memory_size("1GB") == 1024**3

    def test_parse_memory_size_mb(self):
        """Test parsing MB memory size."""
        assert parse_memory_size("512MB") == 512 * 1024**2
        assert parse_memory_size("1024MB") == 1024 * 1024**2

    def test_parse_memory_size_kb(self):
        """Test parsing KB memory size."""
        assert parse_memory_size("1024KB") == 1024 * 1024
        assert parse_memory_size("512KB") == 512 * 1024

    def test_parse_memory_size_bytes(self):
        """Test parsing bytes."""
        assert parse_memory_size("1024") == 1024
        assert parse_memory_size("1024B") == 1024

    def test_parse_memory_size_case_insensitive(self):
        """Test parsing is case insensitive."""
        assert parse_memory_size("4GB") == parse_memory_size("4gb")
        assert parse_memory_size("512MB") == parse_memory_size("512mb")

    def test_parse_memory_size_whitespace(self):
        """Test parsing with whitespace."""
        assert parse_memory_size(" 4GB ") == 4 * 1024**3
        # Space in middle is not supported
        with pytest.raises(ValueError, match="Invalid memory size format"):
            parse_memory_size("512 MB")

    def test_parse_memory_size_empty(self):
        """Test parsing empty string."""
        assert parse_memory_size("") == 0
        assert parse_memory_size(None) == 0

    def test_parse_memory_size_invalid(self):
        """Test parsing invalid format."""
        with pytest.raises(ValueError, match="Invalid memory size format"):
            parse_memory_size("invalid")
        with pytest.raises(ValueError, match="Invalid memory size format"):
            parse_memory_size("4TB")  # Unsupported unit


class TestCreateDuckdbConnection:
    """Test create_duckdb_connection function."""

    def test_create_duckdb_connection_default(self):
        """Test creating connection with defaults."""
        conn = create_duckdb_connection()
        assert conn is not None
        conn.close()

    def test_create_duckdb_connection_with_threads(self):
        """Test creating connection with thread count."""
        conn = create_duckdb_connection(threads=2)
        assert conn is not None
        conn.close()

    def test_create_duckdb_connection_with_memory(self):
        """Test creating connection with memory limit."""
        conn = create_duckdb_connection(memory="1GB")
        assert conn is not None
        limit = conn.execute("SELECT current_setting('memory_limit')").fetchone()[0]
        # 1GB parsed as 1024**3 bytes; DuckDB may report GiB or byte form.
        assert limit is not None
        conn.close()

        conn = create_duckdb_connection(memory="512MB")
        assert conn is not None
        conn.close()

        # Bare byte counts must get a unit suffix for DuckDB.
        conn = create_duckdb_connection(memory="1048576")
        assert conn is not None
        conn.close()

        # Test that invalid memory format doesn't crash
        conn = create_duckdb_connection(memory="invalid")
        assert conn is not None
        conn.close()

    def test_create_duckdb_connection_with_temp_dir(self):
        """Test creating connection with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            conn = create_duckdb_connection(temp_dir=tmpdir)
            assert conn is not None
            conn.close()

    def test_create_duckdb_connection_with_database(self):
        """Test creating connection with database path."""
        # Use a non-existent file path (DuckDB will create it)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            conn = create_duckdb_connection(database=db_path)
            assert conn is not None
            assert os.path.exists(db_path)
            conn.close()

    def test_create_duckdb_connection_invalid_threads(self):
        """Test creating connection with invalid thread count."""
        with pytest.raises(ValueError, match="Thread count must be >= 1"):
            create_duckdb_connection(threads=0)

    def test_create_duckdb_connection_invalid_memory(self):
        """Test creating connection with invalid memory format."""
        # Should not raise, just log warning
        conn = create_duckdb_connection(memory="invalid")
        assert conn is not None
        conn.close()

    def test_create_duckdb_connection_nonexistent_temp_dir(self):
        """Test creating connection with non-existent temp directory."""
        # Should create directory
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, "new_temp")
            conn = create_duckdb_connection(temp_dir=temp_path)
            assert conn is not None
            assert os.path.exists(temp_path)
            conn.close()


class TestGetDuckdbConfigFromOptions:
    """Test get_duckdb_config_from_options function."""

    def test_get_duckdb_config_from_options_all(self):
        """Test extracting all DuckDB options."""
        options = {
            "duckdb_threads": 4,
            "duckdb_memory": "2GB",
            "duckdb_temp_dir": "/tmp/duckdb",
        }
        config = get_duckdb_config_from_options(options)
        assert config == {
            "threads": 4,
            "memory": "2GB",
            "temp_dir": "/tmp/duckdb",
        }

    def test_get_duckdb_config_from_options_partial(self):
        """Test extracting partial DuckDB options."""
        options = {
            "duckdb_threads": 2,
            "other_option": "value",
        }
        config = get_duckdb_config_from_options(options)
        assert config == {"threads": 2}

    def test_get_duckdb_config_from_options_empty(self):
        """Test extracting from empty options."""
        options = {}
        config = get_duckdb_config_from_options(options)
        assert config == {}

    def test_get_duckdb_config_from_options_none(self):
        """Test extracting from None options."""
        options = {"other_option": "value"}
        config = get_duckdb_config_from_options(options)
        assert config == {}

    def test_generic_threads_fallback(self):
        """--threads should be used when duckdb_threads is not set."""
        config = get_duckdb_config_from_options({"threads": 8})
        assert config == {"threads": 8}

    def test_duckdb_threads_takes_precedence(self):
        """duckdb_threads should win over the generic threads option."""
        config = get_duckdb_config_from_options({"threads": 8, "duckdb_threads": 2})
        assert config == {"threads": 2}

    def test_none_threads_ignored(self):
        """None values for thread options should not produce config entries."""
        config = get_duckdb_config_from_options({"threads": None, "duckdb_threads": None})
        assert config == {}


class TestOfflineExtensions:
    """Preinstalled extensions and the error for a missing one."""

    def test_extension_directory_from_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv(EXTENSION_DIR_ENV, str(tmp_path))
        conn = create_duckdb_connection()
        setting = conn.execute("SELECT current_setting('extension_directory')").fetchall()
        assert setting == [(str(tmp_path),)]

    def test_installed_extension_loads(self):
        load_extension(create_duckdb_connection(), "json")  # statically linked

    def test_missing_extension_offline_is_a_configuration_error(self):
        class Offline:
            def load_extension(self, name):
                raise duckdb.IOException(f"Extension {name} not found")

            def install_extension(self, name):
                raise duckdb.HTTPException("Could not reach extensions.duckdb.org")

        with pytest.raises(ConfigurationError) as info:
            load_extension(Offline(), "excel")
        assert info.value.exit_code == 2
        assert "'excel'" in info.value.message
        assert EXTENSION_DIR_ENV in info.value.message


def _settings(conn):
    threads, memory = conn.execute(
        "SELECT current_setting('threads'), current_setting('memory_limit')"
    ).fetchall()[0]
    return int(threads), memory


class TestWorkloads:
    """Connection defaults per kind of work; explicit --duckdb-* options win."""

    def test_row_wise_is_bounded(self):
        threads, memory = _settings(duckdb_connection(workload="row"))
        assert threads == 1
        assert memory == _settings(create_duckdb_connection(memory="256MB"))[1]

    def test_ordered_keeps_duckdb_memory_limit(self):
        threads, memory = _settings(duckdb_connection(workload="ordered"))
        assert threads == 1
        assert memory == _settings(duckdb.connect())[1]

    def test_aggregate_uses_every_core(self):
        assert _settings(duckdb_connection()) == _settings(duckdb.connect())

    def test_options_win(self):
        options = {"duckdb_threads": 3, "duckdb_memory": "2GB"}
        threads, memory = _settings(duckdb_connection(options, workload="row"))
        assert threads == 3
        assert memory == _settings(create_duckdb_connection(memory="2GB"))[1]


@pytest.mark.parametrize(
    "args",
    [
        ["stats", "-O", "json"],
        ["count"],
        ["quality", "--json"],
        ["schema-drift", "--json"],
        ["frequency", "-f", "name"],
    ],
)
def test_commands_pass_duckdb_options_to_their_connection(tmp_path, monkeypatch, args):
    """--duckdb-memory reaches the DuckDB connection of every DuckDB-backed command."""
    from typer.testing import CliRunner

    import undatum.common.duckdb_config as config
    from undatum.core import app

    seen = []
    real = config.create_duckdb_connection

    def spy(**kwargs):
        seen.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(config, "create_duckdb_connection", spy)
    # selector binds the factory when it is imported, which may be before this test.
    from undatum.cmds import selector

    monkeypatch.setattr(selector, "create_duckdb_connection", spy)
    source = tmp_path / "data.csv"
    source.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf8")
    command = [args[0], str(source), *args[1:], "--duckdb-memory", "2GB"]
    if args[0] == "schema-drift":
        command += ["--baseline", str(source)]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output
    assert seen, "no DuckDB connection was made"
    assert all(kwargs.get("memory") == "2GB" for kwargs in seen), seen
