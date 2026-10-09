"""Tests for select command behavior."""

import json
from pathlib import Path

import pytest

from undatum import Dataset
from undatum.cmds.selector import Selector
from undatum.utils import select_fields


def read_jsonl(path: str) -> list[dict]:
    """Read JSONL file into list of dicts."""
    content = Path(path).read_text().splitlines()
    return [json.loads(line) for line in content if line.strip()]


def test_select_iterable_jsonl_output(sample_csv_file, tmp_path):
    output_file = tmp_path / "select_iterable.jsonl"
    options = {
        "fields": "name,city",
        "output": str(output_file),
        "engine": "iterable",
    }

    Selector().select(sample_csv_file, options)

    assert read_jsonl(str(output_file)) == [
        {"name": "Alice", "city": "New York"},
        {"name": "Bob", "city": "London"},
    ]


def test_select_duckdb_matches_iterable(sample_csv_file, tmp_path):
    iterable_output = tmp_path / "select_iterable.jsonl"
    duckdb_output = tmp_path / "select_duckdb.jsonl"

    Selector().select(
        sample_csv_file,
        {"fields": "name,age", "output": str(iterable_output), "engine": "iterable"},
    )
    Selector().select(
        sample_csv_file,
        {"fields": "name,age", "output": str(duckdb_output), "engine": "duckdb"},
    )

    assert read_jsonl(str(iterable_output)) == read_jsonl(str(duckdb_output))


def test_select_requires_fields(sample_csv_file):
    from undatum.common.errors import ValidationError

    with pytest.raises(ValidationError, match="fields"):
        Selector().select(sample_csv_file, {"output": None})


def test_select_filter_translation_matches_iterable(sample_csv_file, tmp_path):
    iterable_output = tmp_path / "select_filter_iterable.jsonl"
    duckdb_output = tmp_path / "select_filter_duckdb.jsonl"
    options = {"fields": "name,age", "filter": "`age` >= 30"}

    Selector().select(
        sample_csv_file,
        {**options, "output": str(iterable_output), "engine": "iterable"},
    )
    Selector().select(
        sample_csv_file,
        {**options, "output": str(duckdb_output), "engine": "duckdb"},
    )

    assert read_jsonl(str(iterable_output)) == read_jsonl(str(duckdb_output))
    assert read_jsonl(str(iterable_output)) == [{"name": "Alice", "age": "30"}]


def test_select_stdout_jsonl(capsys, sample_csv_file):
    Selector().select(sample_csv_file, {"fields": "name,city"})
    captured = capsys.readouterr().out.strip().splitlines()

    assert [json.loads(line) for line in captured] == [
        {"name": "Alice", "city": "New York"},
        {"name": "Bob", "city": "London"},
    ]


def test_select_large_batch(sample_csv_file, tmp_path):
    large_csv = tmp_path / "large.csv"
    rows = ["name,age,city"]
    for i in range(1505):
        rows.append(f"User{i},{20 + (i % 10)},City{i}")
    large_csv.write_text("\n".join(rows) + "\n")

    output_file = tmp_path / "select_large.jsonl"
    Selector().select(
        str(large_csv),
        {"fields": "name,age", "output": str(output_file), "engine": "iterable"},
    )

    assert len(read_jsonl(str(output_file))) == 1505


def test_select_nested_fields_uses_iterable(sample_jsonl_file, tmp_path):
    nested_file = tmp_path / "nested.jsonl"
    nested_file.write_text(
        json.dumps({"user": {"name": "Alice", "city": "NYC"}, "age": 30})
        + "\n"
        + json.dumps({"user": {"name": "Bob", "city": "LA"}, "age": 25})
        + "\n"
    )

    output_file = tmp_path / "nested_select.jsonl"
    Selector().select(
        str(nested_file),
        {
            "fields": "user.name,user.city",
            "output": str(output_file),
            "engine": "duckdb",
            "format_in": "jsonl",
        },
    )

    assert read_jsonl(str(output_file)) == [
        {"user": {"name": "Alice", "city": "NYC"}},
        {"user": {"name": "Bob", "city": "LA"}},
    ]


def test_select_non_comma_csv_duckdb(tmp_path):
    csv_file = tmp_path / "semicolon.csv"
    csv_file.write_text("name;age\nAlice;30\nBob;25\n")

    output_file = tmp_path / "semicolon_out.jsonl"
    Selector().select(
        str(csv_file),
        {
            "fields": "name,age",
            "delimiter": ";",
            "output": str(output_file),
            "engine": "duckdb",
            "format_in": "csv",
        },
    )

    assert read_jsonl(str(output_file)) == [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"},
    ]


def test_select_fields_non_destructive():
    record = {"name": "Alice", "age": 30, "city": "NYC"}
    original = dict(record)
    selected = select_fields(record, [["name"], ["age"]])

    assert record == original
    assert selected == {"name": "Alice", "age": 30}


def test_dataset_select_sdk(sample_csv_file, tmp_path):
    output_file = tmp_path / "sdk_select.jsonl"
    ds = Dataset.read(sample_csv_file)
    result = ds.select(["name", "city"], output=str(output_file))

    assert result.source == str(output_file)
    assert read_jsonl(str(output_file)) == [
        {"name": "Alice", "city": "New York"},
        {"name": "Bob", "city": "London"},
    ]


def test_headers_json_output(sample_csv_file, tmp_path):
    output_file = tmp_path / "fields.json"
    Selector().headers(
        sample_csv_file,
        {"format_out": "json", "output": str(output_file), "limit": 100},
    )
    payload = json.loads(output_file.read_text(encoding="utf8"))
    assert set(payload["fields"]) == {"name", "age", "city"}


def test_frequency_json_output(sample_csv_file, tmp_path):
    output_file = tmp_path / "freq.json"
    Selector().frequency(
        sample_csv_file,
        {
            "fields": "city",
            "format_out": "json",
            "output": str(output_file),
            "engine": "iterable",
        },
    )
    payload = json.loads(output_file.read_text(encoding="utf8"))
    assert isinstance(payload, list)
    assert payload
    assert "city" in payload[0] and "count" in payload[0]


def test_uniq_json_from_extension(sample_csv_file, tmp_path):
    output_file = tmp_path / "cities.json"
    Selector().uniq(
        sample_csv_file,
        {"fields": "city", "output": str(output_file), "engine": "iterable"},
    )
    payload = json.loads(output_file.read_text(encoding="utf8"))
    assert isinstance(payload, list)
    cities = {row["city"] for row in payload}
    assert cities == {"New York", "London"}
