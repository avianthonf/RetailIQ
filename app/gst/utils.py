"""
GSTIN validation utility.

Indian GSTIN structure (15 characters):
  [0-1]  State code (01-37)
  [2-11] PAN (10 chars: 5 alpha + 4 digits + 1 alpha)
  [12]   Entity number (1-9 or A-Z)
  [13]   'Z' (default)
  [14]   Checksum (modulo-36 based)
"""
import re

_GSTIN_RE = re.compile(r'^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$')

_CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _char_value(ch: str) -> int:
    return _CHARSET.index(ch)


def validate_gstin(gstin: str) -> bool:
    """Validate a 15-character Indian GSTIN with modulo-36 checksum."""
    if not gstin or len(gstin) != 15:
        return False

    gstin = gstin.upper()
    if not _GSTIN_RE.match(gstin):
        return False

    # State code validation (01-37)
    state_code = int(gstin[:2])
    if state_code < 1 or state_code > 37:
        return False

    # Modulo-36 checksum (Luhn-like, as used in Indian GSTIN spec)
    total = 0
    for i, ch in enumerate(gstin[:14]):
        val = _char_value(ch)
        if i % 2 != 0:
            val *= 2
        # Carry: sum of quotient and remainder when divided by 36
        total += val // 36 + val % 36

    remainder = total % 36
    check_val = (36 - remainder) % 36
    expected_char = _CHARSET[check_val]

    return gstin[14] == expected_char
