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
        ("undatum scheme x.csv", "undatum schema x.csv --format cerberus"),
        ("undatum scheme x.csv --stype jsonschema", "undatum schema x.csv --format jsonschema"),
        ("undatum scheme x.csv > out.yaml", "undatum schema x.csv --format cerberus > out.yaml"),
        ("undatum scheme x.csv 2>/dev/null", "undatum schema x.csv --format cerberus 2>/dev/null"),
        ("undatum scheme x.csv | head", "undatum schema x.csv --format cerberus | head"),
        ('undatum scheme "a b.csv"  # note', 'undatum schema "a b.csv" --format cerberus  # note'),
        ("Use `undatum scheme FILE`.", "Use `undatum schema FILE --format cerberus`."),
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


def test_scheme_default_format_follows_the_last_argument_line():
    assert migrated("undatum scheme x.csv \\\n  --stype jsonschema\n") == (
        "undatum schema x.csv \\\n  --format jsonschema\n"
    )
    assert migrated("undatum scheme x.csv \\\n  --delimiter ';'\n") == (
        "undatum schema x.csv \\\n  --delimiter ';' --format cerberus\n"
    )
    assert migrated("undatum scheme x.csv \\\n  | head\n") == (
        "undatum schema x.csv --format cerberus \\\n  | head\n"
    )


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


def test_ignore_marker_keeps_the_next_table():
    text = (
        "<!-- migrate-script: ignore -->\n"
        "| Deprecated | Use instead |\n"
        "|------------|-------------|\n"
        "| `undatum profile FILE` | `undatum stats FILE` |\n"
        "| `undatum scheme FILE` | `undatum schema FILE --format cerberus` |\n"
        "| `undatum ingest FILE URI DB TABLE` | `undatum db load FILE --db URI` |\n"
        "\n"
        "Then run `undatum profile x.csv`.\n"
    )
    result = migrate_text(text, "guide.md")
    assert result.migrated == text.replace("Then run `undatum profile", "Then run `undatum stats")
    assert result.findings == []


def test_ignore_marker_keeps_a_fenced_block_with_blank_lines():
    text = (
        "# migrate-script: ignore\n"
        "\n"
        "```bash\n"
        "undatum ingest a.jsonl mongodb://h db c\n"
        "\n"
        "undatum profile x.csv\n"
        "```\n"
        "undatum profile y.csv\n"
    )
    result = migrate_text(text, "ingest.md")
    assert result.migrated == text.replace("profile y.csv", "stats y.csv")
    assert result.findings == []


def test_ignore_marker_at_the_end_of_a_line():
    text = (
        "undatum profile a.csv  # migrate-script: ignore\n"
        "Run `undatum profile b.csv` <!-- migrate-script: ignore -->\n"
        "undatum profile c.csv\n"
    )
    assert migrated(text) == text.replace("profile c.csv", "stats c.csv")


def test_ignore_start_and_end():
    text = (
        "<!-- migrate-script: ignore-start -->\n"
        "undatum profile a.csv\n"
        "\n"
        "undatum ingest a.jsonl mongodb://h db c\n"
        "<!-- migrate-script: ignore-end -->\n"
        "undatum profile b.csv\n"
        "  # migrate-script: ignore-start\n"
        "undatum profile c.csv\n"
    )
    result = migrate_text(text, "page.md")
    assert result.migrated == text.replace("profile b.csv", "stats b.csv")
    assert result.findings == []  # an unclosed range runs to the end of the file


@pytest.mark.parametrize(
    "line",
    [
        "Write `<!-- migrate-script: ignore -->` before a table: `undatum profile x.csv`.",
        "Mark a range with `# migrate-script: ignore-start` and `undatum profile x.csv`.",
        "undatum profile x.csv  # migrate-script: ignore-me",
    ],
)
def test_marker_mentioned_in_text_is_not_a_marker(line):
    assert migrated(line + "\nundatum profile y.csv\n", "page.md") == (
        line.replace("undatum profile", "undatum stats") + "\nundatum stats y.csv\n"
    )


def test_ignore_marker_in_pipeline_yaml():
    text = (
        "steps:\n"
        "  # migrate-script: ignore\n"
        "  - name: legacy\n"
        "    command: ingest\n"
        "\n"
        "  - name: s\n"
        "    command: profile  # migrate-script: ignore\n"
        "  - name: t\n"
        "    command: profile\n"
    )
    result = migrate_text(text, "p.yml")
    assert result.migrated.splitlines()[6] == "    command: profile  # migrate-script: ignore"
    assert result.migrated.splitlines()[8] == "    command: stats"
    assert result.findings == []


def test_documentation_needs_no_migration():
    from pathlib import Path

    from undatum.cmds.migrate import migrate_files

    docs = Path(__file__).resolve().parent.parent / "docs" / "docs"
    migrations = migrate_files([str(docs)])
    assert [m.path for m in migrations if m.changed] == []
    assert [f"{f.path}:{f.line}" for m in migrations for f in m.findings] == []


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


def test_cli_check_passes_on_marked_documentation(tmp_path):
    page = tmp_path / "ingest.md"
    page.write_text(
        "<!-- migrate-script: ignore -->\n```bash\nundatum ingest a.jsonl mongodb://h db c\n```\n"
    )
    result = CliRunner().invoke(app, ["migrate-script", str(tmp_path), "--check"])
    assert result.exit_code == 0
    assert "0 places need review" in result.stderr


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
