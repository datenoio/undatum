"""Text processing module."""

# STAT_READY_DATA_FORMATS = ['jsonl', 'bson', 'csv']
from ..common.command_utils import ITERABLE_OPTIONS_KEYS, get_iterable_options  # noqa: F401
from ..common.s3_iterable import open_path as open_iterable
from ..utils import get_file_type, get_option


def get_keys(adict, prefix=None):
    """Extract all keys from nested dictionary."""
    keys = {}
    for k, v in adict.items():
        fullk = ".".join([prefix, k]) if prefix else k
        keys[fullk] = 1
        if isinstance(v, dict):
            for ak in get_keys(v, fullk):
                keys[ak] = 1
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for ak in get_keys(item, fullk):
                        keys[ak] = 1
        else:
            print(f"{fullk}\t{str(v)}")
    return keys


class TextProcessor:
    """Text processing handler."""

    def __init__(self):
        pass

    def flatten(self, filename, options):
        """Flatten the data: one field per line."""
        get_file_type(filename) if options["format_in"] is None else options["format_in"]
        iterableargs = get_iterable_options(options)
        iterable = open_iterable(filename, mode="r", iterableargs=iterableargs)
        try:
            get_option(options, "output")
            i = 0
            for rec in iterable:
                allkeys = {}
                i += 1
                for k in get_keys(rec):
                    v = allkeys.get(k, 0)
                    allkeys[k] = v + 1
                for k, v in allkeys.items():
                    print("\t".join([k, str(v)]))
        finally:
            iterable.close()
