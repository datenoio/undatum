"""Path and URI utilities for local and remote file handling."""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .errors import DependencyError

# Google Cloud Storage
GCS_URI_SCHEMES = ("gs", "gcs")
# Azure Blob Storage / Azure Data Lake
AZURE_URI_SCHEMES = ("az", "abfs", "abfss")
# Hadoop-style S3 plus GCS/Azure: iterabledata opens these via fsspec.
NATIVE_CLOUD_URI_SCHEMES = GCS_URI_SCHEMES + AZURE_URI_SCHEMES + ("s3a",)
# All object-storage schemes undatum treats as cloud paths (includes boto3 s3://).
CLOUD_URI_SCHEMES = ("s3",) + NATIVE_CLOUD_URI_SCHEMES

_CLOUD_EXTRA_BY_SCHEME = {
    "gs": ("gcsfs", 'pip install "undatum[gcs]" or pip install "undatum[cloud]"'),
    "gcs": ("gcsfs", 'pip install "undatum[gcs]" or pip install "undatum[cloud]"'),
    "az": ("adlfs", 'pip install "undatum[azure]" or pip install "undatum[cloud]"'),
    "abfs": ("adlfs", 'pip install "undatum[azure]" or pip install "undatum[cloud]"'),
    "abfss": ("adlfs", 'pip install "undatum[azure]" or pip install "undatum[cloud]"'),
    "s3a": ("s3fs", 'pip install "undatum[cloud]"'),
    "s3": ("boto3", 'pip install "undatum[s3]" or pip install "undatum[cloud]"'),
}


def _uri_scheme(path: str) -> str:
    """Return the lowercase URI scheme, or empty string for local paths."""
    if not isinstance(path, str):
        return ""
    return urllib.parse.urlparse(path).scheme.lower()


def is_uri(path: str) -> bool:
    """Check if a path is a URI (s3://, http://, https://, etc.).

    Args:
        path: Path string to check

    Returns:
        True if path is a URI, False if local path
    """
    return bool(_uri_scheme(path))


def is_s3_uri(path: str) -> bool:
    """Check if a path is an S3 URI.

    Args:
        path: Path string to check

    Returns:
        True if path is an S3 URI (s3://...)
    """
    return _uri_scheme(path) == "s3"


def is_gcs_uri(path: str) -> bool:
    """Check if a path is a Google Cloud Storage URI (gs:// or gcs://)."""
    return _uri_scheme(path) in GCS_URI_SCHEMES


def is_azure_uri(path: str) -> bool:
    """Check if a path is an Azure Blob/ADLS URI (az://, abfs://, abfss://)."""
    return _uri_scheme(path) in AZURE_URI_SCHEMES


def is_native_cloud_uri(path: str) -> bool:
    """Check if a path is a cloud URI opened natively via iterabledata/fsspec.

    Covers GCS, Azure, and ``s3a://`` but not plain ``s3://`` (boto3 path).
    """
    return _uri_scheme(path) in NATIVE_CLOUD_URI_SCHEMES


def is_cloud_uri(path: str) -> bool:
    """Check if a path is any supported object-storage URI."""
    return _uri_scheme(path) in CLOUD_URI_SCHEMES


def is_http_uri(path: str) -> bool:
    """Check if a path is an HTTP/HTTPS URI.

    Args:
        path: Path string to check

    Returns:
        True if path is HTTP/HTTPS URI
    """
    return _uri_scheme(path) in ("http", "https")


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Parse S3 URI into bucket and key.

    Args:
        s3_uri: S3 URI in format s3://bucket/path/to/file

    Returns:
        Tuple of (bucket, key)

    Raises:
        ValueError: If URI format is invalid
    """
    parsed = urllib.parse.urlparse(s3_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Invalid S3 URI scheme: {s3_uri}")

    bucket = parsed.netloc
    if not bucket:
        raise ValueError(f"Missing bucket in S3 URI: {s3_uri}")

    key = parsed.path.lstrip("/")
    if not key:
        raise ValueError(f"Missing key/path in S3 URI: {s3_uri}")

    return bucket, key


def parse_cloud_uri(uri: str) -> tuple[str, str, str]:
    """Parse a cloud object URI into scheme, bucket/container, and key.

    Args:
        uri: Cloud URI (s3://, gs://, az://, abfs://, ...)

    Returns:
        Tuple of (scheme, bucket_or_container, key)

    Raises:
        ValueError: If URI format is invalid or the scheme is not a cloud scheme
    """
    parsed = urllib.parse.urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme not in CLOUD_URI_SCHEMES:
        raise ValueError(f"Unsupported cloud URI scheme: {uri}")

    bucket = parsed.netloc
    if not bucket:
        raise ValueError(f"Missing bucket or container in cloud URI: {uri}")

    key = parsed.path.lstrip("/")
    if not key:
        raise ValueError(f"Missing key/path in cloud URI: {uri}")

    return scheme, bucket, key


def cloud_object_suffix(path: str) -> str:
    """Return a temp-file suffix from a cloud object key, defaulting to ``.tmp``."""
    try:
        _, _, key = parse_cloud_uri(path)
    except ValueError:
        key = path.split("?")[0]
    return os.path.splitext(key)[1] or ".tmp"


def missing_cloud_extra_error(path: str, cause: BaseException | None = None) -> DependencyError:
    """Build a DependencyError telling the user which cloud extra to install.

    Args:
        path: Cloud URI that triggered the missing dependency
        cause: Optional exception to chain

    Returns:
        DependencyError ready to raise
    """
    from .errors import DependencyError

    scheme = _uri_scheme(path)
    package, install_command = _CLOUD_EXTRA_BY_SCHEME.get(
        scheme, ("fsspec", 'pip install "undatum[cloud]"')
    )
    feature = f"{scheme}:// cloud storage" if scheme else "cloud storage"
    error = DependencyError(package, feature=feature, install_command=install_command)
    if cause is not None:
        error.__cause__ = cause
    return error


def looks_like_missing_cloud_dep(path: str, exc: BaseException) -> bool:
    """Return True if ``exc`` is a missing fsspec/gcsfs/adlfs/s3fs dependency."""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return True
    scheme = _uri_scheme(path)
    package, _ = _CLOUD_EXTRA_BY_SCHEME.get(scheme, ("fsspec", ""))
    text = str(exc).lower()
    needles = (
        f"no module named '{package}'",
        f"no module named {package}",
        f"install {package}",
        f"protocol not known: {scheme}",
    )
    return any(needle in text for needle in needles)


def normalize_path(path: str) -> str:
    """Normalize a path (local or URI).

    Args:
        path: Path to normalize

    Returns:
        Normalized path
    """
    if is_uri(path):
        # For URIs, just return as-is (no normalization needed)
        return path
    # For local paths, normalize
    return os.path.normpath(path)


def resolve_path(path: str) -> str:
    """Resolve a path to absolute path (for local paths only).

    Args:
        path: Path to resolve

    Returns:
        Resolved absolute path (or original URI if URI)
    """
    if is_uri(path):
        # URIs don't need resolution
        return path
    return os.path.abspath(path)


def validate_file_path(file_path: str, check_read: bool = True, check_write: bool = False) -> None:
    """Validate that a file path exists and has required permissions.

    Args:
        file_path: Path to validate
        check_read: If True, check that file is readable
        check_write: If True, check that file is writable

    Raises:
        FileNotFoundError: If file does not exist
        PermissionError: If file doesn't have required permissions
    """
    from .errors import FileNotFoundError, PermissionError, find_similar_files

    if is_uri(file_path):
        # For URIs, we can't validate existence locally
        return

    path = Path(file_path)

    if not path.exists():
        suggestions = find_similar_files(file_path)
        raise FileNotFoundError(file_path, suggestions)

    if check_read and not os.access(file_path, os.R_OK):
        raise PermissionError(file_path, operation="read")

    if check_write and not os.access(file_path, os.W_OK):
        raise PermissionError(file_path, operation="write")


def validate_directory_path(dir_path: str, check_write: bool = False) -> None:
    """Validate that a directory path exists and has required permissions.

    Args:
        dir_path: Path to directory to validate
        check_write: If True, check that directory is writable

    Raises:
        FileNotFoundError: If directory does not exist
        PermissionError: If directory doesn't have required permissions
    """
    from .errors import FileNotFoundError, PermissionError

    if is_uri(dir_path):
        # For URIs, we can't validate existence locally
        return

    path = Path(dir_path)

    if not path.exists():
        raise FileNotFoundError(dir_path)

    if not path.is_dir():
        raise ValueError(f"Path is not a directory: {dir_path}")

    if check_write and not os.access(dir_path, os.W_OK):
        raise PermissionError(dir_path, operation="write")
