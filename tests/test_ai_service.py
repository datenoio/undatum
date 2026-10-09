"""--autodoc through iterable.ai providers (a fake provider stands in for the network)."""

from __future__ import annotations

import importlib
import json
import re
import types

import pytest
from typer.testing import CliRunner

from undatum.ai import AIConfigurationError, AIService, get_ai_service
from undatum.core import app

SAMPLE = "id,email,city\n1,alice@example.com,Paris\n2,bob@example.com,Rome\n"


class FakeProvider:
    """Answers the three autodoc prompts; records every prompt it gets."""

    def __init__(self, name, api_key=None, base_url=None):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.prompts: list[str] = []
        self.models: list[str | None] = []

    def generate(self, prompt, model=None, temperature=0.7, max_tokens=None, **kwargs):
        self.prompts.append(prompt)
        self.models.append(model)
        if prompt.startswith("Describe these data fields"):
            names = re.search(r"in \w+: (.*)\.\n", prompt).group(1).split(", ")
            return json.dumps({name: f"About {name}" for name in names})
        if "structured dataset metadata" in prompt:
            return (
                "```json\n"
                + json.dumps({"title": "Fake title", "keywords": ["fake"], "data_theme": None})
                + "\n```"
            )
        return 'Sure: {"description": "A fake dataset."}'

    def get_usage_info(self):
        return None


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Patch iterable.ai.providers.get_provider; isolate config files and env."""
    for name in (
        "UNDATUM_AI_PROVIDER",
        "UNDATUM_AI_PII_MASK_SAMPLES",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "PERPLEXITY_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OLLAMA_BASE_URL",
        "LMSTUDIO_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    created: list[FakeProvider] = []

    def get_provider(provider=None, api_key=None, base_url=None):
        instance = FakeProvider(provider, api_key, base_url)
        created.append(instance)
        return instance

    # ``iterable.ai`` the attribute is not the package, so patch the module object.
    providers = importlib.import_module("iterable.ai.providers")
    monkeypatch.setattr(providers, "get_provider", get_provider)
    # Local providers check that their server listens; pretend it does.
    monkeypatch.setattr(
        "undatum.ai.service.socket.create_connection",
        lambda *args, **kwargs: types.SimpleNamespace(close=lambda: None),
    )
    (tmp_path / "people.csv").write_text(SAMPLE, encoding="utf8")
    return created


def _sent(created: list[FakeProvider]) -> str:
    return "\n".join(prompt for provider in created for prompt in provider.prompts)


# --- service --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "mask", "masked"),
    [
        ("openai", None, True),
        ("anthropic", None, True),
        ("ollama", None, False),
        ("lmstudio", None, False),
        ("openai", False, False),
        ("ollama", True, True),
    ],
)
def test_sample_masking_defaults(fake, provider, mask, masked):
    service = AIService(provider, mask_samples=mask)
    sample = service.prepare_sample(SAMPLE)
    assert ("alice@example.com" not in sample) is masked
    assert "Paris" in sample


def test_long_samples_are_truncated(fake):
    sample = AIService("ollama").prepare_sample("a\n" + "x" * 10_000)
    assert sample.endswith("(truncated)") and len(sample) < 4100


def test_description_metadata_and_fields(fake):
    service = AIService("openai", model="gpt-test")
    assert service.get_description(SAMPLE) == "A fake dataset."
    assert service.get_structured_metadata(SAMPLE, ["id", "email"])["title"] == "Fake title"
    assert service.get_fields_info(["id", "email"]) == {"id": "About id", "email": "About email"}
    assert fake[0].models == ["gpt-test"] * 3
    assert "alice@example.com" not in _sent(fake)


def test_unknown_provider():
    with pytest.raises(AIConfigurationError, match="Unknown provider"):
        AIService("skynet")


def test_no_provider_configured(fake):
    with pytest.raises(AIConfigurationError, match="No AI provider"):
        get_ai_service()


@pytest.mark.parametrize(
    ("variable", "provider"),
    [
        ("OPENAI_API_KEY", "openai"),
        ("PERPLEXITY_API_KEY", "perplexity"),
        ("OPENROUTER_API_KEY", "openrouter"),
        ("ANTHROPIC_API_KEY", "anthropic"),
    ],
)
def test_provider_from_api_key_variable(fake, monkeypatch, variable, provider):
    monkeypatch.setenv(variable, "sk-test")
    service = get_ai_service()
    assert service.provider == provider
    assert fake[-1].name == provider


def test_legacy_settings_reach_the_provider(fake, monkeypatch):
    monkeypatch.setenv("UNDATUM_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    service = get_ai_service(config={"model": "gpt-x"})
    assert (fake[-1].api_key, service.model) == ("sk-env", "gpt-x")

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu:11434")
    get_ai_service("ollama")
    assert fake[-1].base_url == "http://gpu:11434"


def test_config_file_and_mask_variable(fake, tmp_path, monkeypatch):
    (tmp_path / "undatum.yaml").write_text(
        "ai:\n  provider: lmstudio\n  model: local-model\n  pii_mask_samples: true\n"
    )
    service = get_ai_service()
    assert (service.provider, service.model, service.masks_samples) == (
        "lmstudio",
        "local-model",
        True,
    )
    (tmp_path / "undatum.yaml").unlink()
    monkeypatch.setenv("UNDATUM_AI_PII_MASK_SAMPLES", "false")
    assert get_ai_service("openai").masks_samples is False
    # An explicit setting wins over the variable.
    assert get_ai_service("openai", {"pii_mask_samples": True}).masks_samples is True


# --- --autodoc commands ----------------------------------------------------------------


def _invoke(args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def test_analyze_autodoc(fake):
    result = _invoke(
        ["analyze", "people.csv", "--autodoc", "--ai-provider", "openai", "--outtype", "json"]
    )
    assert "A fake dataset." in result.stdout
    assert "About email" in result.stdout
    assert "Paris" in _sent(fake) and "alice@example.com" not in _sent(fake)


def test_analyze_autodoc_opt_out_of_masking(fake):
    _invoke(
        [
            "analyze",
            "people.csv",
            "--autodoc",
            "--ai-provider",
            "openai",
            "--no-pii-mask-samples",
            "--outtype",
            "json",
        ]
    )
    assert "alice@example.com" in _sent(fake)


def test_schema_autodoc(fake):
    result = _invoke(
        ["schema", "people.csv", "--autodoc", "--ai-provider", "anthropic", "--format", "json"]
    )
    assert "About city" in result.stdout
    # Field descriptions send names only.
    assert "Paris" not in _sent(fake)


def test_schema_bulk_autodoc(fake, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "people.csv").write_text(SAMPLE, encoding="utf8")
    _invoke(
        [
            "schema-bulk",
            "data",
            "--autodoc",
            "--ai-provider",
            "openai",
            "--output",
            "schemas",
            "--format",
            "json",
        ]
    )
    written = "".join(p.read_text() for p in (tmp_path / "schemas").iterdir())
    assert "About email" in written


def test_doc_autodoc(fake):
    result = _invoke(
        ["doc", "people.csv", "--autodoc", "--ai-provider", "gemini", "--format", "json"]
    )
    assert "Fake title" in result.stdout
    assert "Paris" in _sent(fake) and "alice@example.com" not in _sent(fake)


def test_doc_autodoc_local_provider_unmasked(fake):
    _invoke(["doc", "people.csv", "--autodoc", "--ai-provider", "ollama", "--format", "json"])
    assert "alice@example.com" in _sent(fake)


def test_package_autodoc(fake, tmp_path):
    _invoke(
        [
            "package",
            "create",
            "people.csv",
            "--autodoc",
            "--ai-provider",
            "openai",
            "--output",
            "datapackage.json",
        ]
    )
    package = json.loads((tmp_path / "datapackage.json").read_text())
    text = json.dumps(package)
    assert "About email" in text
    assert "alice@example.com" not in _sent(fake)


def test_legacy_provider_variable_with_autodoc(fake, monkeypatch):
    monkeypatch.setenv("UNDATUM_AI_PROVIDER", "openrouter")
    result = _invoke(["doc", "people.csv", "--autodoc", "--format", "json"])
    assert "Fake title" in result.stdout
    assert {provider.name for provider in fake} == {"openrouter"}


@pytest.mark.parametrize(
    "args",
    [
        ["doc", "people.csv", "--autodoc", "--format", "json"],
        ["schema", "people.csv", "--autodoc", "--format", "json"],
        ["analyze", "people.csv", "--autodoc", "--outtype", "json"],
    ],
)
def test_autodoc_without_provider_still_documents(fake, args):
    result = _invoke(args)
    assert "email" in result.stdout
    assert not fake


def test_unreachable_local_server_fails_fast(fake, monkeypatch):
    import time

    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr("undatum.ai.service.socket.create_connection", refuse)
    started = time.monotonic()
    with pytest.raises(AIConfigurationError, match="not reachable"):
        get_ai_service("ollama")
    assert time.monotonic() - started < 5
    assert not fake  # the provider was never created


def test_fail_soft_warns_once_and_continues(fake, caplog):
    service = AIService("openai", fail_soft=True)
    service.client()

    def broken(*args, **kwargs):
        raise RuntimeError("timeout")

    fake[0].generate = broken
    with caplog.at_level("WARNING"):
        assert service.get_description(SAMPLE) == ""
        assert service.get_fields_info(["id"]) == {}
    assert caplog.text.count("AI descriptions skipped") == 1
    strict = AIService("openai")
    strict._client = fake[0]
    with pytest.raises(Exception, match="timeout"):
        strict.get_description(SAMPLE)


def test_analyze_autodoc_survives_an_unreachable_provider(fake, monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr("undatum.ai.service.socket.create_connection", refuse)
    result = _invoke(
        ["analyze", "people.csv", "--autodoc", "--ai-provider", "ollama", "--outtype", "json"]
    )
    assert json.loads(result.stdout)["schema"] == "undatum.analyze/1"


def test_ai_errors_are_undatum_errors():
    from undatum.ai import AIAPIError
    from undatum.common.errors import UndatumError, error_code

    error = AIAPIError("down")
    assert isinstance(error, UndatumError)
    assert (error.exit_code, error_code(error)) == (3, "ai_error")
