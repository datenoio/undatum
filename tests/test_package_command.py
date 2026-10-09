import json
from unittest.mock import MagicMock, patch

import pytest

from undatum.cmds.packager import Packager
from undatum.cmds.pipeline import PipelineRunner
from undatum.common.errors import FileNotFoundError, ValidationError


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("id,name\n1,Alice\n2,Bob\n3,Carol\n", encoding="utf8")
    return path


def test_package_create_generates_descriptor(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"

    result = Packager().create(
        [str(csv_file)],
        options={
            "output": str(output_file),
            "sample_size": 2,
            "quiet": True,
        },
    )

    data = result["package"]
    assert data["profile"] == "tabular-data-package"
    assert data["name"]
    assert len(data["resources"]) == 1
    resource = data["resources"][0]
    assert resource["path"] == csv_file.name
    assert resource["format"] == "csv"
    assert resource["mediatype"] == "text/csv"
    assert resource["schema"]["fields"]
    assert output_file.exists()


def test_package_create_flatten_nested(tmp_path):
    src = tmp_path / "nested.jsonl"
    src.write_text(
        '{"name": "TJK", "capital_city": {"lat": 38.56, "lon": 68.77}}\n',
        encoding="utf8",
    )
    output_file = tmp_path / "datapackage.json"
    result = Packager().create(
        [str(src)],
        options={
            "output": str(output_file),
            "flatten_nested": True,
            "engine": "iterable",
            "quiet": True,
        },
    )
    names = [field["name"] for field in result["package"]["resources"][0]["schema"]["fields"]]
    assert "capital_city.lat" in names
    assert "capital_city.lon" in names


def test_package_create_directory_output(csv_file, tmp_path):
    package_dir = tmp_path / "package"

    Packager().create(
        [str(csv_file)],
        options={
            "package_dir": str(package_dir),
            "sample_size": 1,
            "quiet": True,
        },
    )

    package_file = package_dir / "datapackage.json"
    assert package_file.exists()
    assert (package_dir / csv_file.name).exists()
    data = json.loads(package_file.read_text(encoding="utf8"))
    assert data["resources"][0]["path"] == csv_file.name


def test_package_create_metadata_flags(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"
    result = Packager().create(
        [str(csv_file)],
        options={
            "output": str(output_file),
            "name": "demo-set",
            "title": "Demo Dataset",
            "description": "A demo package",
            "keywords": "demo,test",
            "licenses": "name=MIT",
            "version": "1.0.0",
            "quiet": True,
        },
    )
    data = result["package"]
    assert data["name"] == "demo-set"
    assert data["title"] == "Demo Dataset"
    assert data["description"] == "A demo package"
    assert data["keywords"] == ["demo", "test"]
    assert data["licenses"] == [{"name": "MIT"}]
    assert data["version"] == "1.0.0"


def test_package_create_multiple_files(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"
    other = tmp_path / "other.csv"
    other.write_text("id,name\n4,Dan\n", encoding="utf8")
    result = Packager().create(
        [str(csv_file), str(other)],
        options={"output": str(output_file), "quiet": True},
    )
    assert len(result["package"]["resources"]) == 2


def test_package_create_remote_url(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"
    with patch("undatum.cmds.packager._download_to_temp", return_value=str(csv_file)):
        result = Packager().create(
            ["https://example.org/data.csv"],
            options={"output": str(output_file), "quiet": True},
        )
    assert result["package"]["resources"][0]["path"] == "https://example.org/data.csv"


def test_package_create_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        Packager().create(
            [str(tmp_path / "missing.csv")],
            options={"output": str(tmp_path / "datapackage.json"), "quiet": True},
        )


def test_package_create_no_inputs():
    with pytest.raises(ValidationError):
        Packager().create([], options={"quiet": True})


def test_package_autodoc_fallback(csv_file, tmp_path, monkeypatch):
    output_file = tmp_path / "datapackage.json"

    def _raise(*args, **kwargs):
        raise RuntimeError("AI unavailable")

    monkeypatch.setattr("undatum.cmds.packager.get_structured_metadata", _raise)
    monkeypatch.setattr("undatum.cmds.packager.get_fields_info", _raise)

    result = Packager().create(
        [str(csv_file)],
        options={"output": str(output_file), "autodoc": True, "quiet": True},
    )
    assert result["package"]["resources"]


def test_package_add_resource(csv_file, tmp_path):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    package_file = package_dir / "datapackage.json"
    package_file.write_text(
        json.dumps({"name": "existing", "resources": []}, indent=2),
        encoding="utf8",
    )

    result = Packager().add_resource(
        str(package_file),
        [str(csv_file)],
        options={"quiet": True},
    )
    data = result["package"]
    assert len(data["resources"]) == 1
    assert (package_dir / csv_file.name).exists()


def test_package_validate_basic(tmp_path):
    package_file = tmp_path / "datapackage.json"
    package_file.write_text(
        json.dumps(
            {
                "name": "demo",
                "resources": [{"name": "demo", "path": "demo.csv"}],
            }
        ),
        encoding="utf8",
    )
    assert Packager().validate(str(package_file), options={"quiet": True}) is True


def test_package_validate_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        Packager().validate(str(tmp_path / "missing.json"), options={"quiet": True})


def test_package_validate_invalid_structure(tmp_path):
    package_file = tmp_path / "datapackage.json"
    package_file.write_text(json.dumps({"resources": []}), encoding="utf8")
    with pytest.raises(ValidationError):
        Packager().validate(str(package_file), options={"quiet": True})


def test_package_zip_output(csv_file, tmp_path):
    package_dir = tmp_path / "package"
    zip_path = tmp_path / "bundle.zip"
    result = Packager().create(
        [str(csv_file)],
        options={
            "package_dir": str(package_dir),
            "zip": str(zip_path),
            "quiet": True,
        },
    )
    assert result["archive_path"] == str(zip_path)
    assert zip_path.exists()


def test_pipeline_package_create_step(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"
    runner = PipelineRunner()
    success = runner._execute_package_step(
        {
            "subcommand": "create",
            "input_files": [str(csv_file)],
            "output": str(output_file),
            "quiet": True,
        },
        "package_step",
    )
    assert success is True
    assert output_file.exists()


def test_dataset_package_method(csv_file, tmp_path):
    from undatum.sdk.dataset import Dataset

    output_file = tmp_path / "datapackage.json"
    result = Dataset.read(str(csv_file)).package(output=str(output_file))
    assert result["package"]["name"]
    assert output_file.exists()


def test_field_unique_constraint(csv_file, tmp_path):
    output_file = tmp_path / "datapackage.json"
    result = Packager().create(
        [str(csv_file)],
        options={"output": str(output_file), "quiet": True},
    )
    fields = result["package"]["resources"][0]["schema"]["fields"]
    id_field = next(item for item in fields if item["name"] == "id")
    if id_field.get("unique") is not None:
        assert id_field["unique"] is True


def test_schema_utils_field_mapping():
    from undatum.common.schema_utils import field_to_frictionless_schema

    field = MagicMock()
    field.name = "amount"
    field.ftype = "DOUBLE"
    field.is_array = False
    field.description = "Amount in USD"
    field.unique_count = 5
    field.total_count = 10

    mapped = field_to_frictionless_schema(field)
    assert mapped["type"] == "number"
    assert mapped["description"] == "Amount in USD"
    assert "unique" not in mapped
