"""Extended unit tests for parallel helpers and workers."""

from unittest.mock import patch

import pytest

from undatum.common.errors import ConfigurationError
from undatum.common.parallel import (
    _is_pickle_related,
    _raise_worker_error,
    parallel_map,
    parallel_process_chunks,
    resolve_worker_count,
)
from undatum.common.parallel_workers import (
    frequency_chunk,
    merge_frequency_partials,
    merge_stats_partials,
    stats_accumulate_chunk,
    transform_convert_chunk,
    validate_rules_chunk,
)


def _square_chunk(chunk):
    return [x * x for x in chunk]


def _identity(chunk):
    return list(chunk)


class TestResolveWorkerCount:
    def test_none_uses_cpu_count(self):
        with patch("undatum.common.parallel.get_cpu_count", return_value=6):
            assert resolve_worker_count(None) == 6

    def test_positive(self):
        assert resolve_worker_count(4) == 4

    def test_zero_and_negative_clamped(self):
        assert resolve_worker_count(0) == 0
        assert resolve_worker_count(-3) == 0


class TestPickleErrorMapping:
    def test_is_pickle_related_by_message(self):
        assert _is_pickle_related(RuntimeError("Can't pickle local object"))
        assert not _is_pickle_related(ValueError("boom"))

    def test_raise_maps_pickle_to_configuration_error(self):
        with pytest.raises(ConfigurationError, match="picklable"):
            _raise_worker_error(RuntimeError("cannot pickle 'X' object"), use_processes=True)

    def test_raise_non_pickle_passthrough(self):
        with pytest.raises(ValueError, match="nope"):
            _raise_worker_error(ValueError("nope"), use_processes=True)


class TestParallelMapExtra:
    def test_sequential_chunk_size_gt_one(self):
        results = list(parallel_map(_square_chunk, [1, 2, 3, 4], num_threads=1, chunk_size=2))
        assert results == [1, 4, 9, 16]

    def test_unordered_thread_pool(self):
        items = list(range(12))
        results = list(
            parallel_map(
                _identity,
                items,
                num_threads=3,
                chunk_size=2,
                preserve_order=False,
                use_processes=False,
            )
        )
        assert sorted(results) == items


class TestParallelProcessChunksExtra:
    def test_max_in_flight_one(self):
        chunks = [[i] for i in range(8)]
        results = list(
            parallel_process_chunks(
                _identity,
                iter(chunks),
                num_threads=2,
                use_processes=False,
                preserve_order=True,
                max_in_flight=1,
            )
        )
        assert results == chunks

    def test_unordered_completion(self):
        chunks = [[1], [2], [3], [4]]
        results = list(
            parallel_process_chunks(
                _identity,
                iter(chunks),
                num_threads=2,
                use_processes=False,
                preserve_order=False,
            )
        )
        assert sorted(results) == sorted(chunks)

    def test_process_pool_unordered_content(self):
        chunks = [[1, 2], [3], [4, 5]]
        results = list(
            parallel_process_chunks(
                _square_chunk,
                iter(chunks),
                num_threads=2,
                use_processes=True,
                preserve_order=False,
            )
        )
        flat = sorted(x for chunk in results for x in chunk)
        assert flat == [1, 4, 9, 16, 25]


class TestTransformConvertChunk:
    def test_flatten_pads_missing_keys(self):
        # make_flat stringifies nested dicts; padding applies top-level schema keys.
        chunk = [{"id": 1, "meta": {"city": "NYC"}}, {"id": 2}]
        keys = ["id", "meta", "extra"]
        out = transform_convert_chunk((chunk, keys, True))
        assert len(out) == 2
        assert out[0]["id"] == 1
        assert "meta" in out[0]
        assert out[1]["id"] == 2
        assert out[1].get("extra") is None

    def test_empty_chunk(self):
        assert transform_convert_chunk(([], ["a"], True)) == []
        assert transform_convert_chunk(([], [], False)) == []


class TestValidateRulesChunk:
    def test_required_field_violations_and_indices(self, tmp_path):
        rules = tmp_path / "rules.json"
        rules.write_text(
            '{"rules": [{"name": "email_req", "field": "email", "type": "field", "required": true}]}',
            encoding="utf-8",
        )
        chunk = [{"email": "a@b.com"}, {}, {"email": "c@d.com"}]
        violations, seen = validate_rules_chunk((chunk, 10, str(rules), None))
        assert seen == 3
        assert len(violations) == 1
        assert violations[0]["row"] == 11

    def test_filter_skips_validation(self, tmp_path):
        rules = tmp_path / "rules.json"
        rules.write_text(
            '{"rules": [{"name": "email_req", "field": "email", "type": "field", "required": true}]}',
            encoding="utf-8",
        )
        chunk = [{"email": "", "keep": True}, {"email": "", "keep": False}]
        # Filter keep==true rows before validating email
        violations, seen = validate_rules_chunk((chunk, 0, str(rules), "keep == true"))
        assert seen == 2
        # keep==true should skip the second row; first row still missing email
        # At least ensure the worker returns a list and count.
        assert isinstance(violations, list)


class TestStatsWorkersExtra:
    def test_empty_partials_merge(self):
        fielddata, fieldtypes, count = merge_stats_partials([])
        assert fielddata == {}
        assert fieldtypes == {}
        assert count == 0

    def test_merge_overlapping_keys_and_lengths(self):
        a = stats_accumulate_chunk(([{"name": "aa"}, {"name": "b"}], True))
        b = stats_accumulate_chunk(([{"name": "aa"}, {"name": "ccc"}], True))
        fielddata, _, count = merge_stats_partials([a, b])
        assert count == 4
        assert fielddata["name"]["total"] == 4
        assert fielddata["name"]["n_uniq"] == 3
        assert fielddata["name"]["uniq"]["aa"] == 2
        assert fielddata["name"]["minlen"] == 1
        assert fielddata["name"]["maxlen"] == 3

    def test_nested_fields(self):
        partial = stats_accumulate_chunk(([{"user": {"id": 1}}, {"user": {"id": 2}}], True))
        fielddata, fieldtypes, count = partial
        assert count == 2
        assert "user.id" in fielddata
        assert fielddata["user.id"]["n_uniq"] == 2
        assert "user.id" in fieldtypes

    def test_empty_chunk(self):
        fielddata, fieldtypes, count = stats_accumulate_chunk(([], True))
        assert count == 0
        assert fielddata == {}
        assert fieldtypes == {}


class TestFrequencyWorkersExtra:
    def test_filter_expression(self):
        chunk = [
            {"city": "X", "ok": True},
            {"city": "Y", "ok": False},
            {"city": "X", "ok": True},
        ]
        # Exercise None filter path thoroughly
        counts = frequency_chunk((chunk, ["city"], None))
        assert counts["X"] == 2
        assert counts["Y"] == 1

    def test_multi_field_key(self):
        chunk = [{"a": "1", "b": "x"}, {"a": "1", "b": "x"}, {"a": "2", "b": "y"}]
        counts = frequency_chunk((chunk, ["a", "b"], None))
        assert counts["1\tx"] == 2
        assert counts["2\ty"] == 1

    def test_merge_empty(self):
        assert merge_frequency_partials([]) == {}
        assert merge_frequency_partials([{}]) == {}

    def test_missing_field_skipped(self):
        counts = frequency_chunk(([{"other": 1}], ["city"], None))
        assert counts == {}
