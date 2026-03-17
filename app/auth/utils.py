"""
RetailIQ Auth Utilities
========================
JWT token generation, OTP generation/verification, format_response helper.
"""

import logging
import random
import secrets
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

import jwt
from flask import current_app, jsonify, make_response

from .. import db
from ..utils.redis import get_redis_client

logger = logging.getLogger(__name__)


# ── JWT Tokens ────────────────────────────────────────────────────────────────


def format_response(success=True, data=None, message=None, error=None, status_code=None, meta=None):
    """
    Unified JSON response envelope.
    Returns a Flask Response object (not a tuple) so callers can either:
      return format_response(...)            ← Response with embedded status
      return format_response(...), 201       ← Flask overrides with 201
    """
    payload = {
        "success": success,
        "data": data,
        "error": error,
        "meta": meta,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if message:
        payload["message"] = message

    if status_code is None:
        status_code = 200 if success else 400

    return make_response(jsonify(payload), status_code)


def _config_seconds(value) -> int:
    """Normalize JWT expiry config values to integer seconds."""
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    return int(value)


# ── JWT Tokens ────────────────────────────────────────────────────────────────


def generate_access_token(
    user_id: int,
    store_id: int | None,
    role: str | None,
    chain_group_id: str | None = None,
    chain_role: str | None = None,
) -> str:
    """Generate a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    expires = _config_seconds(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"])
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "store_id": store_id,
        "role": role,
        "chain_group_id": chain_group_id,
        "chain_role": chain_role,
        "iat": now,
        "exp": now + timedelta(seconds=expires),
        "type": "access",
    }
    return jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config.get("JWT_ALGORITHM", "HS256"),
    )


def generate_refresh_token(user_id: int) -> str:
    """Generate a refresh token and store it in Redis with TTL."""
    token = secrets.token_urlsafe(48)
    try:
        redis = get_redis_client()
        expires = _config_seconds(current_app.config["JWT_REFRESH_TOKEN_EXPIRES"])
        redis.setex(f"refresh_token:{token}", expires, str(user_id))
    except Exception as exc:
        logger.warning("Redis unavailable; refresh token not persisted: %s", exc)
    return token


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token. Returns payload or None."""
    try:
        return jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=[current_app.config.get("JWT_ALGORITHM", "HS256")],
        )
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.debug("Invalid token: %s", exc)
        return None


# ── OTP ───────────────────────────────────────────────────────────────────────


def _otp_redis_key(mobile_number: str) -> str:
    return f"otp:{mobile_number}"


def generate_otp(mobile_number: str, email: str | None = None) -> str:
    """Generate a 6-digit OTP, store in Redis, and optionally email it."""
    otp = "".join(random.choices(string.digits, k=6))
    ttl = current_app.config.get("OTP_TTL_SECONDS", 120)

    try:
        redis = get_redis_client()
        redis.setex(_otp_redis_key(mobile_number), ttl, otp)
    except Exception as exc:
        logger.warning("Redis unavailable; OTP not stored: %s", exc)
        # In dev mode, log OTP to console so developers can still test
        logger.info("[DEV] OTP for %s: %s", mobile_number, otp)

    if email:
        from ..email import send_otp_email

        send_otp_email(email, otp)
    else:
        # Always log OTP in non-production environments for testing
        env = current_app.config.get("ENVIRONMENT", "development")
        if env != "production":
            logger.info("[DEV] OTP for %s (email: %s): %s", mobile_number, email, otp)

    return otp


def verify_otp(mobile_number: str, otp: str) -> bool:
    """Verify OTP against Redis store. Returns True if valid."""
    try:
        redis = get_redis_client()
        stored = redis.get(_otp_redis_key(mobile_number))
        if stored and stored == otp:
            redis.delete(_otp_redis_key(mobile_number))
            return True
        return False
    except Exception as exc:
        logger.warning("Redis unavailable for OTP verification: %s", exc)
        return False


# ── Password Reset Tokens ─────────────────────────────────────────────────────


def generate_reset_token(user_id: int, email: str | None = None) -> str:
    """Generate a password reset token stored in Redis for 15 minutes."""
    token = secrets.token_urlsafe(32)
    try:
        redis = get_redis_client()
        redis.setex(f"reset_token:{token}", 900, str(user_id))
    except Exception as exc:
        logger.warning("Redis unavailable; reset token not stored: %s", exc)

    if email:
        from ..email import send_password_reset_email

        send_password_reset_email(email, token)
    else:
        env = current_app.config.get("ENVIRONMENT", "development")
        if env != "production":
            logger.info("[DEV] Reset token for user_id=%s: %s", user_id, token)

    return token


def verify_reset_token(token: str) -> int | None:
    """Verify reset token; returns user_id or None."""
    try:
        redis = get_redis_client()
        uid = redis.get(f"reset_token:{token}")
        if uid:
            redis.delete(f"reset_token:{token}")
            return int(uid)
        return None
    except Exception as exc:
        logger.warning("Redis unavailable for reset token verification: %s", exc)
        return None


# ── Redis Client ──────────────────────────────────────────────────────────────

_redis_client = None


def get_redis_client():
    """Get (or create) a Redis client. Raises on failure."""
    global _redis_client
    if _redis_client is None:
        import redis as redis_lib

        url = current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis_lib.from_url(url, decode_responses=True)
    _redis_client.ping()  # Raises redis.ConnectionError if unavailable
    return _redis_client


def get_user_chain_info(user_id: int):
    """Retrieve chain_group_id and chain_role for a user if they own a group."""
    from ..models import StoreGroup

    group = db.session.query(StoreGroup).filter_by(owner_user_id=user_id).first()
    if group:
        return str(group.id), "CHAIN_OWNER"
    return None, None
