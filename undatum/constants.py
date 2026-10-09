"""Constants and configuration values for the undatum package.

Supported format and compression-codec lists are derived at import time from the
``iterabledata`` (``iterable``) package, which is the I/O foundation for undatum.
This means undatum automatically recognizes every format and codec the underlying
engine supports (100+ formats, 12 codecs) instead of a small hardcoded whitelist.
Static fallback lists are used only when ``iterabledata`` cannot be imported.
"""

import logging

logger = logging.getLogger(__name__)

DATE_PATTERNS = [
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y %H:%M",
]
DEFAULT_DICT_SHARE = 70


# Document formats handled by undatum's own ``extract`` command rather than by
# iterabledata; always merged into the supported-types list.
EXTRACT_FILE_TYPES = ["pdf", "doc", "docx"]

# Static fallbacks used only when iterabledata is unavailable at import time.
_FALLBACK_SUPPORTED_FILE_TYPES = [
    "xls",
    "xlsx",
    "csv",
    "xml",
    "json",
    "jsonl",
    "yaml",
    "tsv",
    "sql",
    "bson",
    "parquet",
    "orc",
    "avro",
]
_FALLBACK_COMPRESSED_FILE_TYPES = ["gz", "xz", "zip", "lz4", "7z", "bz2"]
_FALLBACK_TEXT_DATA_TYPES = ["csv", "json", "jsonl", "xml", "yaml", "tsv", "sql"]


def _build_supported_file_types() -> list[str]:
    """Return all format ids/aliases known to iterabledata plus undatum extras."""
    try:
        from iterable.helpers.detect import DATATYPE_REGISTRY

        types = set(DATATYPE_REGISTRY.keys())
    except Exception as e:  # noqa: BLE001 - any import failure falls back
        logger.debug("Falling back to static SUPPORTED_FILE_TYPES: %s", e)
        types = set(_FALLBACK_SUPPORTED_FILE_TYPES)
    types.update(EXTRACT_FILE_TYPES)
    return sorted(types)


def _build_compressed_file_types() -> list[str]:
    """Return all compression-codec extensions known to iterabledata."""
    try:
        from iterable.helpers.detect import CODEC_REGISTRY

        codecs = {c for c in CODEC_REGISTRY if c not in ("raw",)}
    except Exception as e:  # noqa: BLE001 - any import failure falls back
        logger.debug("Falling back to static COMPRESSED_FILE_TYPES: %s", e)
        codecs = set(_FALLBACK_COMPRESSED_FILE_TYPES)
    return sorted(codecs)


def _build_text_data_types() -> list[str]:
    """Return text-based format ids from iterabledata merged with undatum extras."""
    text = set(_FALLBACK_TEXT_DATA_TYPES)
    try:
        from iterable.helpers.detect import TEXT_DATA_TYPES as _ITER_TEXT

        text.update(_ITER_TEXT)
    except Exception as e:  # noqa: BLE001 - any import failure falls back
        logger.debug("Falling back to static TEXT_DATA_TYPES: %s", e)
    return sorted(text)


_LAZY: dict[str, list[str]] = {}


def __getattr__(name: str) -> list[str]:
    """Build the iterabledata-derived lists on first use.

    Importing iterabledata takes about a second, so ``SUPPORTED_FILE_TYPES``,
    ``COMPRESSED_FILE_TYPES``, ``TEXT_DATA_TYPES`` and ``BINARY_FILE_TYPES`` are computed
    only when a command actually reads them.
    """
    if name not in (
        "SUPPORTED_FILE_TYPES",
        "COMPRESSED_FILE_TYPES",
        "TEXT_DATA_TYPES",
        "BINARY_FILE_TYPES",
    ):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name not in _LAZY:
        if name == "SUPPORTED_FILE_TYPES":
            _LAZY[name] = _build_supported_file_types()
        elif name == "COMPRESSED_FILE_TYPES":
            _LAZY[name] = _build_compressed_file_types()
        elif name == "TEXT_DATA_TYPES":
            _LAZY[name] = _build_text_data_types()
        else:
            supported = set(__getattr__("SUPPORTED_FILE_TYPES"))
            text = set(__getattr__("TEXT_DATA_TYPES"))
            _LAZY[name] = sorted((supported - text) | set(__getattr__("COMPRESSED_FILE_TYPES")))
    return _LAZY[name]


DEFAULT_OPTIONS = {"encoding": "utf8", "delimiter": ",", "limit": 1000}

DUCKABLE_FILE_TYPES = ["csv", "jsonl", "json", "parquet"]
# iterabledata reports gzip as "gz"; accept both "gz" and "gzip"
DUCKABLE_CODECS = ["zst", "gz", "gzip", "raw"]

EU_DATA_THEMES = [
    {"label": "AGRI", "uri": "http://publications.europa.eu/resource/authority/data-theme/AGRI"},
    {"label": "ECON", "uri": "http://publications.europa.eu/resource/authority/data-theme/ECON"},
    {"label": "EDUC", "uri": "http://publications.europa.eu/resource/authority/data-theme/EDUC"},
    {"label": "ENVI", "uri": "http://publications.europa.eu/resource/authority/data-theme/ENVI"},
    {"label": "ENER", "uri": "http://publications.europa.eu/resource/authority/data-theme/ENER"},
    {"label": "GOVE", "uri": "http://publications.europa.eu/resource/authority/data-theme/GOVE"},
    {"label": "HEAL", "uri": "http://publications.europa.eu/resource/authority/data-theme/HEAL"},
    {"label": "INTR", "uri": "http://publications.europa.eu/resource/authority/data-theme/INTR"},
    {"label": "JUST", "uri": "http://publications.europa.eu/resource/authority/data-theme/JUST"},
    {"label": "REGI", "uri": "http://publications.europa.eu/resource/authority/data-theme/REGI"},
    {"label": "SOCI", "uri": "http://publications.europa.eu/resource/authority/data-theme/SOCI"},
    {"label": "TECH", "uri": "http://publications.europa.eu/resource/authority/data-theme/TECH"},
    {"label": "TRAN", "uri": "http://publications.europa.eu/resource/authority/data-theme/TRAN"},
]
