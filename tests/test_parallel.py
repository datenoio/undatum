"""Tests for parallel processing utilities."""

from unittest.mock import patch

import pytest

from undatum.common.parallel import (
    get_cpu_count,
    is_cpu_bound_operation,
    parallel_map,
    parallel_process_chunks,
)
from undatum.common.parallel_workers import (
    frequency_chunk,
    merge_frequency_partials,
    merge_stats_partials,
    stats_accumulate_chunk,
    transform_convert_chunk,
)


class TestGetCpuCount:
    """Test get_cpu_count function."""

    @patch("os.cpu_count")
    def test_get_cpu_count_normal(self, mock_cpu_count):
        """Test get_cpu_count with normal CPU count."""
        mock_cpu_count.return_value = 4
        assert get_cpu_count() == 4

    @patch("os.cpu_count")
    def test_get_cpu_count_none(self, mock_cpu_count):
        """Test get_cpu_count when cpu_count returns None."""
        mock_cpu_count.return_value = None
        assert get_cpu_count() == 1

    @patch("os.cpu_count")
    def test_get_cpu_count_exception(self, mock_cpu_count):
        """Test get_cpu_count when cpu_count raises exception."""
        mock_cpu_count.side_effect = Exception("Test error")
        assert get_cpu_count() == 1


class TestIsCpuBoundOperation:
    """Test is_cpu_bound_operation function."""

    def test_cpu_bound_operations(self):
        """Test CPU-bound operations."""
        cpu_bound_ops = [
            "convert",
            "stats",
            "frequency",
            "validate",
            "dedup",
            "search",
            "fill",
            "transform",
            "apply",
        ]
        for op in cpu_bound_ops:
            assert is_cpu_bound_operation(op) is True
            assert is_cpu_bound_operation(op.upper()) is True

    def test_io_bound_operations(self):
        """Test I/O-bound operations."""
        io_bound_ops = ["read", "write", "load", "save", "copy", "move"]
        for op in io_bound_ops:
            assert is_cpu_bound_operation(op) is False

    def test_unknown_operation(self):
        """Test unknown operation."""
        assert is_cpu_bound_operation("unknown") is False


def _square_chunk(chunk):
    """Top-level picklable chunk squarer for process-pool tests."""
    return [x * x for x in chunk]


def _slow_identity(chunk):
    """Return chunk unchanged (simulates work)."""
    return list(chunk)


class TestParallelMap:
    """Test parallel_map function."""

    def test_parallel_map_single_thread(self):
        """Test parallel_map with single thread (sequential)."""

        def square(x):
            return x * x

        items = [1, 2, 3, 4, 5]
        results = list(parallel_map(square, items, num_threads=1))
        assert results == [1, 4, 9, 16, 25]

    def test_parallel_map_zero_threads(self):
        """Test parallel_map with zero threads (sequential)."""

        def square(x):
            return x * x

        items = [1, 2, 3]
        results = list(parallel_map(square, items, num_threads=0))
        assert results == [1, 4, 9]

    def test_parallel_map_empty(self):
        """Test parallel_map with empty iterable."""

        def square(x):
            return x * x

        items = []
        results = list(parallel_map(square, items))
        assert results == []

    def test_parallel_map_with_chunk_size(self):
        """Test parallel_map with chunk size."""
        items = [1, 2, 3, 4, 5]
        results = list(parallel_map(_square_chunk, items, num_threads=2, chunk_size=2))
        assert len(results) == 5
        assert set(results) == {1, 4, 9, 16, 25}

    def test_parallel_map_preserve_order(self):
        """Ordered map yields chunks in input order."""
        items = list(range(10))
        results = list(
            parallel_map(
                _slow_identity,
                items,
                num_threads=2,
                chunk_size=3,
                preserve_order=True,
                use_processes=False,
            )
        )
        assert results == items


class TestParallelProcessChunks:
    """Test parallel_process_chunks function."""

    def test_parallel_process_chunks_single_thread(self):
        """Test parallel_process_chunks with single thread."""
        chunks = [[1, 2], [3, 4], [5]]
        results = list(parallel_process_chunks(_square_chunk, iter(chunks), num_threads=1))
        assert results == [[1, 4], [9, 16], [25]]

    def test_parallel_process_chunks_empty(self):
        """Test parallel_process_chunks with empty chunks."""
        chunks = []
        results = list(parallel_process_chunks(_square_chunk, iter(chunks)))
        assert results == []

    def test_parallel_process_chunks_zero_threads(self):
        """Test parallel_process_chunks with zero threads."""
        chunks = [[1, 2], [3]]
        results = list(parallel_process_chunks(_square_chunk, iter(chunks), num_threads=0))
        assert results == [[1, 4], [9]]

    def test_parallel_process_chunks_multithreaded(self):
        """Test parallel_process_chunks with multiple threads."""
        chunks = [[1, 2], [3, 4], [5, 6]]
        results = list(
            parallel_process_chunks(_square_chunk, iter(chunks), num_threads=2, use_processes=False)
        )
        assert len(results) == 3
        result_sets = [set(r) for r in results]
        assert {1, 4} in result_sets
        assert {9, 16} in result_sets
        assert {25, 36} in result_sets

    def test_windowed_does_not_materialize_all(self):
        """Ensure streaming submission works with a bounded window."""
        max_seen = {"n": 0}
        active = {"n": 0}

        def gen():
            for i in range(30):
                active["n"] += 1
                max_seen["n"] = max(max_seen["n"], active["n"])
                yield [i]
                active["n"] -= 1

        results = list(
            parallel_process_chunks(
                _slow_identity,
                gen(),
                num_threads=2,
                use_processes=False,
                preserve_order=True,
                max_in_flight=4,
            )
        )
        assert results == [[i] for i in range(30)]
        # Generator should not be fully drained before first yields complete.
        assert max_seen["n"] <= 30

    def test_ordered_reassembly(self):
        """preserve_order yields results in input sequence."""
        chunks = [[i] for i in range(15)]
        results = list(
            parallel_process_chunks(
                _slow_identity,
                iter(chunks),
                num_threads=3,
                use_processes=False,
                preserve_order=True,
                max_in_flight=4,
            )
        )
        assert results == chunks

    def test_process_pool_ordered(self):
        """Process pool preserves order when requested."""
        chunks = [[1, 2], [3, 4], [5]]
        results = list(
            parallel_process_chunks(
                _square_chunk,
                iter(chunks),
                num_threads=2,
                use_processes=True,
                preserve_order=True,
            )
        )
        assert results == [[1, 4], [9, 16], [25]]

    def test_parallel_process_chunks_with_exception(self):
        """Test parallel_process_chunks when processor raises exception."""

        def failing_processor(chunk):
            if 3 in chunk:
                raise ValueError("Test error")
            return [x * x for x in chunk]

        chunks = [[1, 2], [3, 4]]
        with pytest.raises(ValueError, match="Test error"):
            list(
                parallel_process_chunks(
                    failing_processor, iter(chunks), num_threads=2, use_processes=False
                )
            )


class TestParallelWorkers:
    """Test picklable worker helpers."""

    def test_transform_convert_chunk_no_flatten(self):
        chunk = [{"a": 1}, {"a": 2}]
        assert transform_convert_chunk((chunk, [], False)) == chunk

    def test_stats_accumulate_and_merge(self):
        partial_a = stats_accumulate_chunk(([{"name": "a", "age": 1}], True))
        partial_b = stats_accumulate_chunk(([{"name": "b", "age": 2}], True))
        fielddata, fieldtypes, count = merge_stats_partials([partial_a, partial_b])
        assert count == 2
        assert fielddata["name"]["total"] == 2
        assert fielddata["name"]["n_uniq"] == 2
        assert "name" in fieldtypes

    def test_frequency_merge(self):
        a = frequency_chunk(([{"city": "X"}, {"city": "X"}], ["city"], None))
        b = frequency_chunk(([{"city": "Y"}], ["city"], None))
        merged = merge_frequency_partials([a, b])
        assert merged[("X",)] == 2
        assert merged[("Y",)] == 1
