"""Tests for the `undatum ai` commands backed by iterable.ai."""

import importlib
import json
from unittest.mock import patch

from typer.testing import CliRunner

from undatum.core import app

# ``iterable/__init__.py`` binds ``iterable.ai`` to the ``doc`` module, so string patch
# targets like "iterable.ai.suggest.x" resolve to the wrong module on Python 3.10.
_AI_DOC = importlib.import_module("iterable.ai.doc")
_AI_SUGGEST = importlib.import_module("iterable.ai.suggest")

runner = CliRunner()


class TestAiFilter:
    def test_dsl_filter_no_llm(self):
        """Simple DSL is parsed locally without a provider."""
        result = runner.invoke(app, ["ai", "filter", "age > 30"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ast"]["op"] == "gt"
        assert data["ast"]["field"] == "age"
        assert data["source"] == "dsl"

    def test_apply_requires_file(self):
        result = runner.invoke(app, ["ai", "filter", "age > 30", "--apply"])
        assert result.exit_code == 1

    @patch("iterable.ops.schema.infer")
    def test_filter_passes_sample_size(self, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"age": {"type": "integer"}}}
        src = tmp_path / "data.csv"
        src.write_text("age\n1\n", encoding="utf8")
        result = runner.invoke(
            app,
            ["ai", "filter", "age > 30", str(src), "--sample-size", "50"],
        )
        assert result.exit_code == 0, result.stdout
        assert mock_infer.call_args[1]["sample_size"] == 50

    @patch("iterable.ops.schema.infer")
    def test_filter_omits_sample_size_when_unset(self, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"age": {"type": "integer"}}}
        src = tmp_path / "data.csv"
        src.write_text("age\n1\n", encoding="utf8")
        result = runner.invoke(app, ["ai", "filter", "age > 30", str(src)])
        assert result.exit_code == 0, result.stdout
        assert "sample_size" not in mock_infer.call_args[1]

    @patch("iterable.ops.schema.infer")
    def test_filter_passes_flatten_nested(self, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"capital_city.lat": {"type": "float"}}}
        src = tmp_path / "nested.jsonl"
        src.write_text('{"capital_city": {"lat": 38.56}}\n', encoding="utf8")
        result = runner.invoke(
            app,
            ["ai", "filter", "lat > 40", str(src), "--flatten-nested"],
        )
        assert result.exit_code == 0, result.stdout
        assert mock_infer.call_args[1]["flatten_nested"] is True
        assert mock_infer.call_args[1]["keep_nested_parents"] is True
        assert "max_nested_depth" not in mock_infer.call_args[1]

    @patch("iterable.ops.schema.infer")
    def test_filter_passes_flatten_depth_and_parents(self, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"a.b": {"type": "integer"}}}
        src = tmp_path / "nested.jsonl"
        src.write_text('{"a": {"b": {"c": 1}}}\n', encoding="utf8")
        result = runner.invoke(
            app,
            [
                "ai",
                "filter",
                "lat > 40",
                str(src),
                "--flatten-nested",
                "--max-nested-depth",
                "1",
                "--no-keep-nested-parents",
            ],
        )
        assert result.exit_code == 0, result.stdout
        kwargs = mock_infer.call_args[1]
        assert kwargs["flatten_nested"] is True
        assert kwargs["max_nested_depth"] == 1
        assert kwargs["keep_nested_parents"] is False

    @patch("iterable.ops.schema.infer")
    def test_filter_omits_flatten_nested_when_unset(self, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"age": {"type": "integer"}}}
        src = tmp_path / "data.csv"
        src.write_text("age\n1\n", encoding="utf8")
        result = runner.invoke(app, ["ai", "filter", "age > 30", str(src)])
        assert result.exit_code == 0, result.stdout
        assert "flatten_nested" not in mock_infer.call_args[1]

    @patch("iterable.ops.schema.infer")
    @patch("undatum.common.s3_iterable.open_path")
    def test_filter_passes_quotechar(self, mock_open, mock_infer, tmp_path):
        mock_infer.return_value = {"fields": {"name": {"type": "string"}}}
        mock_open.return_value.close = lambda: None
        src = tmp_path / "data.csv"
        src.write_text("name,city\n'Alice','Dushanbe'\n", encoding="utf8")
        result = runner.invoke(
            app,
            ["ai", "filter", "name == 'Alice'", str(src), "--quotechar", "'"],
        )
        assert result.exit_code == 0, result.stdout
        kwargs = mock_open.call_args[1]
        assert kwargs["iterableargs"]["quotechar"] == "'"


class TestAiPlan:
    def test_plan_uses_catalog(self):
        """Plan works offline using catalog metadata (no LLM)."""
        result = runner.invoke(app, ["ai", "plan", "data.csv", "out.parquet"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["source"]["format"] == "csv"
        assert data["target"]["format"] == "parquet"


class TestAiDoc:
    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_default_includes_agent_skill_and_codebook(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Documentation",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(app, ["ai", "doc", "data.csv"])
        assert result.exit_code == 0
        mock_blocks.assert_called_once()
        kwargs = mock_blocks.call_args[1]
        assert "agent_skill" in kwargs["blocks"]
        assert "codebook" in kwargs["blocks"]
        assert "schema" in kwargs["blocks"]

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_schema_blocks_use_generate_blocks(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(
            app,
            ["ai", "doc", "data.csv", "--format", "json", "--blocks", "general,schema"],
        )
        assert result.exit_code == 0
        mock_blocks.assert_called_once()
        mock_enrich.assert_called_once()
        kwargs = mock_blocks.call_args[1]
        assert kwargs["blocks"] == ["general", "schema"]


class TestAiSuggest:
    @patch.object(_AI_SUGGEST, "suggest_transform")
    def test_suggest_delegates(self, mock_suggest):
        mock_suggest.return_value = {"operations": []}
        result = runner.invoke(app, ["ai", "suggest", "data.csv", "drop empty columns"])
        assert result.exit_code == 0
        mock_suggest.assert_called_once()
        assert mock_suggest.call_args[0][0] == "data.csv"
        assert mock_suggest.call_args[0][1] == "drop empty columns"
        assert "sample_size" not in mock_suggest.call_args[1]

    @patch.object(_AI_SUGGEST, "suggest_transform")
    def test_suggest_passes_sample_size(self, mock_suggest):
        mock_suggest.return_value = {"operations": []}
        result = runner.invoke(
            app,
            ["ai", "suggest", "data.csv", "drop empty columns", "--sample-size", "20"],
        )
        assert result.exit_code == 0
        assert mock_suggest.call_args[1]["sample_size"] == 20

    @patch.object(_AI_SUGGEST, "suggest_transform")
    def test_suggest_apply_rename(self, mock_suggest, tmp_path):
        mock_suggest.return_value = {"operations": [{"op": "rename", "mapping": {"id": "user_id"}}]}
        src = tmp_path / "in.csv"
        src.write_text("id,name\n1,Alice\n", encoding="utf8")
        dst = tmp_path / "out.jsonl"
        result = runner.invoke(
            app,
            [
                "ai",
                "suggest",
                str(src),
                "rename id to user_id",
                "--apply",
                "--yes",
                "--output",
                str(dst),
            ],
        )
        assert result.exit_code == 0, result.stdout
        rows = [json.loads(line) for line in dst.read_text(encoding="utf8").splitlines() if line]
        assert rows
        assert "user_id" in rows[0]
        assert "id" not in rows[0]

    @patch.object(_AI_DOC, "generate")
    def test_doc_passes_tables_cache_pii(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--blocks",
                "general",
                "--tables",
                "Sheet2",
                "--cache",
                "--pii-mask-samples",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_generate.call_args[1]
        assert kwargs["tables"] == ["Sheet2"]
        assert kwargs["cache"] is True
        assert kwargs["pii_mask_samples"] is True

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_tables(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--format",
                "json",
                "--blocks",
                "general,schema",
                "--tables",
                "Sheet1,Sheet2",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_blocks.call_args[1]
        assert kwargs["tables"] == ["Sheet1", "Sheet2"]

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_context(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--blocks",
                "general,schema",
                "--context",
                '{"title": "Sales"}',
            ],
        )
        assert result.exit_code == 0
        assert mock_blocks.call_args[1]["context"] == {"title": "Sales"}

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_progress(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(app, ["ai", "doc", "data.csv", "--progress"])
        assert result.exit_code == 0
        assert callable(mock_blocks.call_args[1]["progress"])

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_passes_progress(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(app, ["ai", "doc", "data.csv", "--blocks", "general", "--progress"])
        assert result.exit_code == 0
        assert callable(mock_generate.call_args[1]["progress"])

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_field_descriptions_and_validate(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--blocks",
                "general",
                "--include-field-descriptions",
                "--validate-output",
                "--context",
                '{"title": "Sales"}',
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_generate.call_args[1]
        assert kwargs["include_field_descriptions"] is True
        assert kwargs["validate_output"] is True
        assert kwargs["context"] == {"title": "Sales"}

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_sample_size_and_constraints(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--sample-size",
                "20",
                "--no-detect-constraints",
                "--no-statistics",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_blocks.call_args[1]
        assert kwargs["sample_size"] == 20
        assert kwargs["detect_constraints"] is False
        assert kwargs["include_statistics"] is False

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_passes_sample_size_when_set(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--blocks",
                "general",
                "--sample-size",
                "20",
                "--no-statistics",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_generate.call_args[1]
        assert kwargs["sample_size"] == 20
        assert kwargs["include_statistics"] is False
        assert "detect_constraints" not in kwargs

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_omits_sample_size_when_unset(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(app, ["ai", "doc", "data.csv", "--blocks", "general"])
        assert result.exit_code == 0
        kwargs = mock_generate.call_args[1]
        assert "sample_size" not in kwargs
        assert kwargs["include_statistics"] is True
        assert "temperature" not in kwargs
        assert "max_tokens" not in kwargs
        assert "job_id" not in kwargs

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_temperature_and_max_tokens(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--temperature",
                "0.2",
                "--max-tokens",
                "2048",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_blocks.call_args[1]
        assert kwargs["temperature"] == 0.2
        assert kwargs["max_tokens"] == 2048

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_passes_temperature_and_max_tokens(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(
            app,
            [
                "ai",
                "doc",
                "data.csv",
                "--blocks",
                "general",
                "--temperature",
                "0.2",
                "--max-tokens",
                "2048",
            ],
        )
        assert result.exit_code == 0
        kwargs = mock_generate.call_args[1]
        assert kwargs["temperature"] == 0.2
        assert kwargs["max_tokens"] == 2048

    @patch("undatum.ai.doc_enrichment.enrich_blocks_result")
    @patch.object(_AI_DOC, "generate_blocks")
    def test_doc_blocks_pass_job_id(self, mock_blocks, mock_enrich):
        mock_blocks.return_value = {
            "full_document_markdown": "# Doc",
            "blocks": {"schema": {"data": {"fields": []}}},
        }
        result = runner.invoke(app, ["ai", "doc", "data.csv", "--job-id", "run-42"])
        assert result.exit_code == 0
        assert mock_blocks.call_args[1]["job_id"] == "run-42"

    @patch.object(_AI_DOC, "generate")
    def test_doc_generate_passes_job_id(self, mock_generate):
        mock_generate.return_value = "# Documentation"
        result = runner.invoke(
            app,
            ["ai", "doc", "data.csv", "--blocks", "general", "--job-id", "run-42"],
        )
        assert result.exit_code == 0
        assert mock_generate.call_args[1]["job_id"] == "run-42"
