"""CLI and FastAPI tests for undatum web."""

import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from undatum.__main__ import main
from undatum.core import app


def _require_web_extra() -> None:
    """Skip unless fastapi, jinja2, uvicorn and python-multipart are installed."""
    from undatum.common.errors import DependencyError
    from undatum.web.deps import require_web_dependencies

    try:
        require_web_dependencies()
    except DependencyError:
        pytest.skip("undatum[web] is not installed")


def _csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def test_web_help_lists_command():
    result = CliRunner().invoke(app, ["web", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "sample" in result.stdout.lower()
    assert "127.0.0.1" in result.stdout
    assert "--flatten-nested" in result.stdout
    assert "keep-nested" in result.stdout


def test_web_missing_extra_exits_2(monkeypatch, sample_csv_file):
    from undatum.common.errors import DependencyError

    def boom():
        raise DependencyError(
            "fastapi",
            feature="web UI",
            install_command='pip install "undatum[web]"',
        )

    monkeypatch.setattr("undatum.cli.web_cli.require_web_dependencies", boom)
    monkeypatch.setattr(sys, "argv", ["undatum", "web", sample_csv_file])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2


def test_web_not_a_pipeline_command():
    from undatum.common.pipeline_parser import PipelineSpec, validate_pipeline

    spec = PipelineSpec([{"name": "explore", "command": "web", "args": {}}])
    errors = validate_pipeline(spec)
    assert any("unknown command" in error.lower() for error in errors)


def test_web_explore_shows_sample(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(
        path=sample_csv_file,
        work_dir=tmp_path,
        history_file=tmp_path / "history.json",
    )
    with TestClient(web_app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Alice" in response.text
        assert "Bob" in response.text
        assert "sample" in response.text.lower()
        assert "undatum table" in response.text


def test_web_filter_and_sql(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(
        path=sample_csv_file,
        work_dir=tmp_path,
        history_file=tmp_path / "history.json",
    )
    with TestClient(web_app) as client:
        token = _csrf_token(client.get("/").text)
        filtered = client.post(
            "/filter",
            data={"csrf_token": token, "expr": 'name == "Alice"'},
            follow_redirects=True,
        )
        assert filtered.status_code == 200
        assert "Alice" in filtered.text
        assert "Bob" not in filtered.text.split('id="grid"')[-1].split("</table>")[0]
        assert "--filter" in filtered.text

        token = _csrf_token(filtered.text)
        profiled = client.post(
            "/profile",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        assert profiled.status_code == 200
        assert "undatum stats" in profiled.text
        assert "Profile" in profiled.text

        token = _csrf_token(profiled.text)
        sql = client.post(
            "/sql",
            data={"csrf_token": token, "query": "SELECT name FROM data"},
            follow_redirects=True,
        )
        assert sql.status_code == 200
        assert "undatum sql" in sql.text
        assert "LIMIT 500" in sql.text
        assert "result-table" in sql.text


def test_web_export_validate_pipeline(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(
        path=sample_csv_file,
        work_dir=tmp_path,
        history_file=tmp_path / "history.json",
    )
    with TestClient(web_app) as client:
        token = _csrf_token(client.get("/").text)
        extract = tmp_path / "extract.jsonl"
        exported = client.post(
            "/export",
            data={"csrf_token": token, "path": str(extract)},
            follow_redirects=True,
        )
        assert exported.status_code == 200
        assert extract.exists()
        assert "Alice" in extract.read_text()

        token = _csrf_token(exported.text)
        converted = client.post(
            "/convert",
            data={"csrf_token": token, "path": str(tmp_path / "out.jsonl")},
            follow_redirects=True,
        )
        assert converted.status_code == 200
        assert (tmp_path / "out.jsonl").exists()
        assert "--low-memory" in converted.text or "Wrote" in converted.text

        token = _csrf_token(converted.text)
        validated = client.post(
            "/validate",
            data={"csrf_token": token, "rules": ""},
            follow_redirects=True,
        )
        assert validated.status_code == 200
        assert "Validate sample" in validated.text
        assert "undatum validate" in validated.text

        token = _csrf_token(validated.text)
        masked = client.post(
            "/mask",
            data={"csrf_token": token, "fields": "name", "output": ""},
            follow_redirects=True,
        )
        assert masked.status_code == 200
        assert "Mask preview" in masked.text
        assert "***" in masked.text

        token = _csrf_token(masked.text)
        pipe = tmp_path / "pipeline.yml"
        dumped = client.post(
            "/pipeline",
            data={"csrf_token": token, "path": str(pipe)},
            follow_redirects=True,
        )
        assert dumped.status_code == 200
        assert pipe.exists()
        assert "convert" in pipe.read_text()
        assert "undatum pipeline run" in dumped.text


def test_web_csrf_rejects_bad_token(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(path=sample_csv_file, work_dir=tmp_path)
    with TestClient(web_app) as client:
        client.get("/")
        response = client.post("/open", data={"csrf_token": "nope", "path": sample_csv_file})
        assert response.status_code == 403


def test_web_api_key_required(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(path=sample_csv_file, work_dir=tmp_path, api_key="secret")
    with TestClient(web_app) as client:
        assert client.get("/").status_code == 401
        ok = client.get("/", params={"api_key": "secret"})
        assert ok.status_code == 200
        assert "Alice" in ok.text


def test_web_healthz(tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(work_dir=tmp_path)
    with TestClient(web_app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


def test_web_actions_list_cli_templates(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(path=sample_csv_file, work_dir=tmp_path)
    with TestClient(web_app) as client:
        text = client.get("/").text
        assert "undatum stats" in text
        assert "Equivalent CLI" in text
        assert "htmx.min.js" in text
        assert 'hx-boost="true"' in text
        assert client.get("/static/web.css").status_code == 200
        assert client.get("/static/htmx.min.js").status_code == 200


def test_web_upload_and_frequency(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(work_dir=tmp_path, history_file=tmp_path / "history.json")
    with TestClient(web_app) as client:
        token = _csrf_token(client.get("/").text)
        uploaded = client.post(
            "/upload",
            data={"csrf_token": token},
            files={"file": ("people.csv", Path(sample_csv_file).read_bytes(), "text/csv")},
            follow_redirects=True,
        )
        assert uploaded.status_code == 200
        assert "Alice" in uploaded.text
        assert "Uploaded" in uploaded.text

        token = _csrf_token(uploaded.text)
        counted = client.post(
            "/frequency",
            data={"csrf_token": token, "field": "city"},
            follow_redirects=True,
        )
        assert counted.status_code == 200
        assert "undatum frequency" in counted.text
        assert "New York" in counted.text or "London" in counted.text


def test_web_rejects_overlapping_job(sample_csv_file, tmp_path):
    _require_web_extra()
    from fastapi.testclient import TestClient

    from undatum.web.app import create_app

    web_app = create_app(path=sample_csv_file, work_dir=tmp_path)
    state = web_app.state.web
    state.job_lock.acquire()
    state.busy = "convert"
    try:
        with TestClient(web_app) as client:
            token = _csrf_token(client.get("/").text)
            response = client.post(
                "/profile",
                data={"csrf_token": token},
                follow_redirects=True,
            )
            assert response.status_code == 200
            assert "Busy" in response.text
            assert "convert" in response.text
    finally:
        state.busy = None
        state.job_lock.release()


def test_web_remote_bind_warning():
    _require_web_extra()
    from undatum.web.app import remote_bind_warning

    assert remote_bind_warning("127.0.0.1") is None
    assert remote_bind_warning("localhost") is None
    warning = remote_bind_warning("0.0.0.0")
    assert warning is not None
    assert "0.0.0.0" in warning
    assert "not a hardened public app" in warning


def test_web_package_does_not_import_textual():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "undatum"
    files = list((root / "web").rglob("*.py")) + [root / "cli" / "web_cli.py"]
    forbidden = ("textual", "undatum.tui.app", "undatum.tui.screens")
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert all(item not in name for item in forbidden), f"{path}: {name}"
