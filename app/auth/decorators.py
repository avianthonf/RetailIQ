"""
RetailIQ Auth Decorators
=========================
JWT authentication and role-based access control decorators.
"""

import logging
from functools import wraps

from flask import g, request

from .utils import decode_access_token, format_response

logger = logging.getLogger(__name__)


def require_auth(f):
    """
    Decorator: validates Bearer JWT token and populates g.current_user.
    g.current_user = {"user_id": int, "store_id": int|None, "role": str, ...}
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return format_response(
                success=False,
                message="Authentication required",
                status_code=401,
                error={"code": "MISSING_TOKEN", "message": "Bearer token required"},
            )

        token = auth_header[7:]
        payload = decode_access_token(token)
        if not payload:
            return format_response(
                success=False,
                message="Invalid or expired token",
                status_code=401,
                error={"code": "INVALID_TOKEN", "message": "Token is invalid or has expired"},
            )

        g.current_user = payload
        return f(*args, **kwargs)

    return decorated


def require_role(*roles):
    """
    Decorator: requires g.current_user["role"] to be in `roles`.
    Must be used after @require_auth.

    Usage:
        @require_role("owner")
        @require_role("owner", "manager")
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if not user:
                return format_response(
                    success=False,
                    message="Authentication required",
                    status_code=401,
                    error={"code": "UNAUTHORIZED"},
                )
            if user.get("role") not in roles:
                return format_response(
                    success=False,
                    message=f"Access restricted to: {', '.join(roles)}",
                    status_code=403,
                    error={"code": "FORBIDDEN", "message": f"Requires role: {', '.join(roles)}"},
                )
            return f(*args, **kwargs)

        return decorated

    return decorator


def optional_auth(f):
    """
    Decorator: tries to authenticate but doesn't block if no token.
    Sets g.current_user if valid token present, otherwise g.current_user = None.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_access_token(token)
            if payload:
                g.current_user = payload
        return f(*args, **kwargs)

    return decorated
