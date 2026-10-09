"""S3 connector for reading and writing files from/to AWS S3."""

import logging
import os
import tempfile
from typing import BinaryIO

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None
    ClientError = Exception
    NoCredentialsError = Exception

from ..common.path_utils import parse_s3_uri

logger = logging.getLogger(__name__)


def get_s3_client(region: str | None = None, profile: str | None = None):
    """Create and return an S3 client.

    Args:
        region: AWS region (defaults to AWS_REGION env var or us-east-1)
        profile: AWS profile name (defaults to AWS_PROFILE env var)

    Returns:
        boto3 S3 client

    Raises:
        ImportError: If boto3 is not installed
        NoCredentialsError: If AWS credentials are not found
    """
    if not BOTO3_AVAILABLE:
        raise ImportError("boto3 is required for S3 support. Install with: pip install boto3")

    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    elif os.getenv("AWS_PROFILE"):
        session_kwargs["profile_name"] = os.getenv("AWS_PROFILE")

    session = boto3.Session(**session_kwargs)

    client_kwargs = {}
    if region:
        client_kwargs["region_name"] = region
    elif os.getenv("AWS_REGION"):
        client_kwargs["region_name"] = os.getenv("AWS_REGION")

    return session.client("s3", **client_kwargs)


class S3Reader:
    """Reader for S3 objects that provides file-like interface."""

    def __init__(self, s3_uri: str, region: str | None = None, profile: str | None = None):
        """Initialize S3 reader.

        Args:
            s3_uri: S3 URI (s3://bucket/key)
            region: AWS region (optional)
            profile: AWS profile name (optional)
        """
        self.s3_uri = s3_uri
        self.bucket, self.key = parse_s3_uri(s3_uri)
        self.region = region
        self.profile = profile
        self.client = None
        self._temp_file = None
        self._file_handle = None

    def __enter__(self):
        """Context manager entry."""
        self.client = get_s3_client(region=self.region, profile=self.profile)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def open(self, mode: str = "rb") -> BinaryIO:
        """Open S3 object as file-like object.

        For reading, downloads to temporary file and returns file handle.
        This allows existing file reading code to work with S3 URIs.

        Args:
            mode: File mode ('rb' for binary read)

        Returns:
            File-like object

        Raises:
            ValueError: If mode is not 'rb'
            ClientError: If S3 operation fails
        """
        if mode != "rb":
            raise ValueError(f"S3Reader only supports 'rb' mode, got '{mode}'")

        if self._file_handle:
            return self._file_handle

        # Download to temporary file
        try:
            # Create temporary file
            suffix = os.path.splitext(self.key)[1] or ".tmp"
            temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
            os.close(temp_fd)

            # Download from S3
            logger.info(f"Downloading s3://{self.bucket}/{self.key} to temporary file")
            self.client.download_fileobj(self.bucket, self.key, open(temp_path, "wb"))

            self._temp_file = temp_path
            self._file_handle = open(temp_path, mode)
            return self._file_handle

        except ClientError as e:
            if self._temp_file and os.path.exists(self._temp_file):
                os.remove(self._temp_file)
            raise ValueError(f"Failed to download from S3: {e}") from e

    def close(self):
        """Close file handle and clean up temporary file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
        if self._temp_file and os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except OSError:
                pass
            self._temp_file = None


class S3Writer:
    """Writer for S3 objects that provides file-like interface."""

    def __init__(self, s3_uri: str, region: str | None = None, profile: str | None = None):
        """Initialize S3 writer.

        Args:
            s3_uri: S3 URI (s3://bucket/key)
            region: AWS region (optional)
            profile: AWS profile name (optional)
        """
        self.s3_uri = s3_uri
        self.bucket, self.key = parse_s3_uri(s3_uri)
        self.region = region
        self.profile = profile
        self.client = None
        self._temp_file = None
        self._file_handle = None

    def __enter__(self):
        """Context manager entry."""
        self.client = get_s3_client(region=self.region, profile=self.profile)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def open(self, mode: str = "wb") -> BinaryIO:
        """Open S3 object as file-like object for writing.

        For writing, creates temporary file and uploads on close.
        This allows existing file writing code to work with S3 URIs.

        Args:
            mode: File mode ('wb' for binary write)

        Returns:
            File-like object

        Raises:
            ValueError: If mode is not 'wb'
        """
        if mode != "wb":
            raise ValueError(f"S3Writer only supports 'wb' mode, got '{mode}'")

        if self._file_handle:
            return self._file_handle

        # Create temporary file for writing
        suffix = os.path.splitext(self.key)[1] or ".tmp"
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(temp_fd)

        self._temp_file = temp_path
        self._file_handle = open(temp_path, mode)
        return self._file_handle

    def close(self):
        """Close file handle and upload to S3."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

        # Upload to S3 if file was written
        if self._temp_file and os.path.exists(self._temp_file):
            try:
                logger.info(f"Uploading to s3://{self.bucket}/{self.key}")
                self.client.upload_file(self._temp_file, self.bucket, self.key)
            except ClientError as e:
                raise ValueError(f"Failed to upload to S3: {e}") from e
            finally:
                try:
                    os.remove(self._temp_file)
                except OSError:
                    pass
                self._temp_file = None


def open_s3(
    s3_uri: str, mode: str = "rb", region: str | None = None, profile: str | None = None
) -> BinaryIO:
    """Open S3 URI as file-like object.

    Args:
        s3_uri: S3 URI (s3://bucket/key)
        mode: File mode ('rb' for read, 'wb' for write)
        region: AWS region (optional)
        profile: AWS profile name (optional)

    Returns:
        File-like object (context manager)

    Raises:
        ImportError: If boto3 is not installed
        ValueError: If mode is not supported or URI is invalid
    """
    if mode == "rb":
        reader = S3Reader(s3_uri, region=region, profile=profile)
        reader.__enter__()
        return reader.open(mode)
    elif mode == "wb":
        writer = S3Writer(s3_uri, region=region, profile=profile)
        writer.__enter__()
        return writer.open(mode)
    else:
        raise ValueError(f"Unsupported mode for S3: {mode}")
