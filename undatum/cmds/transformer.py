"""Data transformation module."""

import logging
import sys
from runpy import run_path

import orjson

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    get_iterable_options,
    iter_command_rows,
)

# from xmlr import xmliter
from ..common.errors import FileNotFoundError, PermissionError, ValidationError, find_similar_files
from ..common.path_utils import validate_file_path
from ..common.s3_iterable import open_path as open_iterable
from ..utils import dict_generator, get_option

logger = logging.getLogger(__name__)

DEFAULT_HEADERS_DETECT_LIMIT = 1000


class Transformer:
    """Data transformation handler."""

    def __init__(self):
        pass

    def script(self, fromfile, options=None):
        """Run a script against every record of the file."""
        if options is None:
            options = {}

        # Validate input file exists and is readable
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e

        script_path = options.get("script")
        plugin_name = options.get("plugin")
        if not script_path and not plugin_name:
            raise ValidationError("Script file path or --plugin is required", field="script")

        if plugin_name:
            from ..cli.plugins_cli import plugin_manager

            transform = plugin_manager.get_registry().find_transform(plugin_name)
            if transform is None:
                raise ValidationError(
                    f"Transform plugin '{plugin_name}' is not registered",
                    field="plugin",
                )
            __process_func = transform.transform
        else:
            try:
                validate_file_path(script_path, check_read=True)
            except FileNotFoundError as e:
                suggestions = find_similar_files(script_path)
                raise FileNotFoundError(script_path, suggestions) from e
            except PermissionError as e:
                raise PermissionError(script_path, operation="read") from e

            try:
                script = run_path(script_path)
            except Exception as e:
                raise ValidationError(f"Failed to load script: {e}", field="script") from e

            if "process" not in script:
                raise ValidationError("Script must define a 'process' function", field="script")

            __process_func = script["process"]

        iterableargs = get_iterable_options(options)

        limit = DEFAULT_HEADERS_DETECT_LIMIT

        # First pass: extract schema
        keys_set = set()  # Use set for O(1) lookup instead of O(n) list operations
        read_iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
        try:
            n = 0
            for item in iter_command_rows(read_iterable, options):
                if limit and n > limit:
                    break
                item = __process_func(item)
                n += 1
                dk = dict_generator(item)
                for i in dk:
                    k = ".".join(i[:-1])
                    keys_set.add(k)
        finally:
            read_iterable.close()
        keys = list(keys_set)  # Convert to list for backward compatibility

        # Second pass: process and write
        write_to_iterable = False
        to_file = get_option(options, "output")
        if to_file:
            write_to_iterable = True
            write_iterable = open_iterable(to_file, mode="w", iterableargs={"keys": keys})
        else:
            write_iterable = None

        try:
            read_iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
            try:
                # Try to use reset() if available
                if hasattr(read_iterable, "reset"):
                    read_iterable.reset()

                n = 0
                batch = []
                for r in iter_command_rows(read_iterable, options):
                    n += 1
                    if n % 10000 == 0:
                        logger.info(f"apply script: processing {n} records of {fromfile}")
                        if write_to_iterable and len(batch) > 0:
                            if hasattr(write_iterable, "write_bulk"):
                                write_iterable.write_bulk(batch)
                            else:
                                for item in batch:
                                    write_iterable.write(item)
                            batch = []
                    item = __process_func(r)
                    if write_to_iterable:
                        batch.append(item)
                    else:
                        sys.stdout.write(
                            orjson.dumps(item, option=orjson.OPT_APPEND_NEWLINE).decode("utf8")
                        )

                # Flush remaining batch
                if write_to_iterable and len(batch) > 0:
                    if hasattr(write_iterable, "write_bulk"):
                        write_iterable.write_bulk(batch)
                    else:
                        for item in batch:
                            write_iterable.write(item)

                logger.debug(f"apply script: {n} records processed")
            finally:
                read_iterable.close()
        finally:
            if write_iterable:
                write_iterable.close()
