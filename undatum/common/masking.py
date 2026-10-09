"""Data masking utilities for PII protection."""

import hashlib
import random
import re
from typing import Any


def redact(value: Any, token: str = "***") -> str:
    """Redact a value by replacing it with a fixed token.

    Args:
        value: Value to redact
        token: Token to use for redaction (default: "***")

    Returns:
        Redacted token string
    """
    if value is None:
        return token
    return token


def hash_value(value: Any, salt: str | None = None) -> str:
    """Hash a value deterministically using SHA-256.

    Args:
        value: Value to hash
        salt: Optional salt for hashing (for additional security)

    Returns:
        Hexadecimal hash string (first 16 characters)
    """
    if value is None:
        return ""

    value_str = str(value)
    if salt:
        value_str = f"{salt}{value_str}"

    # Use SHA-256 and take first 16 characters for readability
    hash_obj = hashlib.sha256(value_str.encode("utf-8"))
    return hash_obj.hexdigest()[:16]


def randomize_string(value: Any, length: int | None = None) -> str:
    """Randomize a string value while preserving approximate length.

    Args:
        value: String value to randomize
        length: Optional fixed length (if None, uses original length)

    Returns:
        Random string of similar length
    """
    if value is None:
        return ""

    value_str = str(value)
    if length is None:
        length = len(value_str) if value_str else 8

    # Generate random alphanumeric string
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def randomize_email(value: Any) -> str:
    """Randomize an email address while preserving format.

    Args:
        value: Email address to randomize

    Returns:
        Random email address in format user@domain.com
    """
    if value is None:
        return ""

    value_str = str(value)
    if not is_email(value_str):
        return randomize_string(value_str)

    # Extract local and domain parts
    parts = value_str.split("@", 1)
    if len(parts) == 2:
        local, domain = parts
        # Randomize both parts
        random_local = randomize_string(local, length=min(len(local), 10))
        random_domain = randomize_string(
            domain.split(".")[0], length=min(len(domain.split(".")[0]), 8)
        )
        tld = domain.split(".")[-1] if "." in domain else "com"
        return f"{random_local}@{random_domain}.{tld}"

    return randomize_string(value_str)


def randomize_phone(value: Any) -> str:
    """Randomize a phone number while preserving format.

    Args:
        value: Phone number to randomize

    Returns:
        Random phone number in similar format
    """
    if value is None:
        return ""

    value_str = str(value)
    if not is_phone(value_str):
        return randomize_string(value_str)

    # Extract digits only
    digits = re.sub(r"\D", "", value_str)

    # Generate random phone number with same number of digits
    random_digits = "".join(str(random.randint(0, 9)) for _ in range(len(digits)))

    # Try to preserve format (e.g., (XXX) XXX-XXXX)
    if len(digits) == 10:
        return f"({random_digits[:3]}) {random_digits[3:6]}-{random_digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"+1 ({random_digits[1:4]}) {random_digits[4:7]}-{random_digits[7:]}"
    else:
        return random_digits


def randomize_number(value: Any, min_val: float | None = None, max_val: float | None = None) -> Any:
    """Randomize a numeric value within a range.

    Args:
        value: Numeric value to randomize
        min_val: Minimum value (if None, uses 0 or value * 0.5)
        max_val: Maximum value (if None, uses value * 2 or 100)

    Returns:
        Random number of same type (int or float)
    """
    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            num_val = float(value)
        else:
            num_val = float(str(value))
    except (ValueError, TypeError):
        return randomize_string(value)

    # Determine range
    if min_val is None:
        min_val = max(0, num_val * 0.5) if num_val > 0 else num_val * 2
    if max_val is None:
        max_val = num_val * 2 if num_val > 0 else num_val * 0.5

    # Generate random number
    random_num = random.uniform(min_val, max_val)

    # Preserve type
    if isinstance(value, int):
        return int(random_num)
    return random_num


def mask_value(
    value: Any, method: str, field_name: str | None = None, salt: str | None = None
) -> Any:
    """Mask a value using the specified method with type-aware handling.

    Args:
        value: Value to mask
        method: Masking method ('redact', 'hash', 'randomize')
        field_name: Optional field name for type detection
        salt: Optional salt for hashing

    Returns:
        Masked value
    """
    if method == "redact":
        return redact(value)
    elif method == "hash":
        return hash_value(value, salt=salt)
    elif method == "randomize":
        # Type-aware randomization
        if field_name:
            field_lower = field_name.lower()
            if "email" in field_lower or is_email(str(value)):
                return randomize_email(value)
            elif "phone" in field_lower or "tel" in field_lower or is_phone(str(value)):
                return randomize_phone(value)
            elif "age" in field_lower or "year" in field_lower:
                return randomize_number(value, min_val=18, max_val=100)

        # Try numeric randomization
        try:
            float(str(value))
            return randomize_number(value)
        except (ValueError, TypeError):
            pass

        # Default to string randomization
        return randomize_string(value)
    else:
        raise ValueError(f"Unknown masking method: {method}")


def is_email(value: str) -> bool:
    """Check if a value looks like an email address.

    Args:
        value: Value to check

    Returns:
        True if value appears to be an email address
    """
    if not value or not isinstance(value, str):
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, value))


def is_phone(value: str) -> bool:
    """Check if a value looks like a phone number.

    Args:
        value: Value to check

    Returns:
        True if value appears to be a phone number
    """
    if not value or not isinstance(value, str):
        return False
    # Remove common phone formatting characters
    digits = re.sub(r"\D", "", value)
    # Check if it has 10 or 11 digits (US phone numbers)
    return len(digits) in (10, 11) and digits.isdigit()


def is_ssn(value: str) -> bool:
    """Check if a value looks like a Social Security Number.

    Args:
        value: Value to check

    Returns:
        True if value appears to be an SSN
    """
    if not value or not isinstance(value, str):
        return False
    # Remove dashes and spaces
    digits = re.sub(r"\D", "", value)
    # SSN has 9 digits
    return len(digits) == 9 and digits.isdigit()
