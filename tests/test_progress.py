"""Tests for progress indication utilities."""

from unittest.mock import MagicMock, patch

from undatum.common.progress import (
    ProgressBar,
    _NoProgress,
    is_tty,
    progress,
    progress_bar,
    set_progress_description,
    set_progress_postfix,
    update_progress,
    wrap_iterable,
)


class TestIsTty:
    """Test is_tty function."""

    def test_is_tty_with_real_stdout(self):
        """Test is_tty with real stdout."""
        # This will depend on the actual environment
        result = is_tty()
        assert isinstance(result, bool)

    @patch("sys.stderr")
    def test_is_tty_with_mock_stdout(self, mock_stdout):
        """Progress goes to stderr, so the TTY check looks at stderr."""
        mock_stdout.isatty.return_value = True
        assert is_tty() is True

        mock_stdout.isatty.return_value = False
        assert is_tty() is False

    @patch("sys.stderr")
    def test_is_tty_no_isatty_method(self, mock_stdout):
        """Test is_tty when stderr doesn't have isatty method."""
        del mock_stdout.isatty
        assert is_tty() is False


class TestProgressBar:
    """Test progress_bar context manager."""

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_bar_enabled(self, mock_is_tty):
        """An enabled bar counts updates and stops on exit."""
        with progress_bar(total=100, desc="Test", unit="items") as pbar:
            assert isinstance(pbar, ProgressBar)
            pbar.update(10)
            pbar.update(5)
            assert pbar._progress.tasks[0].completed == 15
        assert pbar._closed

    @patch("undatum.common.progress.is_tty", return_value=False)
    def test_progress_bar_not_tty(self, mock_is_tty):
        """Test progress bar when not a TTY."""
        with progress_bar(total=100, desc="Test") as pbar:
            assert pbar is None

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_bar_disabled(self, mock_is_tty):
        """Test progress bar when disabled."""
        with progress_bar(total=100, desc="Test", disable=True) as pbar:
            assert pbar is None

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_bar_show_progress_false(self, mock_is_tty):
        """Test progress bar when show_progress is False."""
        with progress_bar(total=100, desc="Test", show_progress=False) as pbar:
            assert pbar is None

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_bar_unknown_total_closes_cleanly(self, mock_is_tty):
        """An indeterminate bar (total=None) can be updated and closed."""
        with progress_bar(total=None, desc="Repacking", unit="B") as pbar:
            assert pbar is not None
            pbar.update(10)
            pbar.total = 10
            assert pbar.total == 10


class TestProgress:
    """Test the progress() factory and ProgressBar iteration."""

    @patch("undatum.common.progress.is_tty", return_value=False)
    def test_progress_not_tty_is_noop(self, mock_is_tty):
        bar = progress([1, 2], desc="x", total=2, leave=False)
        assert isinstance(bar, _NoProgress)
        assert list(bar) == [1, 2]
        with bar as same:
            same.update(1)
            same.set_postfix({"a": 1})

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_iterates_and_counts(self, mock_is_tty):
        items = list(range(2500))
        with progress(items, desc="Rows", unit="rows") as bar:
            assert list(bar) == items
            assert bar.total == 2500
            assert bar._progress.tasks[0].completed == 2500

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_progress_postfix_and_description(self, mock_is_tty):
        with progress(desc="Counting", total=None, initial=5, leave=False) as bar:
            bar.set_postfix({"throughput": "10 rows/s"})
            bar.set_description("Done")
            task = bar._progress.tasks[0]
            assert task.fields["postfix"] == "throughput=10 rows/s"
            assert task.description == "Done"
            assert task.completed == 5

    def test_show_progress_false(self):
        assert isinstance(progress([1], show_progress=False), _NoProgress)


class TestUpdateProgress:
    """Test update_progress function."""

    def test_update_progress_with_pbar(self):
        """Test update_progress with a progress bar."""
        mock_pbar = MagicMock()
        update_progress(mock_pbar, n=5)
        mock_pbar.update.assert_called_once_with(5)

    def test_update_progress_with_none(self):
        """Test update_progress with None (no progress bar)."""
        update_progress(None, n=5)  # Should not raise

    def test_update_progress_with_exception(self):
        """Test update_progress when update raises exception."""
        mock_pbar = MagicMock()
        mock_pbar.update.side_effect = Exception("Test error")
        update_progress(mock_pbar, n=5)  # Should not raise


class TestSetProgressDescription:
    """Test set_progress_description function."""

    def test_set_progress_description_with_pbar(self):
        """Test set_progress_description with a progress bar."""
        mock_pbar = MagicMock()
        set_progress_description(mock_pbar, "New description")
        mock_pbar.set_description.assert_called_once_with("New description")

    def test_set_progress_description_with_none(self):
        """Test set_progress_description with None."""
        set_progress_description(None, "New description")  # Should not raise

    def test_set_progress_description_with_exception(self):
        """Test set_progress_description when set_description raises exception."""
        mock_pbar = MagicMock()
        mock_pbar.set_description.side_effect = Exception("Test error")
        set_progress_description(mock_pbar, "New description")  # Should not raise


class TestSetProgressPostfix:
    """Test set_progress_postfix function."""

    def test_set_progress_postfix_with_pbar(self):
        """Test set_progress_postfix with a progress bar."""
        mock_pbar = MagicMock()
        postfix = {"speed": "100 items/s"}
        set_progress_postfix(mock_pbar, postfix)
        mock_pbar.set_postfix.assert_called_once_with(postfix)

    def test_set_progress_postfix_with_none(self):
        """Test set_progress_postfix with None."""
        set_progress_postfix(None, {"speed": "100 items/s"})  # Should not raise

    def test_set_progress_postfix_with_exception(self):
        """Test set_progress_postfix when set_postfix raises exception."""
        mock_pbar = MagicMock()
        mock_pbar.set_postfix.side_effect = Exception("Test error")
        set_progress_postfix(mock_pbar, {"speed": "100 items/s"})  # Should not raise


class TestWrapIterable:
    """Test wrap_iterable function."""

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_wrap_iterable_enabled(self, mock_is_tty):
        """Test wrap_iterable when progress is enabled."""
        items = [1, 2, 3]
        result = list(wrap_iterable(iter(items), total=3, desc="Test"))
        assert result == [1, 2, 3]

    @patch("undatum.common.progress.is_tty", return_value=False)
    def test_wrap_iterable_not_tty(self, mock_is_tty):
        """Test wrap_iterable when not a TTY."""
        items = [1, 2, 3]
        result = list(wrap_iterable(iter(items), total=3, desc="Test"))
        assert result == [1, 2, 3]

    @patch("undatum.common.progress.is_tty", return_value=True)
    def test_wrap_iterable_disabled(self, mock_is_tty):
        assert list(wrap_iterable(iter([1, 2]), disable=True)) == [1, 2]
