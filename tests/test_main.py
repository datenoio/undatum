"""Tests for main entry point."""

import sys
from unittest.mock import patch

import pytest

from undatum.__main__ import main
from undatum.common.errors import UndatumError, ValidationError


class TestMain:
    """Test main entry point."""

    @patch("undatum.__main__.app")
    def test_main_success(self, mock_app):
        """Test main function with successful execution."""
        mock_app.return_value = None
        main()
        mock_app.assert_called_once()

    @patch("undatum.__main__.app")
    def test_main_keyboard_interrupt(self, mock_app):
        """Test main function with keyboard interrupt exits 130."""
        mock_app.side_effect = KeyboardInterrupt()
        with patch("builtins.print") as mock_print:
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 130
            mock_print.assert_called_once_with("Interrupted", file=sys.stderr)

    @patch("undatum.__main__.app")
    def test_main_undatum_error(self, mock_app):
        """Test main function with UndatumError uses its exit code."""
        mock_app.side_effect = UndatumError("Test error", exit_code=2)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    @patch("undatum.__main__.app")
    def test_main_validation_error(self, mock_app):
        """Test main function with ValidationError exits 1."""
        mock_app.side_effect = ValidationError("Bad input")
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("undatum.__main__.app")
    def test_main_other_exception(self, mock_app):
        """Test main function handles unexpected exceptions gracefully."""
        mock_app.side_effect = ValueError("Test error")
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0

    def test_cli_missing_file_exits_1(self, monkeypatch):
        """undatum CLI exits 1 for a missing input file."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["undatum", "head", "/definitely/missing/undatum-no-such.csv"],
        )
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("undatum.__main__.app")
    def test_cli_dependency_error_exits_2(self, mock_app):
        """Missing optional dependency exits 2."""
        from undatum.common.errors import DependencyError

        mock_app.side_effect = DependencyError("fastapi", feature="api")
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_cli_unreadable_file_exits_3(self, tmp_path, monkeypatch):
        """Permission denied on an input file exits 3."""
        import os
        import stat

        if sys.platform == "win32":
            pytest.skip("chmod-based permission test is Unix-only")
        path = tmp_path / "secret.csv"
        path.write_text("name,age\nAlice,30\n", encoding="utf-8")
        os.chmod(path, 0)
        if os.access(path, os.R_OK):
            pytest.skip("process can still read a chmod-0 file")
        monkeypatch.setattr(sys, "argv", ["undatum", "head", str(path)])
        try:
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 3
        finally:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def test_manpage_documents_commands_and_exit_codes():
    """Shipped man page lists core commands and the exit-code contract."""
    from pathlib import Path

    manpage = Path(__file__).resolve().parents[1] / "man" / "undatum.1"
    text = manpage.read_text(encoding="utf-8")
    assert ".TH UNDATUM 1" in text
    assert ".B convert" in text
    assert ".B sql" in text
    assert ".B config show" in text
    assert ".B 1" in text
    assert "User error" in text
