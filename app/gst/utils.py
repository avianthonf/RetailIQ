"""RetailIQ GST Utilities."""

import re


def validate_gstin(gstin: str) -> bool:
    """
    Validate Indian GSTIN format and checksum.
    Format: 2-digit state code + 10-char PAN + 1 entity number + Z + 1 checksum
    Example: 29ABCDE1234F1Z5
    """
    if not gstin or len(gstin) != 15:
        return False

    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    if not re.match(pattern, gstin.upper()):
        return False

    # Checksum validation using mod-36 Luhn-variant
    gstin = gstin.upper()
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    factor = 1
    total = 0
    for i, char in enumerate(gstin[:-1]):
        code_point = chars.index(char)
        addend = factor * code_point
        factor = 2 if factor == 1 else 1
        addend = (addend // 36) + (addend % 36)
        total += addend

    remainder = total % 36
    check_code_point = (36 - remainder) % 36
    expected_checksum = chars[check_code_point]
    return gstin[-1] == expected_checksum
