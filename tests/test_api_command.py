import json
from unittest.mock import patch

import pytest

from undatum.cmds.api import (
    DataApi,
    _apply_sort_alias,
    _build_api_app,
    _unique_resource_name,
    dump_api_config,
    load_api_config,
    require_api_dependencies,
)


def _skip_without_api():
    try:
        import fastapi  # noqa: F401
        from fastapi.testclient import TestClient  # noqa: F401
    except ImportError:
        pytest.skip("fastapi not installed (pip install 'undatum[api]')")


def _sample_config(csv_path):
    return {
        "resources": [
            {
                "name": "data",
                "path": str(csv_path),
                "format": "csv",
                "primary_key": "id",
                "fields": [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "varchar"},
                    {"name": "amount", "type": "integer"},
                ],
                "pagination": {"default_limit": 5, "max_limit": 50},
                "query": {
                    "allowed_ops": ["eq", "ne", "lt", "gt", "le", "ge", "like"],
                    "allowed_order_by": ["id", "name", "amount"],
                },
            }
        ]
    }


@pytest.fixture
def sample_csv(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text(
        "id,name,amount\n1,Alice,100\n2,Bob,200\n3,Carol,150\n",
        encoding="utf8",
    )
    return csv_path


def test_api_discover_writes_config(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text("id,amount\n1,100\n2,200\n", encoding="utf8")
    output_path = tmp_path / "api.yml"

    DataApi().discover([str(csv_path)], {"output": str(output_path), "format_in": "csv"})

    config = load_api_config(str(output_path))
    assert "resources" in config
    assert config["resources"][0]["name"] == "sales"
    assert config["resources"][0]["format"] == "csv"
    assert config["resources"][0]["path"] == str(csv_path.resolve())


def test_api_discover_resource_name_collision(tmp_path, capsys):
    first = tmp_path / "sales.csv"
    second = tmp_path / "sales.parquet"
    first.write_text("id,v\n1,a\n", encoding="utf8")
    second.write_text("not parquet", encoding="utf8")

    with patch("undatum.cmds.api._detect_format", side_effect=["csv", "csv"]):
        with patch(
            "undatum.cmds.api._infer_fields",
            return_value=[{"name": "id", "type": "integer"}, {"name": "v", "type": "varchar"}],
        ):
            with patch("undatum.cmds.api._infer_primary_key_candidates", return_value=[]):
                config = DataApi().discover(
                    [str(first), str(second)],
                    {"emit": False, "format_in": "csv"},
                )

    names = [resource["name"] for resource in config["resources"]]
    assert names == ["sales", "sales_2"]
    assert "collision" in capsys.readouterr().err.lower()


def test_api_config_json_roundtrip(tmp_path):
    config = {
        "resources": [
            {
                "name": "items",
                "path": "data/items.csv",
                "format": "csv",
                "fields": [{"name": "id", "type": "integer"}],
                "pagination": {"default_limit": 10, "max_limit": 100},
                "query": {"allowed_ops": ["eq"], "allowed_order_by": ["id"]},
            }
        ]
    }
    output_path = tmp_path / "api.json"
    output_path.write_text(dump_api_config(config, output=str(output_path), config_format="json"))

    loaded = load_api_config(str(output_path))
    assert loaded == json.loads(json.dumps(config))


def test_unique_resource_name():
    used: set[str] = set()
    assert _unique_resource_name("sales", used) == "sales"
    assert _unique_resource_name("sales", used) == "sales_2"
    assert _unique_resource_name("sales", used) == "sales_3"


def test_apply_sort_alias():
    assert _apply_sort_alias({"sort": "-amount"}) == {
        "order_by": "amount",
        "order_dir": "desc",
    }
    assert _apply_sort_alias({"sort": "name"}) == {
        "order_by": "name",
        "order_dir": "asc",
    }


def test_require_api_dependencies_raises():
    with patch.dict("sys.modules", {"fastapi": None, "uvicorn": None}):
        with pytest.raises(Exception) as exc_info:
            require_api_dependencies()
        assert "undatum[api]" in str(exc_info.value)


def test_api_build_app(sample_csv):
    _skip_without_api()
    app = _build_api_app(_sample_config(sample_csv))
    assert app is not None


def test_api_list_envelope_and_filter(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    client = TestClient(_build_api_app(_sample_config(sample_csv)))
    response = client.get("/data?amount__gt=100")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert "pagination" in payload
    assert payload["pagination"]["count"] == 2
    assert all(row["amount"] > 100 for row in payload["data"])


def test_api_sort_alias(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    client = TestClient(_build_api_app(_sample_config(sample_csv)))
    response = client.get("/data?sort=-amount")
    assert response.status_code == 200
    amounts = [row["amount"] for row in response.json()["data"]]
    assert amounts == sorted(amounts, reverse=True)


def test_api_include_total(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    client = TestClient(_build_api_app(_sample_config(sample_csv)))
    response = client.get("/data?include_total=true&amount__gt=100")
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 2


def test_api_detail_endpoint(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    client = TestClient(_build_api_app(_sample_config(sample_csv)))
    response = client.get("/data/2")
    assert response.status_code == 200
    assert response.json()["name"] == "Bob"


def test_api_root_and_docs(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    client = TestClient(_build_api_app(_sample_config(sample_csv)))
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["docs"] == "/docs"
    assert root.json()["resources"][0]["name"] == "data"

    docs = client.get("/docs")
    assert docs.status_code == 200

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    assert "/data" in schema["paths"]
    list_params = {param["name"] for param in schema["paths"]["/data"]["get"]["parameters"]}
    assert {"limit", "offset", "order_by", "sort"}.issubset(list_params)


def test_api_composite_primary_key_no_detail_route(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    config = _sample_config(sample_csv)
    config["resources"][0]["primary_key"] = ["id", "name"]
    client = TestClient(_build_api_app(config))
    assert client.get("/data/1").status_code == 404
    openapi_paths = client.get("/openapi.json").json()["paths"]
    assert "/data/{pk}" not in openapi_paths


def test_api_export_openapi(sample_csv, tmp_path):
    _skip_without_api()

    config_path = tmp_path / "api.json"
    config_path.write_text(
        dump_api_config(_sample_config(sample_csv), config_format="json"),
        encoding="utf8",
    )
    output_path = tmp_path / "openapi.json"
    schema = DataApi().export_openapi(str(config_path), {"output": str(output_path)})

    assert output_path.exists()
    assert schema["info"]["title"] == "undatum Data API"
    assert "/data" in schema["paths"]
    loaded = json.loads(output_path.read_text(encoding="utf8"))
    assert loaded["paths"]["/data"]["get"]["responses"]["200"]


def test_validate_api_config_schema_rejects_empty():
    from undatum.cmds.api import validate_api_config_schema

    with pytest.raises(ValueError, match="resources"):
        validate_api_config_schema({})
    with pytest.raises(ValueError, match="format"):
        validate_api_config_schema(
            {"resources": [{"name": "x", "path": "a.csv", "format": "xlsx"}]}
        )


def test_api_key_auth(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    from undatum.cmds.api import _build_api_app

    app = _build_api_app(_sample_config(sample_csv), api_key="secret")
    client = TestClient(app)
    assert client.get("/data").status_code == 401
    assert client.get("/data", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/docs").status_code == 200


def test_api_key_rejected_in_query_string(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    app = _build_api_app(_sample_config(sample_csv), api_key="secret")
    client = TestClient(app)
    assert client.get("/data?api_key=secret").status_code == 401
    assert client.get("/data", headers={"X-API-Key": "wrong"}).status_code == 401


def test_api_pagination_limits_are_per_resource(tmp_path):
    _skip_without_api()
    from fastapi.testclient import TestClient

    small = tmp_path / "small.csv"
    big = tmp_path / "big.csv"
    rows = "".join(f"{i},n{i}\n" for i in range(100))
    small.write_text("id,name\n" + rows, encoding="utf8")
    big.write_text("id,name\n" + rows, encoding="utf8")
    fields = [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
    config = {
        "resources": [
            {
                "name": "small",
                "path": str(small),
                "format": "csv",
                "fields": fields,
                "pagination": {"default_limit": 5, "max_limit": 10},
            },
            {
                "name": "big",
                "path": str(big),
                "format": "csv",
                "fields": fields,
                "pagination": {"default_limit": 5, "max_limit": 1000},
            },
        ]
    }
    client = TestClient(_build_api_app(config))
    assert client.get("/small?limit=50").status_code == 422
    response = client.get("/big?limit=50")
    assert response.status_code == 200
    assert response.json()["pagination"]["count"] == 50


def test_api_query_timeout_returns_504(sample_csv):
    _skip_without_api()
    import duckdb
    from fastapi.testclient import TestClient

    app = _build_api_app(_sample_config(sample_csv), query_timeout=0.5)
    client = TestClient(app)

    original_execute = duckdb.DuckDBPyConnection.execute

    def slow_execute(self, sql, *args, **kwargs):
        if sql.startswith("SELECT * FROM"):
            raise duckdb.InterruptException("interrupted")
        return original_execute(self, sql, *args, **kwargs)

    with patch.object(duckdb.DuckDBPyConnection, "execute", slow_execute):
        response = client.get("/data")
    assert response.status_code == 504


def test_api_config_rejects_negative_timeout(sample_csv):
    from undatum.cmds.api import validate_api_config_schema

    config = _sample_config(sample_csv)
    config["query_timeout"] = -1
    with pytest.raises(ValueError, match="query_timeout"):
        validate_api_config_schema(config)


def test_api_cors(sample_csv):
    _skip_without_api()
    from fastapi.testclient import TestClient

    from undatum.cmds.api import _build_api_app

    app = _build_api_app(_sample_config(sample_csv), cors_origins=["https://app.example.com"])
    client = TestClient(app)
    response = client.options(
        "/data",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_api_s3_resource_path_materialized(sample_csv):
    from unittest.mock import MagicMock, patch

    from undatum.cmds.api import _materialize_resource_path

    temps = []
    mock_client = MagicMock()
    mock_client.download_file.side_effect = lambda bucket, key, dest: __import__("shutil").copy(
        str(sample_csv), dest
    )
    with patch("undatum.formats.s3.get_s3_client", return_value=mock_client):
        local = _materialize_resource_path("s3://bucket/data.csv", temps)
    assert temps and local == temps[0]
    assert open(local, encoding="utf8").read().startswith("id,name")
    mock_client.download_file.assert_called_once()


def test_api_gcs_resource_path_materialized(sample_csv):
    from unittest.mock import patch

    from undatum.cmds.api import _materialize_resource_path

    def fake_download(path, dest):
        import shutil

        shutil.copy(str(sample_csv), dest)

    temps = []
    with patch("undatum.cmds.api._download_fsspec_uri", side_effect=fake_download):
        local = _materialize_resource_path("gs://bucket/data.csv", temps)
    assert temps and local == temps[0]
    assert open(local, encoding="utf8").read().startswith("id,name")


def test_api_azure_resource_path_materialized(sample_csv):
    from unittest.mock import patch

    from undatum.cmds.api import _materialize_resource_path

    def fake_download(path, dest):
        import shutil

        shutil.copy(str(sample_csv), dest)

    temps = []
    with patch("undatum.cmds.api._download_fsspec_uri", side_effect=fake_download):
        local = _materialize_resource_path("az://container/data.csv", temps)
    assert temps and local == temps[0]
    assert open(local, encoding="utf8").read().startswith("id,name")


def test_api_gcs_missing_fsspec_raises_dependency_error(tmp_path):
    from unittest.mock import patch

    from undatum.cmds.api import _download_fsspec_uri
    from undatum.common.errors import DependencyError

    dest = tmp_path / "unused.csv"
    with patch.dict("sys.modules", {"fsspec": None}):
        with pytest.raises(DependencyError, match="undatum\\[gcs\\]"):
            _download_fsspec_uri("gs://bucket/data.csv", str(dest))


def test_api_rejects_http_resource_path(tmp_path):
    from undatum.cmds.api import _validate_resources_config

    config = {
        "resources": [
            {
                "name": "data",
                "path": "https://example.com/data.csv",
                "format": "csv",
            }
        ]
    }
    with pytest.raises(ValueError, match="cloud URI"):
        _validate_resources_config(config)
