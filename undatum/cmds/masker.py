"""Data masking command module."""

import logging

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    get_iterable_options,
    iter_command_rows,
)
from ..common.errors import FileNotFoundError, PermissionError, ValidationError, find_similar_files
from ..common.masking import mask_value
from ..common.path_utils import validate_file_path
from ..common.s3_iterable import open_path as open_iterable
from ..common.writer import emit_records
from ..utils import get_option

logger = logging.getLogger(__name__)


class Masker:
    """Data masking handler for anonymizing sensitive fields."""

    def __init__(self):
        pass

    def mask(self, fromfile: str, tofile: str | None, options: dict | None = None):
        """Mask sensitive fields in a data file.

        Args:
            fromfile: Path to input file
            tofile: Path to output file (None for stdout)
            options: Dictionary of options including:
                - fields: Comma-separated list of fields to mask
                - method: Masking method ('redact', 'hash', 'randomize')
                - salt: Optional salt for hashing
                - format_in: Input format override
                - format_out: Output format override
        """
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

        # Parse fields to mask
        fields_str = get_option(options, "fields")
        if not fields_str:
            raise ValidationError(
                "--fields option is required. Specify fields to mask (e.g., --fields email,phone)",
                field="fields",
            )

        fields_to_mask = [f.strip() for f in fields_str.split(",") if f.strip()]
        if not fields_to_mask:
            raise ValidationError("No valid fields specified for masking", field="fields")

        # Get masking method
        method = get_option(options, "method") or "redact"
        if method not in ("redact", "hash", "randomize"):
            raise ValidationError(
                f"Invalid masking method: '{method}'. Must be one of: redact, hash, randomize",
                field="method",
                suggestions=["redact", "hash", "randomize"],
            )

        # Get optional salt for hashing
        salt = get_option(options, "salt")

        # Get iterable options
        iterableargs = get_iterable_options(options)

        format_out = get_option(options, "format_out")
        logger.info(f"Masking fields: {fields_to_mask} using method: {method}")

        it_in = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
        try:
            masked = (
                self._mask_record(record, fields_to_mask, method, salt)
                for record in iter_command_rows(it_in, options)
            )
            count = emit_records(masked, tofile, format_out=format_out)
            logger.info("Masked %d records", count)
        finally:
            it_in.close()

    def _mask_record(
        self, record: dict, fields_to_mask: list[str], method: str, salt: str | None = None
    ) -> dict:
        """Mask specified fields in a record.

        Args:
            record: Record dictionary
            fields_to_mask: List of field names to mask
            method: Masking method
            salt: Optional salt for hashing

        Returns:
            Record with masked fields
        """
        masked = dict(record)
        for field in fields_to_mask:
            if field in masked:
                masked[field] = mask_value(masked[field], method, field_name=field, salt=salt)
        return masked
