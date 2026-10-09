"""Pytest configuration and fixtures."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "benchmark: marks tests as benchmarks")
    config.addinivalue_line(
        "markers", "use_cli_config: allow reading undatum.yaml / env CLI defaults"
    )


@pytest.fixture(autouse=True)
def _isolate_cli_defaults(request, monkeypatch):
    """Keep developer/user config files from leaking into tests."""
    if request.node.get_closest_marker("use_cli_config"):
        return
    monkeypatch.setattr("undatum.common.app_config.get_cli_defaults", lambda: {})


try:
    import pytest_benchmark  # noqa: F401
except ImportError:

    @pytest.fixture
    def benchmark():
        """Skip benchmarks when pytest-benchmark is unavailable."""
        pytest.skip("pytest-benchmark is not installed")


# Default contents of the sample files. A test module sets ``SAMPLE_CSV`` / ``SAMPLE_JSONL``
# at module level when its assertions need other rows.
SAMPLE_CSV = "name,age,city\nAlice,30,New York\nBob,25,London\n"
SAMPLE_JSONL = (
    '{"name": "Alice", "age": 30, "city": "New York"}\n'
    '{"name": "Bob", "age": 25, "city": "London"}\n'
)


@pytest.fixture
def sample_csv_file(request, tmp_path):
    """``sample.csv`` with the test module's ``SAMPLE_CSV`` (default: two people)."""
    path = tmp_path / "sample.csv"
    path.write_text(getattr(request.module, "SAMPLE_CSV", SAMPLE_CSV))
    return str(path)


@pytest.fixture
def sample_jsonl_file(request, tmp_path):
    """``sample.jsonl`` with the test module's ``SAMPLE_JSONL`` (default: two people)."""
    path = tmp_path / "sample.jsonl"
    path.write_text(getattr(request.module, "SAMPLE_JSONL", SAMPLE_JSONL))
    return str(path)


@pytest.fixture
def semicolon_csv(tmp_path):
    """``orgs.csv``: semicolon-delimited, with quoted fields that contain commas."""
    path = tmp_path / "orgs.csv"
    path.write_text(
        'id;name;city\n1;"Acme, Inc";"New York"\n2;"Beta LLC";London\n',
        encoding="utf8",
    )
    return str(path)
