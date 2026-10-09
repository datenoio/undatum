"""AI helpers for ``--autodoc`` (dataset and field descriptions, structured metadata).

All requests go through iterabledata's ``iterable.ai`` providers, the same stack as
``undatum ai``. Configuration keeps the historical names: ``UNDATUM_AI_PROVIDER``,
``--ai-provider`` / ``--ai-model`` / ``--ai-base-url``, the ``ai:`` section of
``undatum.yaml`` and provider API-key variables.
"""

from __future__ import annotations

from typing import Any

from .base import AIAPIError, AIConfigurationError, AIServiceError
from .config import get_ai_config, get_provider_config
from .service import LOCAL_PROVIDERS, PROVIDERS, AIService


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def get_ai_service(provider: str | None = None, config: dict[str, Any] | None = None) -> AIService:
    """Return a configured :class:`AIService`.

    Args:
        provider: Provider name (``openai``, ``anthropic``, ``gemini``, ``azure``,
            ``openrouter``, ``ollama``, ``lmstudio``, ``perplexity``,
            ``openai-compatible``); taken from the configuration when ``None``.
        config: Overrides (``model``, ``base_url``, ``api_key``, ``timeout``,
            ``pii_mask_samples``) on top of environment and config-file settings.

    Returns:
        The service; the provider client is created and checked immediately.

    Raises:
        AIConfigurationError: If no provider is configured or it cannot be set up.

    Examples:
        >>> service = get_ai_service("ollama", {"model": "llama3.2"})
    """
    full_config = get_ai_config(config or {})
    provider_name = (provider or full_config.get("provider") or "").lower()
    if not provider_name:
        raise AIConfigurationError(
            "No AI provider specified. Set UNDATUM_AI_PROVIDER or a provider API key "
            "(OPENAI_API_KEY, ANTHROPIC_API_KEY, ...), configure it in undatum.yaml, "
            "or pass --ai-provider."
        )
    provider_config = get_provider_config(full_config, provider_name)
    service = AIService(
        provider=provider_name,
        model=provider_config.get("model"),
        api_key=provider_config.get("api_key"),
        base_url=provider_config.get("base_url"),
        timeout=int(provider_config.get("timeout") or 30),
        mask_samples=_as_bool(full_config.get("pii_mask_samples")),
    )
    service.client()
    return service


def get_fields_info(
    fields: list[str] | str, language: str = "English", ai_service: AIService | None = None
) -> dict[str, str]:
    """Descriptions of field names (``fields`` may be a comma-separated string)."""
    service = ai_service or get_ai_service()
    names = [f.strip() for f in fields.split(",")] if isinstance(fields, str) else list(fields)
    return service.get_fields_info(names, language)


def get_description(
    data: str, language: str = "English", ai_service: AIService | None = None
) -> str:
    """A short dataset description from a CSV sample."""
    return (ai_service or get_ai_service()).get_description(data, language)


def get_structured_metadata(
    data: str,
    fields: list[str] | str,
    language: str = "English",
    ai_service: AIService | None = None,
) -> dict[str, Any]:
    """Structured metadata (title, keywords, coverage, theme, ...) from a CSV sample."""
    names = [f.strip() for f in fields.split(",")] if isinstance(fields, str) else list(fields)
    return (ai_service or get_ai_service()).get_structured_metadata(data, names, language)


__all__ = [
    "LOCAL_PROVIDERS",
    "PROVIDERS",
    "AIAPIError",
    "AIConfigurationError",
    "AIService",
    "AIServiceError",
    "get_ai_config",
    "get_ai_service",
    "get_description",
    "get_fields_info",
    "get_provider_config",
    "get_structured_metadata",
]
