"""Tests for TUI services (no Textual required)."""

from pathlib import Path

import pytest

from undatum.common.errors import FileNotFoundError, ValidationError
from undatum.tui.services import TuiServices, clamp_sample_limit
from undatum.tui.session import DEFAULT_SAMPLE_LIMIT, MAX_SAMPLE_LIMIT


def test_clamp_sample_limit_default():
    assert clamp_sample_limit(None) == DEFAULT_SAMPLE_LIMIT


def test_clamp_sample_limit_caps_at_max():
    assert clamp_sample_limit(MAX_SAMPLE_LIMIT + 100) == MAX_SAMPLE_LIMIT


def test_clamp_sample_limit_rejects_zero():
    with pytest.raises(ValidationError):
        clamp_sample_limit(0)


def test_load_sample_csv(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    assert session.headers == ["name", "age", "city"]
    assert len(session.sample_rows) == 2
    assert session.truncated is False
    assert session.sample_rows[0]["name"] == "Alice"
    assert "undatum table" in (session.last_cli or "")
    rows = TuiServices().grid_rows(session)
    assert rows[0][0] == "Alice"
    assert rows[1][0] == "Bob"


def test_load_sample_flatten_nested(tmp_path):
    src = tmp_path / "nested.jsonl"
    src.write_text(
        '{"name": "TJK", "capital_city": {"lat": 38.56, "lon": 68.77}}\n',
        encoding="utf8",
    )
    session = TuiServices().load_sample(str(src), {"flatten_nested": True}, 200)
    assert "capital_city.lat" in session.headers
    assert "capital_city.lon" in session.headers
    assert session.sample_rows[0]["capital_city.lat"] == 38.56
    assert session.sample_rows[0]["name"] == "TJK"


def test_load_sample_respects_limit(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 1)
    assert len(session.sample_rows) == 1
    assert session.truncated is True
    assert session.sample_rows[0]["name"] == "Alice"


def test_load_sample_missing_file(tmp_path):
    missing = str(tmp_path / "no-such.csv")
    with pytest.raises(FileNotFoundError):
        TuiServices().load_sample(missing, {}, 10)


def test_apply_filter_keeps_matching_sample_rows(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    TuiServices().apply_filter(session, 'name == "Alice"')
    rows = TuiServices().grid_rows(session)
    assert len(rows) == 1
    assert rows[0][0] == "Alice"
    assert "select" in (session.last_cli or "")
    assert "--filter" in (session.last_cli or "")
    TuiServices().apply_filter(session, "")
    assert session.filter_expr is None
    assert len(TuiServices().grid_rows(session)) == 2


def test_apply_filter_rejects_invalid_expression(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    with pytest.raises(ValidationError):
        TuiServices().apply_filter(session, "name == (")


def test_frequency_on_sample_field(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    headers, rows, cli = TuiServices().frequency(session, "city")
    values = {row[0] for row in rows}
    assert "New York" in values
    assert "London" in values
    assert headers[0] == "city"
    assert "undatum frequency" in cli
    assert "--fields city" in cli


def test_export_view_writes_visible_rows(sample_csv_file, tmp_path):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    TuiServices().apply_filter(session, 'name == "Alice"')
    out = str(tmp_path / "out.jsonl")
    cli = TuiServices().export_view(session, out)
    text = Path(out).read_text()
    assert "Alice" in text
    assert "Bob" not in text
    assert "select" in cli
    assert "--output" in cli


def test_profile_uses_stats_processor(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    headers, rows, cli = TuiServices().profile(session)
    assert headers[0] == "Field"
    field_names = {row[0] for row in rows}
    assert "name" in field_names
    assert "undatum stats" in cli
    assert "undatum stats" in (session.last_cli or "")


def test_ensure_sql_limit_injects_when_missing():
    from undatum.tui.actions import DEFAULT_SQL_LIMIT
    from undatum.tui.services import ensure_sql_limit

    query, injected = ensure_sql_limit("SELECT * FROM data")
    assert injected is True
    assert f"LIMIT {DEFAULT_SQL_LIMIT}" in query
    query, injected = ensure_sql_limit("SELECT * FROM data LIMIT 10")
    assert injected is False
    assert query == "SELECT * FROM data LIMIT 10"


def test_run_sql_uses_executor_and_default_limit(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    headers, rows, cli = TuiServices().run_sql(session, "SELECT * FROM data")
    assert "name" in headers
    values = {row[headers.index("name")] for row in rows}
    assert "Alice" in values
    assert "Bob" in values
    assert "undatum sql" in cli
    assert "LIMIT 500" in cli
    assert "# LIMIT 500 added" in cli


def test_run_sql_keeps_existing_limit(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    _headers, rows, cli = TuiServices().run_sql(session, "SELECT name FROM data LIMIT 1")
    assert len(rows) == 1
    assert "# LIMIT" not in cli


def test_palette_filter_and_cli_template(sample_csv_file):
    from undatum.tui.actions import filter_actions, get_action, render_cli

    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    matches = filter_actions("sql")
    assert any(action.id == "sql" for action in matches)
    profile = get_action("profile")
    assert profile is not None
    cli = render_cli(profile, session)
    assert "undatum stats" in cli
    assert session.source in cli


def test_recent_history_stores_paths_only(sample_csv_file, tmp_path):
    from undatum.tui.history import load_recent_paths, record_recent_path

    history = tmp_path / "tui-history.json"
    record_recent_path(sample_csv_file, history)
    other = tmp_path / "other.csv"
    other.write_text("a,b\n1,2\n")
    record_recent_path(str(other), history)
    paths = load_recent_paths(history)
    assert str(other.resolve()) == paths[0]
    assert Path(sample_csv_file).resolve().as_posix() in {Path(item).as_posix() for item in paths}
    text = history.read_text()
    assert "Alice" not in text
    assert "paths" in text


def test_convert_save_writes_full_file(sample_csv_file, tmp_path):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    out = str(tmp_path / "out.jsonl")
    cli = TuiServices().convert_save(session, out)
    text = Path(out).read_text()
    assert "Alice" in text
    assert "Bob" in text
    assert "undatum convert" in cli
    assert "--low-memory" in cli


def test_validate_sample_completeness(tmp_path):
    csv_path = tmp_path / "gappy.csv"
    csv_path.write_text("name,city\nAlice,\nBob,London\n")
    session = TuiServices().load_sample(str(csv_path), {}, 200)
    headers, rows, cli = TuiServices().validate_sample(session)
    assert headers[0] == "Field"
    city = next(row for row in rows if row[0] == "city")
    assert city[2] == "1"
    assert "undatum validate" in cli
    assert "sample" in cli


def test_validate_sample_rules_file(sample_csv_file, tmp_path):
    rules = tmp_path / "rules.yaml"
    rules.write_text("rules:\n  - field: name\n    type: field\n    required: true\n")
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    _headers, rows, cli = TuiServices().validate_sample(session, str(rules))
    assert "--rules" in cli
    assert rows[0][2] == "ok"


def test_mask_preview_redacts_sample_field(sample_csv_file):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    _headers, rows, cli = TuiServices().mask_preview(session, "name")
    assert rows[0][0] == "***"
    assert "Alice" not in rows[0]
    assert "undatum mask" in cli


def test_mask_write_uses_masker(sample_csv_file, tmp_path):
    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    out = str(tmp_path / "masked.jsonl")
    cli = TuiServices().mask_write(session, out, "name")
    text = Path(out).read_text()
    assert "Alice" not in text
    assert "***" in text
    assert "--output" in cli


def test_export_pipeline_yaml(sample_csv_file, tmp_path):
    from undatum.common.pipeline_parser import PipelineSpec, validate_pipeline

    session = TuiServices().load_sample(sample_csv_file, {}, 200)
    TuiServices().apply_filter(session, 'name == "Alice"')
    spec = TuiServices().build_pipeline_spec(session)
    assert spec["steps"][0]["command"] == "convert"
    assert spec["steps"][1]["command"] == "select"
    assert spec["steps"][1]["args"]["filter"] == 'name == "Alice"'
    assert validate_pipeline(PipelineSpec(spec["steps"])) == []
    out = tmp_path / "pipeline.yml"
    cli = TuiServices().export_pipeline(session, str(out))
    text = out.read_text()
    assert "select" in text
    assert session.source in text
    assert "undatum pipeline run" in cli


def test_load_sample_opens_s3_via_open_path(monkeypatch):
    class FakeIterable:
        def __iter__(self):
            return iter([{"name": "Alice"}])

        def close(self):
            return None

    monkeypatch.setattr("undatum.tui.services.open_path", lambda *args, **kwargs: FakeIterable())
    session = TuiServices().load_sample("s3://bucket/data.csv", {}, 10)
    assert session.source == "s3://bucket/data.csv"
    assert session.sample_rows[0]["name"] == "Alice"


def test_load_sample_opens_gcs_via_open_path(monkeypatch):
    class FakeIterable:
        def __iter__(self):
            return iter([{"name": "Alice"}])

        def close(self):
            return None

    monkeypatch.setattr("undatum.tui.services.open_path", lambda *args, **kwargs: FakeIterable())
    session = TuiServices().load_sample("gs://bucket/data.csv", {}, 10)
    assert session.source == "gs://bucket/data.csv"
    assert session.sample_rows[0]["name"] == "Alice"


def test_load_sample_opens_azure_via_open_path(monkeypatch):
    class FakeIterable:
        def __iter__(self):
            return iter([{"name": "Alice"}])

        def close(self):
            return None

    monkeypatch.setattr("undatum.tui.services.open_path", lambda *args, **kwargs: FakeIterable())
    session = TuiServices().load_sample("az://container/data.csv", {}, 10)
    assert session.source == "az://container/data.csv"
    assert session.sample_rows[0]["name"] == "Alice"
