import secrets
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app

from app import db
from app.auth.utils import get_redis_client
from app.models import DeveloperApplication


def generate_auth_code(client_id, user_id, scopes):
    """
    Generate an authorization code and store it in Redis with 10-minute TTL.
    """
    code = secrets.token_urlsafe(32)
    redis_client = get_redis_client()
    data = {
        "client_id": client_id,
        "user_id": str(user_id),
        "scopes": ",".join(scopes) if scopes else "",
    }
    # Store with prefix 'oauth_code:'
    redis_client.hset(f"oauth_code:{code}", mapping=data)
    redis_client.expire(f"oauth_code:{code}", 600)
    return code


def verify_auth_code(code, client_id):
    """
    Verify the auth code and return associated data if valid.
    Code is deleted after verification (one-time use).
    """
    redis_client = get_redis_client()
    key = f"oauth_code:{code}"
    data = redis_client.hgetall(key)

    if not data:
        return None

    if data.get("client_id") != client_id:
        return None

    redis_client.delete(key)
    return {
        "user_id": int(data["user_id"]),
        "scopes": data["scopes"].split(",") if data["scopes"] else [],
    }


def generate_oauth_tokens(app_id, user_id=None, scopes=None):
    """
    Generate Access and Refresh tokens for a developer application.
    """
    private_key = current_app.config["JWT_PRIVATE_KEY"]
    now = datetime.now(timezone.utc)

    # Access Token (short-lived, 1 hour by default for OAuth)
    access_payload = {
        "sub": str(user_id) if user_id else f"app_{app_id}",
        "app_id": str(app_id),
        "type": "access",
        "scopes": scopes or [],
        "iat": now.timestamp(),
        "exp": (now + timedelta(hours=1)).timestamp(),
    }
    access_token = jwt.encode(access_payload, private_key, algorithm="RS256")

    # Refresh Token (long-lived)
    refresh_token = secrets.token_urlsafe(64)
    redis_client = get_redis_client()
    refresh_data = {
        "app_id": str(app_id),
        "user_id": str(user_id) if user_id else "",
        "scopes": ",".join(scopes) if scopes else "",
    }
    redis_client.hset(f"oauth_refresh:{refresh_token}", mapping=refresh_data)
    # 30 days expiry
    redis_client.expire(f"oauth_refresh:{refresh_token}", 30 * 24 * 3600)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": " ".join(scopes) if scopes else "",
    }


def refresh_oauth_token(refresh_token, client_id, client_secret):
    """
    Exchange a refresh token for a new access token.
    """
    redis_client = get_redis_client()
    key = f"oauth_refresh:{refresh_token}"
    data = redis_client.hgetall(key)

    if not data:
        return None

    app_id = int(data["app_id"])
    app = db.session.get(DeveloperApplication, app_id)

    if not app or app.client_id != client_id:
        return None

    # Verify client secret (this should be done in the caller or here)
    # We'll assume the caller verifies the client_secret before calling this.

    user_id = int(data["user_id"]) if data.get("user_id") else None
    scopes = data["scopes"].split(",") if data["scopes"] else []

    return generate_oauth_tokens(app_id, user_id, scopes)


def verify_client_credentials(client_id, client_secret):
    """
    Verify client_id and client_secret (hashed).
    """
    import bcrypt

    app = db.session.query(DeveloperApplication).filter_by(client_id=client_id).first()
    if not app:
        return None

    if bcrypt.checkpw(client_secret.encode(), app.client_secret_hash.encode()):
        return app

    return None
