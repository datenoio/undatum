"""Python engine uniq: distinct combinations in first-seen order, in linear time."""

from undatum.cmds.selector import get_iterable_fields_uniq


def test_distinct_combinations_in_first_seen_order():
    rows = [
        {"a": "x", "b": "1"},
        {"a": "y", "b": "1"},
        {"a": "x", "b": "1"},
        {"a": "x", "b": 2},
        {"a": "y", "b": "1"},
    ]
    assert get_iterable_fields_uniq(rows, ["a", "b"]) == [["x", "1"], ["y", "1"], ["x", "2"]]


def test_many_distinct_values():
    # A list membership test made this quadratic (200,000 values took 99 s).
    rows = [{"id": str(i % 150_000)} for i in range(200_000)]
    result = get_iterable_fields_uniq(rows, ["id"])
    assert len(result) == 150_000
    assert result[:2] == [["0"], ["1"]]
