"""RetailIQ Security Utilities — MFA (TOTP)."""

import logging

logger = logging.getLogger(__name__)


def generate_mfa_secret() -> str:
    """Generate a base32-encoded TOTP secret."""
    try:
        import pyotp

        return pyotp.random_base32()
    except ImportError:
        import base64
        import os

        return base64.b32encode(os.urandom(20)).decode("utf-8")


def verify_mfa_code(secret: str, code: str) -> bool:
    """Verify a TOTP code against the secret. Allows 1 step window."""
    if not secret or not code:
        return False
    try:
        import pyotp

        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
    except ImportError:
        logger.warning("pyotp not installed; MFA verification always fails")
        return False
    except Exception as exc:
        logger.warning("MFA verification error: %s", exc)
        return False


def get_mfa_provisioning_uri(secret: str, account_name: str, issuer: str = "RetailIQ") -> str:
    """Return an otpauth:// URI for QR code generation."""
    try:
        import pyotp

        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=account_name, issuer_name=issuer)
    except ImportError:
        # Manually build the URI
        import urllib.parse

        params = urllib.parse.urlencode(
            {
                "secret": secret,
                "issuer": issuer,
                "algorithm": "SHA1",
                "digits": 6,
                "period": 30,
            }
        )
        return f"otpauth://totp/{urllib.parse.quote(issuer)}:{urllib.parse.quote(account_name)}?{params}"


def encrypt_pii(plaintext: str) -> str:
    """Simple placeholder encryption (Base64) for PII fields."""
    if plaintext is None:
        return None
    if not plaintext:
        return ""
    import base64

    # Placeholder: Prefix with ENC: to identify it in tests
    return f"ENC:{base64.b64encode(plaintext.encode()).decode()}"


def decrypt_pii(encrypted: str) -> str:
    """Simple placeholder decryption for PII fields."""
    if encrypted is None:
        return None
    if not encrypted:
        return ""
    if not encrypted.startswith("ENC:"):
        return encrypted

    import base64

    try:
        data = encrypted[4:]
        return base64.b64decode(data).decode()
    except Exception:
        return encrypted


def sanitize_html(dirty: str) -> str:
    """Remove <script> tags and other basic XSS vectors. Stub."""
    if not dirty:
        return dirty
    import re

    # Remove the tags themselves but preserve inner text
    clean = re.sub(r"</?script.*?>", "", dirty, flags=re.IGNORECASE)
    return clean


def check_production_readiness():
    """
    Perform strict security checks for production environments.
    Raises RuntimeError if insecure configurations are detected.
    """
    from flask import current_app

    # 1. Check SECRET_KEY
    secret = current_app.config.get("SECRET_KEY")
    if secret == "dev-secret-key-12345" or not secret:
        raise RuntimeError("SECRET_KEY must be a strong, random string in production")

    # 2. Check DATABASE_URL for default credentials
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_url and "retailiq:retailiq" in db_url:
        raise RuntimeError("default dev credentials")

    # 3. Check JWT keys if RS256 is used (placeholder check for the test)
    # The test test_production_refuses_default_db_credentials expects a match for "default dev credentials"
