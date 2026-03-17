"""
RetailIQ OAuth 2.0 Helpers
===========================
Authorization code flow, client credentials, and token management.
"""

import logging
import secrets
from datetime import datetime, timezone

import bcrypt

logger = logging.getLogger(__name__)


def get_redis_client():
    from ..utils.redis import get_redis_client as _get

    return _get()


def _get_redis():
    return get_redis_client()


def generate_auth_code(client_id: str, user_id: int, scopes: list) -> str:
    """
    Generate a one-time authorization code stored in Redis for 5 minutes.
    """
    code = secrets.token_urlsafe(32)
    try:
        redis = _get_redis()
        import json

        redis.setex(
            f"oauth_code:{code}",
            300,
            json.dumps({"client_id": client_id, "user_id": user_id, "scopes": scopes}),
        )
    except Exception as exc:
        logger.warning("Redis unavailable for auth code: %s", exc)
    return code


def verify_auth_code(code: str, client_id: str) -> dict | None:
    """
    Verify authorization code. Returns {user_id, scopes} or None.
    Consumes the code (single use).
    """
    try:
        import json

        redis = _get_redis()
        raw = redis.get(f"oauth_code:{code}")
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("client_id") != client_id:
            return None
        redis.delete(f"oauth_code:{code}")
        return {"user_id": data["user_id"], "scopes": data["scopes"]}
    except Exception as exc:
        logger.warning("Redis unavailable for code verification: %s", exc)
        return None


def verify_client_credentials(client_id: str | None, client_secret: str | None):
    """
    Verify OAuth client credentials. Returns DeveloperApplication or None.
    """
    if not client_id or not client_secret:
        return None
    try:
        from app import db
        from app.models import DeveloperApplication

        app_obj = db.session.query(DeveloperApplication).filter_by(client_id=client_id).first()
        if not app_obj:
            logger.debug("OAuth: Client ID %s not found", client_id)
            return None
        if app_obj.status != "ACTIVE":
            logger.debug("OAuth: Client ID %s is not ACTIVE (status: %s)", client_id, app_obj.status)
            return None

        if bcrypt.checkpw(client_secret.encode(), app_obj.client_secret_hash.encode()):
            return app_obj
        logger.debug("OAuth: Client ID %s secret mismatch", client_id)
        return None
    except Exception as exc:
        logger.error("Error verifying client credentials: %s", exc)
        return None


def generate_oauth_tokens(app_id: int, user_id: int | None = None, scopes: list | None = None) -> dict:
    """
    Generate OAuth access + refresh token pair for a developer application.
    """
    import json

    access_token = secrets.token_urlsafe(48)
    refresh_token = secrets.token_urlsafe(48)
    scopes = scopes or []

    data = {"app_id": app_id, "user_id": user_id, "scopes": scopes}
    try:
        redis = _get_redis()
        redis.setex(f"oauth_access:{access_token}", 3600, json.dumps(data))  # 1 hour
        redis.setex(f"oauth_refresh:{refresh_token}", 86400 * 30, json.dumps(data))  # 30 days
    except Exception as exc:
        logger.warning("Redis unavailable for OAuth tokens: %s", exc)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token,
        "scope": " ".join(scopes),
    }


def refresh_oauth_token(refresh_token: str, client_id: str, client_secret: str) -> dict | None:
    """Refresh OAuth tokens. Returns new token dict or None."""
    try:
        import json

        redis = _get_redis()
        raw = redis.get(f"oauth_refresh:{refresh_token}")
        if not raw:
            return None
        data = json.loads(raw)

        # Verify client still valid
        app_obj = verify_client_credentials(client_id, client_secret)
        if not app_obj or app_obj.id != data.get("app_id"):
            return None

        # Revoke old refresh token
        redis.delete(f"oauth_refresh:{refresh_token}")

        return generate_oauth_tokens(data["app_id"], data.get("user_id"), data.get("scopes", []))
    except Exception as exc:
        logger.warning("Redis unavailable for OAuth refresh: %s", exc)
        return None


def verify_oauth_token(token: str) -> dict | None:
    """Verify OAuth access token. Returns token data or None."""
    try:
        import json

        redis = _get_redis()
        raw = redis.get(f"oauth_access:{token}")
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis unavailable for OAuth verification: %s", exc)
        return None
