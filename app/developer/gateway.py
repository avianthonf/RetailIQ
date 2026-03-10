import time
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from app import db
from app.auth.utils import get_redis_client
from app.models import APIUsageRecord, Developer, DeveloperApplication


def require_oauth(scopes=None):
    """
    Decorator to require a valid OAuth access token and specific scopes.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"error": "unauthorized", "message": "Missing or invalid Authorization header"}), 401

            token = auth_header.split(" ")[1]
            try:
                public_key = current_app.config["JWT_PUBLIC_KEY"]
                payload = jwt.decode(token, public_key, algorithms=["RS256"])
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "token_expired", "message": "Access token has expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "invalid_token", "message": "Invalid access token"}), 401

            # Verify token type
            if payload.get("type") != "access":
                return jsonify({"error": "invalid_token", "message": "Not an access token"}), 401

            # Check scopes
            token_scopes = payload.get("scopes", [])
            if scopes:
                for s in scopes:
                    if s not in token_scopes:
                        return jsonify({"error": "insufficient_scope", "message": f"Missing scope: {s}"}), 403

            # Attach app and user to g
            g.app_id = int(payload["app_id"])
            g.user_id = int(payload["sub"]) if payload["sub"].isdigit() else None
            g.scopes = token_scopes

            # Start timing for usage recording
            g._api_start_time = time.time()

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_api_key(f):
    """
    Decorator to require a valid Developer API Key.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "unauthorized", "message": "Missing X-API-Key header"}), 401

        # Verify API Key (in a real app, we should hash this)
        import hashlib

        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        developer = db.session.query(Developer).filter_by(api_key_hash=api_key_hash).first()
        if not developer:
            return jsonify({"error": "unauthorized", "message": "Invalid API Key"}), 401

        g.developer_id = developer.id
        g.user_id = developer.user_id

        return f(*args, **kwargs)

    return decorated_function


def record_usage(response):
    """
    After-request hook to record API usage.
    """
    if hasattr(g, "app_id") and hasattr(g, "_api_start_time"):
        latency = (time.time() - g._api_start_time) * 1000  # ms
        status_code = response.status_code
        is_error = status_code >= 400

        # In a real high-scale app, we would buffer these in Redis and sync to DB asynchronously.
        # For now, we'll increment in Redis and let a background task sync to APIUsageRecord.
        redis_client = get_redis_client()
        minute_bucket = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()

        key = f"usage:{g.app_id}:{request.path}:{request.method}:{minute_bucket}"
        pipe = redis_client.pipeline()
        pipe.hincrby(key, "request_count", 1)
        if is_error:
            pipe.hincrby(key, "error_count", 1)
        pipe.hincrby(key, "total_latency_ms", int(latency))
        # bytes_transferred could be estimated from response.data
        if response.data:
            pipe.hincrby(key, "bytes_transferred", len(response.data))

        pipe.expire(key, 3600 * 2)  # Keep in Redis for 2 hours
        pipe.execute()

    return response
