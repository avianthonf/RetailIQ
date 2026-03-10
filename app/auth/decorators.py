from functools import wraps

import jwt
from flask import current_app, g, request

from app import db
from app.models import RBACPermission

from .utils import format_response


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return format_response(
                False, error={"code": "UNAUTHORIZED", "message": "Missing or invalid token"}, meta=None
            ), 401

        token = auth_header.split(" ")[1]
        try:
            public_key = current_app.config["JWT_PUBLIC_KEY"]
            # Explicitly enforce RS256 and validate standard claims
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={
                    "require": ["exp", "iat", "user_id", "role", "store_id"],
                    "verify_iat": True,
                },
            )
            g.current_user = payload
        except jwt.ExpiredSignatureError:
            return format_response(
                False, error={"code": "TOKEN_EXPIRED", "message": "Token has expired"}, meta=None
            ), 401
        except jwt.InvalidTokenError as e:
            # Log the specific error for debugging but return generic message
            current_app.logger.warning(f"JWT Verification Failed: {e}")
            return format_response(False, error={"code": "INVALID_TOKEN", "message": "Invalid token"}, meta=None), 401

        return f(*args, **kwargs)

    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return format_response(
                    False, error={"code": "UNAUTHORIZED", "message": "User not authenticated"}, meta=None
                ), 401

            if g.current_user.get("role") not in roles:
                return format_response(
                    False,
                    error={"code": "FORBIDDEN", "message": f"Requires one of roles: {', '.join(roles)}"},
                    meta=None,
                ), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_permission(resource, action):
    """
    Decorator to enforce fine-grained RBAC permissions.
    Checks if the user's role has entry in rbac_permissions table.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(g, "current_user", None):
                return format_response(
                    False, error={"code": "UNAUTHORIZED", "message": "User not authenticated"}, meta=None
                ), 401

            role = g.current_user.get("role")
            if not role:
                return format_response(
                    False, error={"code": "FORBIDDEN", "message": "User role not found in token"}, meta=None
                ), 403

            # Check for specific permission in DB
            permission = db.session.query(RBACPermission).filter_by(role=role, resource=resource, action=action).first()

            # Owner usually has all permissions (bypass or seed)
            if not permission and role != "owner":
                return format_response(
                    False,
                    error={
                        "code": "FORBIDDEN",
                        "message": f"Requires '{action}' permission on '{resource}'",
                    },
                    meta=None,
                ), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator
