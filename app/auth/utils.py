import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis
from flask import current_app


from app.utils.responses import standard_json as format_response



def get_redis_client():
    redis_url = current_app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def generate_access_token(user_id, store_id, role):
    from app import db
    from app.models import StoreGroup

    private_key = current_app.config["JWT_PRIVATE_KEY"]
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "store_id": store_id,
        "role": role,
        "iat": now.timestamp(),
        "exp": (now + timedelta(minutes=60)).timestamp(),
    }

    # Inject Chain claims
    store_group = db.session.query(StoreGroup).filter_by(owner_user_id=user_id).first()
    if store_group:
        payload["chain_group_id"] = str(store_group.id)
        payload["chain_role"] = "CHAIN_OWNER"

    return jwt.encode(payload, private_key, algorithm="RS256")


def generate_refresh_token(user_id):
    redis_client = get_redis_client()
    token = str(uuid.uuid4())
    # 30 days expiry
    redis_client.setex(f"refresh_token:{token}", 30 * 24 * 3600, user_id)
    return token


def generate_otp(identifier, email=None):
    """Generate a 6-digit OTP, store in Redis, and (optionally) email it.

    Args:
        identifier: The Redis key suffix (mobile_number).
        email: If provided, sends the OTP to this email address.
    """
    from app.email import send_otp_email

    redis_client = get_redis_client()
    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    # 300s TTL
    redis_client.setex(f"otp:{identifier}", 300, otp)

    if email:
        send_otp_email(email, otp)
    else:
        print(f"[DEV] OTP for {identifier}: {otp}")

    return otp


def verify_otp(mobile_number, otp):
    redis_client = get_redis_client()
    key = f"otp:{mobile_number}"
    stored_otp = redis_client.get(key)
    if stored_otp and stored_otp == otp:
        redis_client.delete(key)
        return True
    return False


def generate_reset_token(user_id, email=None):
    """Generate a password-reset token, store in Redis, and (optionally) email it.

    Args:
        user_id: The user ID to associate with the reset token.
        email: If provided, sends the reset token to this email address.
    """
    from app.email import send_password_reset_email

    redis_client = get_redis_client()
    token = str(uuid.uuid4())
    # 10 mins TTL
    redis_client.setex(f"reset:{token}", 600, user_id)

    if email:
        send_password_reset_email(email, token)
    else:
        print(f"[DEV] Password Reset Token for user {user_id}: {token}")

    return token


def verify_reset_token(token):
    redis_client = get_redis_client()
    user_id = redis_client.get(f"reset:{token}")
    if not user_id:
        return None
    return user_id


def generate_team_invite(store_id):
    redis_client = get_redis_client()
    invite_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    # 24 hours TTL
    redis_client.setex(f"invite:{invite_code}", 24 * 3600, store_id)
    return invite_code
