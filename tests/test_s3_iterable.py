"""Tests for S3 iterable integration."""

from unittest.mock import MagicMock, patch

import pytest

from undatum.common.s3_iterable import open_iterable_with_s3


def _unwrap(result):
    """S3 reads are wrapped so closing them removes the downloaded temp file."""
    from undatum.common.s3_iterable import _TempFileCleanupIterable

    return result._inner if isinstance(result, _TempFileCleanupIterable) else result


class TestOpenIterableWithS3:
    """Test open_iterable_with_s3 function."""

    @pytest.fixture(autouse=True)
    def _boto3_path(self, monkeypatch):
        """These tests cover the boto3 download path (used when s3fs is missing)."""
        monkeypatch.setattr("undatum.common.s3_iterable._s3fs_available", lambda: False)

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=False)
    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_local_file(self, mock_open_iterable, mock_is_s3_uri):
        """Test opening local file."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("/local/path/file.jsonl", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        mock_is_s3_uri.assert_called_with("/local/path/file.jsonl")
        assert mock_is_s3_uri.call_count >= 1
        mock_open_iterable.assert_called_once_with(
            "/local/path/file.jsonl", mode="r", iterableargs={}
        )

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_read(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test opening S3 file for reading."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "path/to/file.jsonl")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.jsonl"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True

        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("s3://my-bucket/path/to/file.jsonl", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        mock_get_client.assert_called_once_with(region=None, profile=None)
        mock_client.download_file.assert_called_once_with(
            "my-bucket", "path/to/file.jsonl", mock_temp_file
        )
        mock_open_iterable.assert_called_once_with(mock_temp_file, mode="r", iterableargs={})
        mock_close.assert_called_once_with(mock_fd)
        mock_remove.assert_called_once_with(mock_temp_file)

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_s3_file_write_delegates_to_native_cloud(self, mock_open_iterable, mock_is_s3_uri):
        """S3 write mode delegates to iterabledata's native cloud support."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("s3://bucket/key.jsonl", mode="w") as result:
            assert _unwrap(result) is mock_iterable

        mock_open_iterable.assert_called_once_with(
            "s3://bucket/key.jsonl", mode="w", iterableargs={}
        )

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_gcs_file_delegates_to_native_cloud(self, mock_open_iterable):
        """GCS URIs are opened directly via iterabledata (read and write)."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("gs://bucket/data.jsonl", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        mock_open_iterable.assert_called_once_with(
            "gs://bucket/data.jsonl", mode="r", iterableargs={}
        )

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_gcs_alias_delegates_to_native_cloud(self, mock_open_iterable):
        """gcs:// is treated the same as gs://."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("gcs://bucket/data.jsonl", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        mock_open_iterable.assert_called_once_with(
            "gcs://bucket/data.jsonl", mode="r", iterableargs={}
        )

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_azure_file_delegates_to_native_cloud(self, mock_open_iterable):
        """Azure URIs are opened directly via iterabledata (read and write)."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("az://container/data.jsonl", mode="w") as result:
            assert _unwrap(result) is mock_iterable

        mock_open_iterable.assert_called_once_with(
            "az://container/data.jsonl", mode="w", iterableargs={}
        )

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_gcs_missing_extra_raises_dependency_error(self, mock_open_iterable):
        """Missing gcsfs becomes a DependencyError with an install hint."""
        from undatum.common.errors import DependencyError

        mock_open_iterable.side_effect = ImportError("No module named 'gcsfs'")
        with pytest.raises(DependencyError, match="undatum\\[gcs\\]"):
            with open_iterable_with_s3("gs://bucket/data.jsonl", mode="r"):
                pass

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_path_azure_delegates_to_native_cloud(self, mock_open_iterable):
        from undatum.common.s3_iterable import open_path

        mock_open_iterable.return_value = MagicMock()
        result = open_path("abfs://container/data.csv", mode="r")
        mock_open_iterable.assert_called_once_with(
            "abfs://container/data.csv", mode="r", iterableargs={}
        )
        assert result is mock_open_iterable.return_value

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_with_region(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test opening S3 file with region specified."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "file.jsonl")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.jsonl"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True

        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3(
            "s3://my-bucket/file.jsonl", mode="r", region="us-east-1"
        ) as result:
            assert _unwrap(result) is mock_iterable

        mock_get_client.assert_called_once_with(region="us-east-1", profile=None)

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_with_profile(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test opening S3 file with profile specified."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "file.jsonl")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.jsonl"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True

        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3(
            "s3://my-bucket/file.jsonl", mode="r", profile="myprofile"
        ) as result:
            assert _unwrap(result) is mock_iterable

        mock_get_client.assert_called_once_with(region=None, profile="myprofile")

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_cleanup_on_error(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test that temp file is cleaned up even on error."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "file.jsonl")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.jsonl"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True

        mock_open_iterable.side_effect = ValueError("Test error")

        with pytest.raises(ValueError):
            with open_iterable_with_s3("s3://my-bucket/file.jsonl", mode="r"):
                pass

        mock_remove.assert_called_once_with(mock_temp_file)

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_no_extension(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test opening S3 file without extension."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "file")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.tmp"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True

        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        with open_iterable_with_s3("s3://my-bucket/file", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        # Should use .tmp suffix when no extension
        assert mock_mkstemp.called

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=True)
    @patch("undatum.common.s3_iterable.parse_s3_uri")
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("tempfile.mkstemp")
    @patch("os.close")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_open_s3_file_remove_error(
        self,
        mock_remove,
        mock_exists,
        mock_close,
        mock_mkstemp,
        mock_open_iterable,
        mock_get_client,
        mock_parse_uri,
        mock_is_s3_uri,
    ):
        """Test handling error when removing temp file."""
        mock_is_s3_uri.return_value = True
        mock_parse_uri.return_value = ("my-bucket", "file.jsonl")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_fd = 123
        mock_temp_file = "/tmp/temp123.jsonl"
        mock_mkstemp.return_value = (mock_fd, mock_temp_file)
        mock_exists.return_value = True
        mock_remove.side_effect = OSError("Permission denied")

        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        # Should not raise, just log warning
        with open_iterable_with_s3("s3://my-bucket/file.jsonl", mode="r") as result:
            assert _unwrap(result) is mock_iterable

        mock_remove.assert_called_once_with(mock_temp_file)

    @patch("undatum.common.s3_iterable.is_s3_uri", return_value=False)
    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_local_file_with_iterableargs(self, mock_open_iterable, mock_is_s3_uri):
        """Test opening local file with iterableargs."""
        mock_iterable = MagicMock()
        mock_open_iterable.return_value = mock_iterable

        iterableargs = {"delimiter": ",", "encoding": "utf-8"}
        with open_iterable_with_s3(
            "/local/path/file.csv", mode="r", iterableargs=iterableargs
        ) as result:
            assert _unwrap(result) is mock_iterable

        mock_open_iterable.assert_called_once_with(
            "/local/path/file.csv", mode="r", iterableargs=iterableargs
        )


class TestConnectorPluginIntegration:
    """Test connector plugin wiring in open_path."""

    def _make_connector(self, payload: bytes):
        import io

        connector = MagicMock()
        connector.name = "test-connector"
        connector.open.return_value = io.BytesIO(payload)
        return connector

    @patch("undatum.common.s3_iterable.open_iterable")
    @patch("undatum.common.s3_iterable._find_plugin_connector")
    def test_open_path_uses_connector(self, mock_find, mock_open_iterable):
        """open_path should download via connector plugin for custom schemes."""
        from undatum.common.s3_iterable import open_path

        mock_find.return_value = self._make_connector(b'{"a": 1}\n')
        mock_inner = MagicMock()
        mock_open_iterable.return_value = mock_inner

        result = open_path("myproto://host/data.jsonl", mode="r")

        mock_find.assert_called_once_with("myproto://host/data.jsonl")
        # open_iterable is called with the downloaded temp file, not the URI
        temp_path = mock_open_iterable.call_args[0][0]
        assert temp_path.endswith(".jsonl")
        result.close()

    @patch("undatum.common.s3_iterable.open_iterable")
    def test_open_path_no_connector_for_local(self, mock_open_iterable):
        """Local paths must not consult the plugin registry."""
        from undatum.common.s3_iterable import open_path

        mock_open_iterable.return_value = MagicMock()
        open_path("/local/file.csv", mode="r")
        mock_open_iterable.assert_called_once_with("/local/file.csv", mode="r", iterableargs={})

    @patch("undatum.common.s3_iterable._find_plugin_connector")
    def test_open_path_connector_write_unsupported(self, mock_find):
        """Write mode through a connector plugin should raise."""
        from undatum.common.s3_iterable import open_path

        mock_find.return_value = self._make_connector(b"")
        with pytest.raises(NotImplementedError):
            open_path("myproto://host/data.jsonl", mode="w")


class TestStreamingS3:
    """With s3fs installed, s3:// reads stream through fsspec."""

    @patch("undatum.common.s3_iterable._s3fs_available", return_value=True)
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    def test_s3_read_streams_with_region_and_profile(self, mock_open, mock_client, _available):
        from undatum.common.s3_iterable import open_path

        open_path("s3://bucket/data.csv", region="eu-west-1", profile="prod")
        mock_client.assert_not_called()  # no boto3 download
        args, kwargs = mock_open.call_args
        assert args[0] == "s3://bucket/data.csv"
        options = kwargs["iterableargs"]["storage_options"]
        assert options["profile"] == "prod"
        assert options["client_kwargs"] == {"region_name": "eu-west-1"}

    @patch("undatum.common.s3_iterable._s3fs_available", return_value=False)
    @patch("undatum.common.s3_iterable.parse_s3_uri", return_value=("bucket", "data.csv"))
    @patch("undatum.common.s3_iterable.get_s3_client")
    @patch("undatum.common.s3_iterable.open_iterable")
    def test_s3_read_downloads_without_s3fs(self, mock_open, mock_client, _parse, _available):
        from undatum.common.s3_iterable import open_path

        result = open_path("s3://bucket/data.csv")
        mock_client.return_value.download_file.assert_called_once()
        result.close()
