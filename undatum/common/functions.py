"""Common utility functions for dictionary operations.

This module provides helper functions for accessing nested dictionary
values using dot-notation keys.
"""

from typing import Any


def get_dict_value(adict: Any, key: str, prefix: list[str] | None = None) -> Any:
    """Get value from dictionary using dot-notation key.

    Args:
        adict: Dictionary to search.
        key: Dot-separated key path (e.g., 'field.subfield').
        prefix: Pre-split key parts (used internally for recursion).

    Returns:
        Value at the specified key path.

    Raises:
        KeyError: If any key in the path doesn't exist.
    """
    if prefix is None:
        prefix = key.split(".")
    if len(prefix) == 1:
        return adict[prefix[0]]
    return get_dict_value(adict[prefix[0]], key, prefix=prefix[1:])


def get_dict_value_deep(
    adict: Any,
    key: str,
    prefix: list[str] | None = None,
    as_array: bool = False,
    splitter: str = ".",
) -> Any:
    """Get value from hierarchical dictionaries with deep traversal.

    Supports nested dictionaries and lists, with optional array collection
    of values from multiple sources.

    Args:
        adict: Dictionary or list to search.
        key: Dot-separated key path (e.g., 'field.subfield').
        prefix: Pre-split key parts (used internally for recursion).
        as_array: If True, collect all matching values into an array.
        splitter: Character used to split key path (default: '.').

    Returns:
        Value at the specified key path, or list of values if as_array=True.
        Returns None if key path not found.
    """
    if prefix is None:
        prefix = key.split(splitter)
    if len(prefix) == 1:
        if isinstance(adict, dict):
            if prefix[0] not in adict:
                return None
            if as_array:
                return [adict[prefix[0]]]
            return adict[prefix[0]]
        if isinstance(adict, list):
            if as_array:
                result = []
                for v in adict:
                    if prefix[0] in v:
                        result.append(v[prefix[0]])
                return result
            if len(adict) > 0 and prefix[0] in adict[0]:
                return adict[0][prefix[0]]
        return None
    if isinstance(adict, dict):
        if prefix[0] in adict:
            return get_dict_value_deep(adict[prefix[0]], key, prefix=prefix[1:], as_array=as_array)
    elif isinstance(adict, list):
        if as_array:
            result = []
            for v in adict:
                res = get_dict_value_deep(v[prefix[0]], key, prefix=prefix[1:], as_array=as_array)
                if res:
                    result.extend(res)
            return result
        return get_dict_value_deep(adict[0][prefix[0]], key, prefix=prefix[1:], as_array=as_array)
    return None
