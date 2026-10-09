"""AI service for ``--autodoc``, backed by iterabledata's ``iterable.ai`` providers.

The same provider stack serves ``undatum ai ...`` and ``--autodoc`` on ``analyze``,
``schema``, ``doc`` and ``package``. Sample records sent to a remote provider are masked
for likely PII (column-name heuristics of ``iterable.ai``) unless masking is turned off;
local providers (Ollama, LM Studio) receive them unmasked unless masking is turned on.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar
from urllib.parse import urlparse

from .base import AIAPIError, AIConfigurationError

# Provider names accepted by iterable.ai (plus aliases).
PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "azure",
    "openrouter",
    "ollama",
    "lmstudio",
    "perplexity",
    "openai-compatible",
)
LOCAL_PROVIDERS = ("ollama", "lmstudio")
LOCAL_DEFAULT_URLS = {"ollama": "http://localhost:11434", "lmstudio": "http://localhost:1234"}
MAX_SAMPLE_CHARS = 4000
CONNECT_TIMEOUT = 2.0

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _metadata_prompt(data: str, fields: list[str], language: str) -> str:
    from ..constants import EU_DATA_THEMES

    themes = json.dumps(EU_DATA_THEMES, ensure_ascii=False)
    return (
        "I have the following CSV data sample:\n"
        f"{data}\n"
        f"Field names: {', '.join(fields)}\n\n"
        f"Generate structured dataset metadata in {language}. "
        "Return a JSON object with these keys only:\n"
        "- title (string)\n"
        "- keywords (array of strings)\n"
        "- geographic_coverage (object with countries, regions, coordinates_present)\n"
        "- temporal_coverage (object with start, end, granularity)\n"
        "- languages (array of objects with code and confidence)\n"
        "- data_theme (object with label and uri, or null)\n"
        "- confidence (object with per-section confidence 0-1)\n"
        "- evidence (object mapping keys to brief evidence strings)\n\n"
        "Use the EU Data Theme vocabulary list for data_theme selection:\n"
        f"{themes}\n"
        "If you cannot determine a field, set it to null or empty. Respond with JSON only."
    )


def _fields_prompt(fields: list[str], language: str) -> str:
    return (
        f"Describe these data fields in {language}: {', '.join(fields)}.\n"
        "Return a JSON object that maps each field name to a one-sentence description of "
        "what it represents. Respond with JSON only."
    )


def _description_prompt(data: str, language: str) -> str:
    return (
        "I have the following CSV data sample:\n"
        f"{data}\n"
        f"Please provide a short description of this dataset in {language}. Consider this "
        "as a sample of a larger dataset. Don't generate code or data examples.\n"
        'Return your response as a JSON object with a "description" key.'
    )


def _extract_json(text: str) -> dict[str, Any]:
    """The first JSON object in a model response."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AIAPIError(f"The model did not return JSON: {text[:200]}")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIAPIError(f"The model returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AIAPIError("The model returned JSON that is not an object")
    return value


@dataclass
class AIService:
    """One configured provider of ``iterable.ai``.

    Args:
        provider: Provider name (see :data:`PROVIDERS`).
        model: Model name (provider default when ``None``).
        api_key: API key (provider environment variables when ``None``).
        base_url: Endpoint for local or compatible providers.
        timeout: Request timeout in seconds (where the provider supports it).
        mask_samples: Mask likely PII in sample rows; ``None`` masks for remote
            providers only.
        fail_soft: After the first failed request, warn once and return empty results
            (``--autodoc`` keeps producing the report without AI content).
    """

    provider: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    timeout: int = 30
    mask_samples: bool | None = None
    fail_soft: bool = False
    _client: Any = field(default=None, repr=False)
    _failed: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()
        if self.provider not in PROVIDERS:
            raise AIConfigurationError(
                f"Unknown provider: {self.provider}. Available providers: {', '.join(PROVIDERS)}"
            )

    @property
    def masks_samples(self) -> bool:
        """Whether sample rows are masked before they are sent."""
        if self.mask_samples is not None:
            return self.mask_samples
        return self.provider not in LOCAL_PROVIDERS

    def _check_local_server(self) -> None:
        """Fail fast when a local provider's server is not listening."""
        url = self.base_url or os.environ.get("LLM_BASE_URL") or LOCAL_DEFAULT_URLS[self.provider]
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            socket.create_connection(
                (parsed.hostname or "localhost", port), CONNECT_TIMEOUT
            ).close()
        except OSError as exc:
            raise AIConfigurationError(
                f"{self.provider} is not reachable at {url} ({exc}); start it or pass --ai-base-url"
            ) from exc

    def client(self) -> Any:
        """The ``iterable.ai`` provider instance (created on first use)."""
        if self._client is None:
            if self.provider in LOCAL_PROVIDERS:
                self._check_local_server()
            try:
                from iterable.ai.providers import get_provider

                self._client = get_provider(
                    self.provider, api_key=self.api_key, base_url=self.base_url
                )
            except ImportError as exc:
                raise AIConfigurationError(f"AI support is not available: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 - provider-specific configuration errors
                raise AIConfigurationError(
                    f"Failed to configure {self.provider} provider: {exc}"
                ) from exc
        return self._client

    def _generate(self, prompt: str) -> str:
        try:
            return str(self.client().generate(prompt, model=self.model, temperature=0.2))
        except (AIConfigurationError, AIAPIError):
            raise
        except Exception as exc:  # noqa: BLE001 - network and provider errors
            raise AIAPIError(f"{self.provider} request failed: {exc}") from exc

    def prepare_sample(self, data: str) -> str:
        """Mask (when enabled) and truncate a CSV sample before it is sent."""
        if self.masks_samples and data.strip():
            from iterable.ai.context import redact_for_llm

            reader = csv.DictReader(io.StringIO(data))
            rows = redact_for_llm(list(reader))
            if reader.fieldnames:
                out = io.StringIO()
                writer = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                data = out.getvalue()
        if len(data) > MAX_SAMPLE_CHARS:
            data = data[:MAX_SAMPLE_CHARS] + "\n... (truncated)"
        return data

    def _soft(self, call: Callable[[], T], default: T) -> T:
        """Run ``call``; with ``fail_soft``, turn AI errors into ``default`` (warning once)."""
        if self._failed:
            return default
        try:
            return call()
        except (AIConfigurationError, AIAPIError) as exc:
            if not self.fail_soft:
                raise
            self._failed = True
            logger.warning("AI descriptions skipped: %s", str(exc).rstrip("."))
            return default

    def get_fields_info(self, fields: list[str], language: str = "English") -> dict[str, str]:
        """Descriptions of field names (only names are sent, never values)."""
        return self._soft(lambda: self._fields_info(fields, language), {})

    def _fields_info(self, fields: list[str], language: str) -> dict[str, str]:
        if not fields:
            return {}
        answer = _extract_json(self._generate(_fields_prompt(list(fields), language)))
        return {name: str(answer[name]) for name in fields if answer.get(name) is not None}

    def get_description(self, data: str, language: str = "English") -> str:
        """A short description of a dataset from a CSV sample."""
        return self._soft(lambda: self._description(data, language), "")

    def _description(self, data: str, language: str) -> str:
        text = self._generate(_description_prompt(self.prepare_sample(data), language))
        try:
            return str(_extract_json(text).get("description") or "").strip() or text.strip()
        except AIAPIError:
            return text.strip()

    def get_structured_metadata(
        self, data: str, fields: list[str], language: str = "English"
    ) -> dict[str, Any]:
        """Title, keywords, coverage, theme, ... as a dict."""
        return self._soft(lambda: self._structured_metadata(data, fields, language), {})

    def _structured_metadata(self, data: str, fields: list[str], language: str) -> dict[str, Any]:
        return _extract_json(
            self._generate(_metadata_prompt(self.prepare_sample(data), list(fields), language))
        )
