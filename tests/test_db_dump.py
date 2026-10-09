"""Tests for db dump command."""

import sqlite3

from undatum.cmds.db_dump import DatabaseDumper


def test_db_dump_sqlite_to_csv(tmp_path):
    db_path = tmp_path / "test.db"
    out = tmp_path / "users.csv"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')")
    conn.commit()
    conn.close()

    DatabaseDumper().dump(
        f"sqlite:///{db_path}",
        str(out),
        table="users",
        output_format="csv",
    )
    text = out.read_text(encoding="utf-8")
    assert "Ada" in text
    assert "Grace" in text


def test_db_dump_requires_table_or_query(tmp_path):
    import pytest

    from undatum.common.errors import ValidationError

    with pytest.raises(ValidationError):
        DatabaseDumper().dump("sqlite:///x.db", str(tmp_path / "o.csv"))
