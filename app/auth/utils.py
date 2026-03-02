import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis
from flask import current_app


def format_response(success=True, data=None, error=None, meta=None):
    """
    Standard Response Envelope
    { success: bool, data: obj|null, error: {code,message}|null, meta: pagination|null, timestamp: ISO8601 }
    """
    return {
        "success": success,
        "data": data,
        "error": error,
        "meta": meta,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def get_redis_client():
    redis_url = current_app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/1')
    return redis.Redis.from_url(redis_url, decode_responses=True)

def generate_access_token(user_id, store_id, role):
    from app import db
    from app.models import StoreGroup

    private_key = current_app.config['JWT_PRIVATE_KEY']
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': user_id,
        'store_id': store_id,
        'role': role,
        'iat': now.timestamp(),
        'exp': (now + timedelta(hours=2)).timestamp()
    }

    # Inject Chain claims
    store_group = db.session.query(StoreGroup).filter_by(owner_user_id=user_id).first()
    if store_group:
        payload['chain_group_id'] = str(store_group.id)
        payload['chain_role'] = 'CHAIN_OWNER'

    return jwt.encode(payload, private_key, algorithm='RS256')

def generate_refresh_token(user_id):
    redis_client = get_redis_client()
    token = str(uuid.uuid4())
    # 30 days expiry
    redis_client.setex(f"refresh_token:{token}", 30 * 24 * 3600, user_id)
    return token

def generate_otp(mobile_number):
    redis_client = get_redis_client()
    otp = ''.join(random.choices(string.digits, k=6))
    # 300s TTL
    redis_client.setex(f"otp:{mobile_number}", 300, otp)
    print(f"[DEV] OTP for {mobile_number}: {otp}")
    return otp

def verify_otp(mobile_number, otp):
    redis_client = get_redis_client()
    key = f"otp:{mobile_number}"
    stored_otp = redis_client.get(key)
    if stored_otp and stored_otp == otp:
        redis_client.delete(key)
        return True
    return False

def generate_reset_token(user_id):
    redis_client = get_redis_client()
    token = str(uuid.uuid4())
    # 10 mins TTL
    redis_client.setex(f"reset:{token}", 600, user_id)
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
    invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    # 24 hours TTL
    redis_client.setex(f"invite:{invite_code}", 24 * 3600, store_id)
    return invite_code

