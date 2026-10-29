"""CLI defaults from config files and environment variables.

Precedence (highest last): environment → ``~/.undatum/config.yaml`` →
``undatum.yaml`` in the current directory → explicit CLI flags.

The ``ai:`` mapping is handled separately by :mod:`undatum.ai.config`.
This module reads the ``defaults:`` mapping for command options.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CLI_DEFAULT_KEYS = (
    "engine",
    "threads",
    "progress",
    "encoding",
    "delimiter",
    "quotechar",
    "format_out",
    "cache",
)

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}

_cache: dict[str, Any] | None = None


def clear_cli_defaults_cache() -> None:
    """Drop the resolved-defaults cache (used by tests)."""
    global _cache
    _cache = None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _defaults_from_mapping(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("defaults")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in CLI_DEFAULT_KEYS:
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        if key == "threads":
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in ("progress", "cache"):
            if isinstance(value, bool):
                out[key] = value
            elif isinstance(value, str) and value.strip().lower() in _TRUTHY | _FALSY:
                out[key] = value.strip().lower() in _TRUTHY
        else:
            out[key] = value
    return out


def _env_defaults() -> dict[str, Any]:
    out: dict[str, Any] = {}
    engine = os.getenv("UNDATUM_ENGINE")
    if engine:
        out["engine"] = engine
    threads = os.getenv("UNDATUM_THREADS")
    if threads:
        try:
            out["threads"] = int(threads)
        except ValueError:
            pass
    for key, name in (("progress", "UNDATUM_PROGRESS"), ("cache", "UNDATUM_CACHE")):
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            lowered = value.strip().lower()
            if lowered in _TRUTHY:
                out[key] = True
            elif lowered in _FALSY:
                out[key] = False
    encoding = os.getenv("UNDATUM_ENCODING")
    if encoding:
        out["encoding"] = encoding
    delimiter = os.getenv("UNDATUM_DELIMITER")
    if delimiter:
        out["delimiter"] = delimiter
    quotechar = os.getenv("UNDATUM_QUOTECHAR")
    if quotechar:
        out["quotechar"] = quotechar
    format_out = os.getenv("UNDATUM_FORMAT_OUT")
    if format_out:
        out["format_out"] = format_out
    return out


def config_file_paths() -> dict[str, Path]:
    """Return the standard config locations (may not exist)."""
    return {
        "home": Path.home() / ".undatum" / "config.yaml",
        "project": Path.cwd() / "undatum.yaml",
    }


def get_cli_defaults() -> dict[str, Any]:
    """Return merged CLI defaults.

    Returns:
        Mapping of option names to default values. Empty when nothing is set.
    """
    global _cache
    if _cache is not None:
        return dict(_cache)

    merged: dict[str, Any] = {}
    merged.update(_env_defaults())
    paths = config_file_paths()
    home = paths["home"]
    project = paths["project"]
    if home.is_file():
        merged.update(_defaults_from_mapping(_read_yaml(home)))
    if project.is_file():
        merged.update(_defaults_from_mapping(_read_yaml(project)))
    _cache = dict(merged)
    return dict(merged)


def describe_cli_config() -> dict[str, Any]:
    """Return resolved defaults plus which config files were found."""
    paths = config_file_paths()
    home = paths["home"]
    project = paths["project"]
    return {
        "files": {
            "home": str(home) if home.is_file() else None,
            "project": str(project) if project.is_file() else None,
        },
        "defaults": get_cli_defaults(),
    }
