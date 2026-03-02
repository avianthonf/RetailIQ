"""Input sanitization utilities for free-text fields."""

from typing import Optional


def sanitize_string(value: str | None, max_length: int = 256) -> str | None:
    """Strip whitespace and truncate to max_length.

    Returns None if value is None or empty after stripping.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_length]
