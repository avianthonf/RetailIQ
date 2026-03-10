import base64
import os

import bleach
import pyotp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app


def get_encryption_key():
    """Derives a key from the JWT_PRIVATE_KEY or a dedicated encryption secret."""
    secret = current_app.config.get("ENCRYPTION_SECRET") or current_app.config.get("JWT_PRIVATE_KEY")
    if not secret:
        # Fallback for development, should be configured in prod
        secret = "dev-secret-key-change-this-in-prod"

    salt = b"retail-iq-salt"  # In production, use a persistent salt from config
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return kdf.derive(secret.encode() if isinstance(secret, str) else secret)


def encrypt_pii(data: str) -> str:
    """Encrypts PII data using AES-GCM."""
    if not data:
        return data
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_pii(encrypted_data: str) -> str:
    """Decrypts PII data using AES-GCM."""
    if not encrypted_data:
        return encrypted_data
    try:
        key = get_encryption_key()
        aesgcm = AESGCM(key)
        raw_data = base64.b64decode(encrypted_data)
        nonce = raw_data[:12]
        ciphertext = raw_data[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        # If decryption fails, it might be unencrypted legacy data or wrong key
        return encrypted_data


def sanitize_html(text: str) -> str:
    """Sanitizes HTML to prevent XSS."""
    if not text:
        return text
    # Allow a minimal set of safe tags if needed, otherwise strip all
    return bleach.clean(text, tags=[], attributes={}, strip=True)


def generate_mfa_secret() -> str:
    """Generates a random secret for TOTP MFA."""
    return pyotp.random_base32()


def get_mfa_provisioning_uri(secret: str, email: str) -> str:
    """Returns the provisioning URI for Google Authenticator etc."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="RetailIQ")


def verify_mfa_code(secret: str, code: str) -> bool:
    """Verifies a TOTP code against the secret."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
