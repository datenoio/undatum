"""Integration tests for parallel validate, stats, and frequency."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import orjson
import pytest

from undatum.cmds.selector import Selector, get_iterable_fields_freq
from undatum.cmds.statistics import StatProcessor
from undatum.cmds.validator import Validator
from undatum.common.s3_iterable import open_path as open_iterable


@pytest.fixture
def people_csv(tmp_path: Path) -> Path:
    path = tmp_path / "people.csv"
    lines = ["name,age,city,email"]
    rows = [
        ("Alice", "30", "NYC", "alice@example.com"),
        ("Bob", "25", "LA", "bad-email"),
        ("Carol", "40", "SF", "carol@example.com"),
        ("Dan", "25", "NYC", ""),
        ("Eve", "30", "LA", "eve@example.com"),
        ("Frank", "35", "SF", "frank@example.com"),
        ("Grace", "25", "NYC", "grace@example.com"),
        ("Hank", "40", "LA", "not-an-email"),
    ]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def required_email_rules(tmp_path: Path) -> Path:
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "name": "email_required",
                        "field": "email",
                        "type": "field",
                        "required": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _run_validate_capture(path: Path, rules: Path, **opts) -> dict:
    """Run validate and capture violations without SystemExit on errors."""
    captured: dict = {}

    def _capture(violations, total_records, options):
        captured["violations"] = list(violations)
        captured["total_records"] = total_records

    options = {
        "rules": str(rules),
        "output_format": "json",
        "progress": False,
        "max_violations": 100,
        **opts,
    }
    with patch.object(Validator, "_generate_validation_report", side_effect=_capture):
        Validator().validate(str(path), options)
    return captured


class TestParallelValidate:
    def test_parallel_matches_sequential_violations(
        self, people_csv: Path, required_email_rules: Path
    ):
        seq = _run_validate_capture(people_csv, required_email_rules)
        par = _run_validate_capture(people_csv, required_email_rules, threads=2, batch_size=3)
        assert seq["total_records"] == par["total_records"] == 8
        seq_idxs = sorted(v["row"] for v in seq["violations"])
        par_idxs = sorted(v["row"] for v in par["violations"])
        assert seq_idxs == par_idxs
        assert len(seq_idxs) >= 1  # empty email on Dan

    def test_threads_one_behaves_like_sequential(
        self, people_csv: Path, required_email_rules: Path
    ):
        data = _run_validate_capture(people_csv, required_email_rules, threads=1)
        assert data["total_records"] == 8


class TestParallelStats:
    def _profile(self, path: Path, threads=None):
        processor = StatProcessor(nodates=True)
        options = {
            "engine": "iterable",
            "progress": False,
            "no_progress": True,
            "quiet": True,
            "batch_size": 3,
        }
        if threads is not None:
            options["threads"] = threads
        return processor.stats(str(path), options)

    def test_parallel_matches_sequential_counts(self, people_csv: Path):
        seq = self._profile(people_csv)
        par = self._profile(people_csv, threads=2)
        assert seq["count"] == par["count"] == 8
        assert seq["num_fields"] == par["num_fields"]
        seq_fields = {f["key"]: f["is_uniq"] for f in seq["fields"]}
        par_fields = {f["key"]: f["is_uniq"] for f in par["fields"]}
        assert seq_fields == par_fields
        for key in seq["debug"]["fielddata"]:
            assert (
                seq["debug"]["fielddata"][key]["total"] == par["debug"]["fielddata"][key]["total"]
            )
            assert (
                seq["debug"]["fielddata"][key]["n_uniq"] == par["debug"]["fielddata"][key]["n_uniq"]
            )

    def test_jsonl_parallel_stats(self, tmp_path: Path):
        path = tmp_path / "rows.jsonl"
        with path.open("wb") as fh:
            for i in range(20):
                fh.write(orjson.dumps({"id": i, "group": i % 3}) + b"\n")
        seq = self._profile(path)
        par = self._profile(path, threads=3)
        assert seq["count"] == par["count"] == 20


class TestParallelFrequency:
    def test_helper_parallel_matches_sequential(self, people_csv: Path):
        it = open_iterable(str(people_csv), mode="r", iterableargs={})
        try:
            seq = get_iterable_fields_freq(it, ["city"], dolog=False)
        finally:
            it.close()

        it = open_iterable(str(people_csv), mode="r", iterableargs={})
        try:
            par = get_iterable_fields_freq(it, ["city"], dolog=False, threads=2)
        finally:
            it.close()

        assert seq == par

    def test_selector_frequency_with_threads(self, people_csv: Path, tmp_path: Path):
        out_seq = tmp_path / "freq_seq.csv"
        out_par = tmp_path / "freq_par.csv"
        selector = Selector()
        selector.frequency(
            str(people_csv),
            {
                "fields": "city",
                "output": str(out_seq),
                "engine": "python",
                "progress": False,
            },
        )
        selector.frequency(
            str(people_csv),
            {
                "fields": "city",
                "output": str(out_par),
                "engine": "python",
                "threads": 2,
                "progress": False,
            },
        )
        assert out_par.read_text(encoding="utf-8") == out_seq.read_text(encoding="utf-8")
