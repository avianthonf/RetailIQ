from functools import wraps

import jwt
from flask import current_app, g, request

from .utils import format_response


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return format_response(False, error={"code": "UNAUTHORIZED", "message": "Missing or invalid token"}, meta=None), 401

        token = auth_header.split(" ")[1]
        try:
            public_key = current_app.config['JWT_PUBLIC_KEY']
            payload = jwt.decode(token, public_key, algorithms=['RS256'])
            g.current_user = payload
        except jwt.ExpiredSignatureError:
            return format_response(False, error={"code": "TOKEN_EXPIRED", "message": "Token has expired"}, meta=None), 401
        except jwt.InvalidTokenError:
            return format_response(False, error={"code": "INVALID_TOKEN", "message": "Invalid token"}, meta=None), 401

        return f(*args, **kwargs)
    return decorated

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(g, 'current_user', None):
                return format_response(False, error={"code": "UNAUTHORIZED", "message": "User not authenticated"}, meta=None), 401

            if g.current_user.get('role') not in roles:
                return format_response(False, error={"code": "FORBIDDEN", "message": f"Requires one of roles: {', '.join(roles)}"}, meta=None), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator
