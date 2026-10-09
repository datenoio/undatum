"""``undatum migrate-script``: rewriting deprecated spellings in scripts and pipelines."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from undatum.cli.conventions import DEPRECATED_COMMANDS, RENAMES
from undatum.cmds.migrate import command_aliases, migrate_text
from undatum.core import app


def migrated(text: str, path: str = "run.sh") -> str:
    return migrate_text(text, path).migrated


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("undatum count x.csv --filetype csv", "undatum count x.csv --format-in csv"),
        ("undatum count x.csv --filetype=csv", "undatum count x.csv --format-in=csv"),
        ("undatum head x.csv --n 5", "undatum head x.csv --limit 5"),
        ("undatum -v analyze x.csv --outtype json", "undatum -v analyze x.csv --format-out json"),
        ("undatum diff a.csv b.csv --format json", "undatum diff a.csv b.csv --format-out json"),
        ("undatum stats x.csv --engine iterable", "undatum stats x.csv --engine python"),
        ("undatum stats x.csv -e iterable", "undatum stats x.csv -e python"),
        ("undatum stats x.csv --engine=iterable", "undatum stats x.csv --engine=python"),
        ("undatum profile x.csv", "undatum stats x.csv"),
        ("undatum document x.csv", "undatum doc x.csv"),
        ("undatum scheme x.csv", "undatum schema --format cerberus x.csv"),
        ("undatum scheme x.csv --stype jsonschema", "undatum schema x.csv --format jsonschema"),
        ("python -m undatum head x.csv --n 2", "python -m undatum head x.csv --limit 2"),
        ("/usr/local/bin/undatum head x.csv --n 2", "/usr/local/bin/undatum head x.csv --limit 2"),
        (
            "undatum head x.csv --n 2 | undatum count - --filetype csv",
            "undatum head x.csv --limit 2 | undatum count - --format-in csv",
        ),
        ("$ undatum head x.csv --n 2", "$ undatum head x.csv --limit 2"),
        ("FOO=1 uv run undatum head x.csv --n 2", "FOO=1 uv run undatum head x.csv --limit 2"),
        ("    run: undatum head x.csv --n 2", "    run: undatum head x.csv --limit 2"),
        ("Use `undatum profile x.csv`.", "Use `undatum stats x.csv`."),
        ("out=$(undatum count x.csv --filetype csv)", "out=$(undatum count x.csv --format-in csv)"),
    ],
)
def test_rewrites(before, after):
    assert migrated(before + "\n") == after + "\n"


@pytest.mark.parametrize(
    "line",
    [
        "undatum sql \"SELECT '--n' AS x FROM data\" x.csv",  # quoted text
        "echo undatum head x.csv --n 5",  # not an invocation
        "undatum head x.csv  # --n 5 in a comment",
        "undatum convert a.csv b.jsonl --filetype csv",  # convert never had --filetype
        "undatum ai doc x.csv --ai-provider openai",  # still accepted on ai doc
        "undatum stats x.csv --engine duckdb",
    ],
)
def test_leaves_alone(line):
    assert migrated(line + "\n") == line + "\n"


def test_line_continuations_keep_the_command():
    text = "undatum head x.csv \\\n  --n 5 \\\n  -e iterable\nother --n 5\n"
    assert migrated(text) == "undatum head x.csv \\\n  --limit 5 \\\n  -e python\nother --n 5\n"


def test_crlf_and_other_lines_are_kept():
    text = "set -e\r\nundatum head x.csv --n 5\r\n"
    assert migrated(text) == "set -e\r\nundatum head x.csv --limit 5\r\n"


def test_findings_for_manual_changes():
    result = migrate_text(
        "undatum ingest x.jsonl mongodb://h db c\nundatum scheme x.csv --delimiter ';'\n",
        "load.sh",
    )
    messages = [(f.line, f.message) for f in result.findings]
    assert messages[0][0] == 1 and "db load" in messages[0][1]
    assert messages[1][0] == 2 and "--delimiter" in messages[1][1]


def test_pipeline_yaml():
    text = (
        "steps:\n"
        "  - name: s\n"
        "    command: profile\n"
        "    args:\n"
        "      engine: iterable\n"
        "  - name: load\n"
        "    command: ingest\n"
        "    run: undatum count x.csv --filetype csv\n"
    )
    result = migrate_text(text, "p.yml")
    assert "command: stats" in result.migrated
    assert "engine: python" in result.migrated
    assert "--format-in csv" in result.migrated
    assert any("db load" in f.message for f in result.findings)


def test_alias_tables_cover_the_renames():
    tables = command_aliases()
    seen = {old for aliases in tables.values() for old in aliases}
    assert set(RENAMES) <= seen | {"--n"}  # every rename is in use somewhere
    assert {"profile", "document", "scheme", "ingest"} == set(DEPRECATED_COMMANDS)


def test_cli_diff_write_and_check(tmp_path):
    script = tmp_path / "etl.sh"
    script.write_text("#!/bin/sh\nundatum head data.csv --n 5\n")
    runner = CliRunner()
    shown = runner.invoke(app, ["migrate-script", str(tmp_path)])
    assert shown.exit_code == 0
    assert "+undatum head data.csv --limit 5" in shown.stdout
    assert script.read_text().endswith("--n 5\n")  # not written without --write
    assert runner.invoke(app, ["migrate-script", str(script), "--check"]).exit_code == 1
    written = runner.invoke(app, ["migrate-script", str(script), "--write"])
    assert written.exit_code == 0
    assert script.read_text() == "#!/bin/sh\nundatum head data.csv --limit 5\n"
    assert runner.invoke(app, ["migrate-script", str(script), "--check"]).exit_code == 0


def test_db_load_pipeline_step(tmp_path, monkeypatch):
    import sqlite3

    from undatum.cmds.pipeline import PipelineRunner
    from undatum.common.pipeline_parser import PipelineSpec, validate_pipeline

    monkeypatch.chdir(tmp_path)
    (tmp_path / "in.csv").write_text("id,name\n1,a\n2,b\n")
    spec = PipelineSpec(
        [
            {
                "name": "load",
                "command": "db load",
                "args": {
                    "input": "in.csv",
                    "db": f"sqlite:///{tmp_path / 't.db'}",
                    "table": "people",
                    "create_table": True,
                },
            }
        ]
    )
    assert validate_pipeline(spec) == []
    assert PipelineRunner().run(spec)
    rows = sqlite3.connect(tmp_path / "t.db").execute("select * from people").fetchall()
    assert rows == [("1", "a"), ("2", "b")]


def test_migration_guide_lists_every_alias():
    from pathlib import Path

    guide = (
        Path(__file__).resolve().parent.parent / "docs/docs/getting-started/migrating-to-2.md"
    ).read_text(encoding="utf8")
    for path, aliases in command_aliases().items():
        for old, new in aliases.items():
            row = next((line for line in guide.splitlines() if line.startswith(f"| `{old}`")), "")
            assert f"`{new}`" in row, f"{old} -> {new} missing from the guide"
            assert f"`{path}`" in row, f"{path} missing from the {old} row"
    for command in DEPRECATED_COMMANDS:
        assert f"`undatum {command}" in guide, command
