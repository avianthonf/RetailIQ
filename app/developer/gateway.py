"""
RetailIQ Developer Gateway
============================
OAuth scope enforcement and API usage recording for /api/v2.
"""

import logging
from functools import wraps

from flask import g, request

from ..utils.redis import get_redis_client

logger = logging.getLogger(__name__)


def get_redis():
    """Wrapper to safely import redis client at runtime."""
    from ..utils.redis import get_redis_client as _get

    return _get()


def require_oauth(scopes: list[str] | None = None):
    """
    Decorator: validates OAuth access token and verifies required scopes.
    Populates g.oauth_app and g.oauth_scopes.
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                from app.auth.utils import format_response

                return format_response(
                    success=False,
                    message="Bearer token required",
                    status_code=401,
                    error={"code": "MISSING_TOKEN"},
                )

            token = auth_header[7:]

            from app.auth.oauth import verify_oauth_token

            token_data = verify_oauth_token(token)

            if not token_data:
                from app.auth.utils import format_response

                return format_response(
                    success=False,
                    message="Invalid or expired OAuth token",
                    status_code=401,
                    error={"code": "INVALID_TOKEN"},
                )

            # Scope check
            if scopes:
                token_scopes = set(token_data.get("scopes", []))
                required = set(scopes)
                missing = required - token_scopes
                if missing:
                    from app.auth.utils import format_response

                    return format_response(
                        success=False,
                        message=f"Insufficient scopes. Required: {', '.join(missing)}",
                        status_code=403,
                        error={"code": "INSUFFICIENT_SCOPE", "required": list(missing)},
                    )

            g.oauth_app_id = token_data.get("app_id")
            g.oauth_scopes = token_data.get("scopes", [])
            g.current_user = {"user_id": token_data.get("user_id"), "store_id": None, "role": None}

            return f(*args, **kwargs)

        return decorated

    return decorator


def record_usage(response):
    """
    after_request hook: record API usage for the current OAuth app.
    Non-fatal — never raises.
    """
    try:
        app_id = getattr(g, "oauth_app_id", None)
        if not app_id:
            return response

        from datetime import datetime, timezone

        from app import db
        from app.models import APIUsageRecord

        now = datetime.now(timezone.utc)
        bucket = now.replace(second=0, microsecond=0)
        endpoint = request.endpoint or request.path
        method = request.method
        is_error = response.status_code >= 400

        record = (
            db.session.query(APIUsageRecord)
            .filter_by(app_id=app_id, endpoint=endpoint, method=method, minute_bucket=bucket)
            .first()
        )

        if record:
            record.request_count += 1
            if is_error:
                record.error_count += 1
        else:
            record = APIUsageRecord(
                app_id=app_id,
                endpoint=endpoint,
                method=method,
                minute_bucket=bucket,
                request_count=1,
                error_count=1 if is_error else 0,
            )
            db.session.add(record)

        db.session.commit()
    except Exception as exc:
        logger.debug("Usage recording failed (non-fatal): %s", exc)

    return response
