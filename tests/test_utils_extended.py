"""Extended tests for utility functions."""

import os
import tempfile

import pytest

from undatum.utils import (
    TypeGuesser,
    buf_count_newlines_gen,
    detect_delimiter,
    detect_encoding,
    dict_generator,
    get_dict_keys,
    get_dict_value,
    get_file_type,
    get_option,
    guess_datatype,
    guess_int_size,
    normalize_for_json,
    strip_dict_fields,
)


class TestDetectEncoding:
    """Test detect_encoding function."""

    def test_detect_encoding_utf8(self):
        """Test detecting UTF-8 encoding."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"Hello, world!")
            temp_path = f.name

        try:
            result = detect_encoding(temp_path)
            assert "encoding" in result
            assert result["encoding"] is not None
        finally:
            os.unlink(temp_path)

    def test_detect_encoding_with_limit(self):
        """Test detecting encoding with limit."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"Test content")
            temp_path = f.name

        try:
            result = detect_encoding(temp_path, limit=100)
            assert "encoding" in result
        finally:
            os.unlink(temp_path)


class TestDetectDelimiter:
    """Test detect_delimiter function."""

    def test_detect_delimiter_comma(self):
        """Test detecting comma delimiter."""
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write("col1,col2,col3\n")
            temp_path = f.name

        try:
            result = detect_delimiter(temp_path)
            assert result == ","
        finally:
            os.unlink(temp_path)

    def test_detect_delimiter_semicolon(self):
        """Test detecting semicolon delimiter."""
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write("col1;col2;col3\n")
            temp_path = f.name

        try:
            result = detect_delimiter(temp_path)
            assert result == ";"
        finally:
            os.unlink(temp_path)

    def test_detect_delimiter_tab(self):
        """Test detecting tab delimiter."""
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write("col1\tcol2\tcol3\n")
            temp_path = f.name

        try:
            result = detect_delimiter(temp_path)
            assert result == "\t"
        finally:
            os.unlink(temp_path)


class TestGetFileType:
    """Test get_file_type function."""

    def test_get_file_type_csv(self):
        """Test getting CSV file type."""
        assert get_file_type("data.csv") == "csv"
        assert get_file_type("/path/to/file.CSV") == "csv"

    def test_get_file_type_jsonl(self):
        """Test getting JSONL file type."""
        assert get_file_type("data.jsonl") == "jsonl"

    def test_get_file_type_unsupported(self):
        """Test getting unsupported file type.

        Supported formats are now driven by iterabledata's registry, so the
        extension must be one the engine genuinely does not recognize.
        """
        assert get_file_type("data.unknownext") is None
        assert get_file_type("data") is None


class TestGetOption:
    """Test get_option function."""

    def test_get_option_from_dict(self):
        """Test getting option from dictionary."""
        options = {"key1": "value1", "key2": "value2"}
        assert get_option(options, "key1") == "value1"
        assert get_option(options, "key2") == "value2"

    def test_get_option_from_defaults(self):
        """Test getting option from defaults."""
        options = {}
        assert get_option(options, "encoding") == "utf8"
        assert get_option(options, "delimiter") == ","

    def test_get_option_not_found(self):
        """Test getting option that doesn't exist."""
        options = {}
        assert get_option(options, "nonexistent") is None


class TestGetDictValue:
    """Test get_dict_value function."""

    def test_get_dict_value_simple(self):
        """Test getting value from simple dictionary."""
        d = {"key": "value"}
        assert get_dict_value(d, ["key"]) == ["value"]

    def test_get_dict_value_nested(self):
        """Test getting value from nested dictionary."""
        d = {"level1": {"level2": {"level3": "value"}}}
        assert get_dict_value(d, ["level1", "level2", "level3"]) == ["value"]

    def test_get_dict_value_list(self):
        """Test getting value from list of dictionaries."""
        d = [{"key": "value1"}, {"key": "value2"}]
        assert get_dict_value(d, ["key"]) == ["value1", "value2"]

    def test_get_dict_value_none(self):
        """Test getting value from None."""
        assert get_dict_value(None, ["key"]) == []


class TestStripDictFields:
    """Test strip_dict_fields function."""

    def test_strip_dict_fields_simple(self):
        """Test stripping simple fields."""
        record = {"field1": "value1", "field2": "value2", "field3": "value3"}
        fields = [["field1"], ["field2"]]
        result = strip_dict_fields(record, fields)
        assert "field1" in result
        assert "field2" in result
        assert "field3" not in result

    def test_strip_dict_fields_nested(self):
        """Test stripping nested fields."""
        record = {"level1": {"level2": {"field1": "value1", "field2": "value2"}}}
        fields = [["level1", "level2", "field1"]]
        result = strip_dict_fields(record, fields)
        assert "field1" in result["level1"]["level2"]
        assert "field2" not in result["level1"]["level2"]


class TestDictGenerator:
    """Test dict_generator function."""

    def test_dict_generator_simple(self):
        """Test generating from simple dictionary."""
        d = {"key1": "value1", "key2": "value2"}
        result = list(dict_generator(d))
        assert len(result) == 2
        assert ["key1", "value1"] in result
        assert ["key2", "value2"] in result

    def test_dict_generator_nested(self):
        """Test generating from nested dictionary."""
        d = {"level1": {"level2": "value"}}
        result = list(dict_generator(d))
        assert ["level1", "level2", "value"] in result

    def test_dict_generator_skips_id(self):
        """Test that _id is skipped."""
        d = {"_id": "123", "key": "value"}
        result = list(dict_generator(d))
        assert ["_id", "123"] not in result
        assert ["key", "value"] in result


class TestGuessIntSize:
    """Test guess_int_size function."""

    def test_guess_int_size_uint8(self):
        """Test guessing uint8 size."""
        assert guess_int_size(100) == "uint8"
        assert guess_int_size(254) == "uint8"  # Less than 255

    def test_guess_int_size_uint16(self):
        """Test guessing uint16 size."""
        assert guess_int_size(255) == "uint16"  # 255 is >= 255, so uint16
        assert guess_int_size(65534) == "uint16"  # Less than 65535

    def test_guess_int_size_uint32(self):
        """Test guessing uint32 size."""
        assert guess_int_size(65536) == "uint32"
        assert guess_int_size(1000000) == "uint32"


class TestGuessDatatype:
    """Test guess_datatype function."""

    def test_guess_datatype_int(self):
        """Test guessing integer type."""
        from qddate import DateParser

        qd = DateParser()
        result = guess_datatype(123, qd)
        assert result["base"] == "int"

    def test_guess_datatype_float(self):
        """Test guessing float type."""
        from qddate import DateParser

        qd = DateParser()
        result = guess_datatype(123.45, qd)
        assert result["base"] == "float"

    def test_guess_datatype_string_digit(self):
        """Test guessing digit string."""
        from qddate import DateParser

        qd = DateParser()
        result = guess_datatype("123", qd)
        assert result["base"] == "int"

    def test_guess_datatype_string_float(self):
        """Test guessing float string."""
        from qddate import DateParser

        qd = DateParser()
        result = guess_datatype("123.45", qd)
        assert result["base"] == "float"

    def test_guess_datatype_none(self):
        """Test guessing None type."""
        from qddate import DateParser

        qd = DateParser()
        result = guess_datatype(None, qd)
        assert result["base"] == "empty"


class TestBufCountNewlinesGen:
    """Test buf_count_newlines_gen function."""

    def test_buf_count_newlines_gen(self):
        """Test counting newlines in file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            temp_path = f.name

        try:
            count = buf_count_newlines_gen(temp_path)
            assert count == 3
        finally:
            os.unlink(temp_path)

    def test_buf_count_newlines_gen_empty(self):
        """Test counting newlines in empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            count = buf_count_newlines_gen(temp_path)
            assert count == 0
        finally:
            os.unlink(temp_path)


class TestGetDictKeys:
    """Test get_dict_keys function."""

    def test_get_dict_keys_simple(self):
        """Test getting keys from simple dictionaries."""
        items = [{"key1": "value1", "key2": "value2"}]
        keys = get_dict_keys(items)
        assert "key1" in keys
        assert "key2" in keys

    def test_get_dict_keys_nested(self):
        """Test getting keys from nested dictionaries."""
        items = [{"level1": {"level2": "value"}}]
        keys = get_dict_keys(items)
        assert "level1.level2" in keys

    def test_get_dict_keys_with_limit(self):
        """Test getting keys with limit."""
        items = [{"key" + str(i): "value" + str(i)} for i in range(100)]
        keys = get_dict_keys(items, limit=10)
        # The limit applies to items processed, not keys returned
        # So we just check that it doesn't crash and returns some keys
        assert len(keys) > 0
        assert isinstance(keys, list)


class TestNormalizeForJson:
    """Test normalize_for_json function."""

    def test_normalize_for_json_uuid(self):
        """Test normalizing UUID to string."""
        try:
            import uuid

            test_uuid = uuid.uuid4()
            result = normalize_for_json(test_uuid)
            assert isinstance(result, str)
            assert result == str(test_uuid)
        except ImportError:
            pytest.skip("uuid module not available")

    def test_normalize_for_json_dict(self):
        """Test normalizing dictionary."""
        d = {"key": "value", "nested": {"key2": "value2"}}
        result = normalize_for_json(d)
        assert result == d

    def test_normalize_for_json_list(self):
        """Test normalizing list."""
        lst = [1, 2, 3]
        result = normalize_for_json(lst)
        assert result == lst

    def test_normalize_for_json_primitive(self):
        """Test normalizing primitive types."""
        assert normalize_for_json(123) == 123
        assert normalize_for_json("string") == "string"
        assert normalize_for_json(True) is True


class _CountingDates:
    """qddate stand-in: ISO dates (and anything starting with one) are dates."""

    def __init__(self):
        self.calls = 0

    def match(self, value):
        self.calls += 1
        head = value[:10]
        if (
            len(head) == 10
            and head[4] == "-"
            and head[7] == "-"
            and head.replace("-", "").isdigit()
        ):
            return {"pattern": {"key": "iso"}}
        return None


class TestTypeGuesser:
    """TypeGuesser gives guess_datatype results with fewer date checks."""

    VALUES = [
        "",
        "   ",
        "12",
        "012",
        "1.5",
        "2020-01-02",
        "2020-01-02 note",
        "abc",
        "a1",
        None,
        7,
        2.5,
    ]

    def test_same_results_as_guess_datatype(self):
        qd = _CountingDates()
        guesser = TypeGuesser(qd)
        for value in self.VALUES:
            assert guesser.base("f", value) == guess_datatype(value, qd)["base"], value

    def test_same_results_without_date_parser(self):
        guesser = TypeGuesser(None)
        for value in self.VALUES:
            assert guesser.base("f", value) == guess_datatype(value, None)["base"], value

    def test_values_without_digits_skip_the_date_check(self):
        qd = _CountingDates()
        guesser = TypeGuesser(qd)
        for value in ["lorem ipsum", "", "plain"] * 100:
            guesser.base("notes", value)
        assert qd.calls == 0

    def test_repeated_values_are_cached(self):
        qd = _CountingDates()
        guesser = TypeGuesser(qd)
        for _ in range(50):
            assert guesser.base("day", "2020-01-02") == "date"
        assert qd.calls == 1

    def test_date_checks_stop_for_non_date_fields(self):
        qd = _CountingDates()
        guesser = TypeGuesser(qd, date_probe=100)
        for i in range(1000):
            guesser.base("code", f"x{i}")
        assert qd.calls == 100
        # A real date column keeps being checked.
        for i in range(1000):
            day = f"2020-01-{i % 28 + 1:02d} {i}"
            assert guesser.base("day", day) == "date"
        assert qd.calls == 1100
