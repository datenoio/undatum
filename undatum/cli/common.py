"""Shared helpers for CLI modules."""

import logging
from typing import Annotated, Any

import typer
from rich.console import Console

console = Console()

AI_PROVIDER_HELP = (
    "AI provider: openai, anthropic, gemini, azure, openrouter, ollama, lmstudio, perplexity "
    "or openai-compatible (default: UNDATUM_AI_PROVIDER or the ai: section of undatum.yaml)."
)

# Tri-state: None masks samples for remote AI providers only (the default).
AIMaskSamplesOpt = Annotated[
    bool | None,
    typer.Option(
        "--pii-mask-samples/--no-pii-mask-samples",
        help=(
            "Mask likely PII in sample rows sent to the AI provider with --autodoc. "
            "Default: masked for remote providers, unmasked for ollama and lmstudio."
        ),
        show_default=False,
    ),
]


# Verbosity levels: -q (errors only), default (warnings), -v (info), -vv (debug).
_LEVELS = {-1: logging.ERROR, 0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


def configure_logging(verbosity: int = 0) -> None:
    """Configure stderr logging for the CLI.

    The default shows only warnings and errors, so a successful command prints
    nothing to stderr. Debug output adds timestamps and logger names.

    Args:
        verbosity: -1 for errors only, 0 for warnings, 1 for info, 2 or more for debug.
    """
    level = _LEVELS[max(-1, min(verbosity, 2))]
    if level <= logging.DEBUG:
        fmt = "%(asctime)s %(name)s %(levelname)s: %(message)s"
    else:
        fmt = "%(levelname)s: %(message)s"
    logging.basicConfig(format=fmt, level=level, force=True)
    # Third-party libraries stay quiet unless debugging.
    for noisy in ("urllib3", "httpx", "asyncio", "matplotlib", "elastic_transport"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def enable_verbose():
    """Enable debug logging (per-command ``--verbose``; same as the global ``-vv``)."""
    configure_logging(2)


def build_ai_config(
    model: str | None = None, base_url: str | None = None, mask_samples: bool | None = None
) -> dict[str, Any] | None:
    """The ``ai_config`` option dict of the ``--autodoc`` commands (``None`` when empty)."""
    config: dict[str, Any] = {}
    if model:
        config["model"] = model
    if base_url:
        config["base_url"] = base_url
    if mask_samples is not None:
        config["pii_mask_samples"] = mask_samples
    return config or None
