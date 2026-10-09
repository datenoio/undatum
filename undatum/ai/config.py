"""Configuration management for AI services."""

import os
from pathlib import Path
from typing import Any

import yaml

# API-key variables per provider, in auto-detection order (first set wins; the historical
# providers come first). Azure also needs an endpoint, so it is never auto-detected.
PROVIDER_KEY_VARIABLES: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "perplexity": ("PERPLEXITY_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def _provider_api_keys() -> dict[str, str | None]:
    """The API key set in the environment for each provider (``None`` when unset)."""
    return {
        provider: next((os.environ[name] for name in names if os.getenv(name)), None)
        for provider, names in PROVIDER_KEY_VARIABLES.items()
    }


def find_config_file() -> Path | None:
    """Find configuration file in standard locations.

    Checks:
    1. Current directory: undatum.yaml
    2. Home directory: ~/.undatum/config.yaml

    Returns:
        Path to config file if found, None otherwise
    """
    # Check current directory
    current_dir_config = Path.cwd() / "undatum.yaml"
    if current_dir_config.exists():
        return current_dir_config

    # Check home directory
    home_config = Path.home() / ".undatum" / "config.yaml"
    if home_config.exists():
        return home_config

    return None


def load_config_file() -> dict[str, Any]:
    """Load configuration from YAML file.

    Returns:
        Dictionary with configuration, empty dict if no file found
    """
    config_file = find_config_file()
    if not config_file:
        return {}

    try:
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            return config.get("ai", {})
    except (yaml.YAMLError, OSError, KeyError):
        return {}


def get_env_config() -> dict[str, Any]:
    """Load configuration from environment variables.

    Environment variables:
    - UNDATUM_AI_PROVIDER: Provider name (see ``undatum.ai.PROVIDERS``)
    - UNDATUM_AI_PII_MASK_SAMPLES: Mask likely PII in AI samples (true/false)
    - API keys: see :data:`PROVIDER_KEY_VARIABLES`
    - OLLAMA_BASE_URL: Base URL for Ollama (defaults to http://localhost:11434)
    - LMSTUDIO_BASE_URL: Base URL for LM Studio (defaults to http://localhost:1234/v1)

    Returns:
        Dictionary with configuration from environment
    """
    config = {}

    provider = os.getenv("UNDATUM_AI_PROVIDER")
    if provider:
        config["provider"] = provider
    mask = os.getenv("UNDATUM_AI_PII_MASK_SAMPLES")
    if mask:
        config["pii_mask_samples"] = mask

    # Check for provider-specific API keys
    api_keys = _provider_api_keys()

    # Use the first available API key if provider not specified
    if not provider:
        for prov, key in api_keys.items():
            if key:
                config["provider"] = prov
                config["api_key"] = key
                break
    else:
        # Use provider-specific key
        key = api_keys.get(provider.lower())
        if key:
            config["api_key"] = key

    # Provider-specific base URLs
    ollama_url = os.getenv("OLLAMA_BASE_URL")
    if ollama_url:
        config["ollama_base_url"] = ollama_url

    lmstudio_url = os.getenv("LMSTUDIO_BASE_URL")
    if lmstudio_url:
        config["lmstudio_base_url"] = lmstudio_url

    return config


def merge_config(
    cli_config: dict[str, Any] | None = None,
    file_config: dict[str, Any] | None = None,
    env_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge configurations with precedence: CLI > File > Environment.

    Args:
        cli_config: Configuration from CLI arguments
        file_config: Configuration from config file
        env_config: Configuration from environment variables

    Returns:
        Merged configuration dictionary
    """
    if env_config is None:
        env_config = get_env_config()
    if file_config is None:
        file_config = load_config_file()
    if cli_config is None:
        cli_config = {}

    # Start with environment config (lowest precedence)
    merged = env_config.copy()

    # Override with file config
    merged.update(file_config)

    # Override with CLI config (highest precedence)
    merged.update(cli_config)

    return merged


def get_ai_config(cli_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get AI configuration with proper precedence.

    Args:
        cli_config: Optional CLI configuration to override defaults

    Returns:
        Complete AI configuration dictionary
    """
    return merge_config(cli_config=cli_config)


def get_provider_config(config: dict[str, Any], provider: str) -> dict[str, Any]:
    """Extract provider-specific configuration.

    Args:
        config: Full configuration dictionary
        provider: Provider name

    Returns:
        Provider-specific configuration
    """
    # Map providers to their environment variable API keys
    provider_api_keys = _provider_api_keys()

    # Determine API key: use provider-specific env var if available, otherwise use config
    api_key = None
    if provider.lower() in provider_api_keys:
        # Always prefer provider-specific environment variable
        api_key = provider_api_keys[provider.lower()]

    # Fall back to config api_key if provider-specific env var not set
    if not api_key:
        api_key = config.get("api_key")

    provider_config = {
        "api_key": api_key,
        "model": config.get("model"),
        "timeout": config.get("timeout", 30),
    }

    # Provider-specific base URLs
    if provider == "ollama":
        provider_config["base_url"] = config.get("ollama_base_url") or config.get("base_url")
    elif provider == "lmstudio":
        provider_config["base_url"] = config.get("lmstudio_base_url") or config.get("base_url")
    else:
        provider_config["base_url"] = config.get("base_url")

    return provider_config
