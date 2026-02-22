from flask import request
import bcrypt
from marshmallow import ValidationError
from . import auth_bp
from .schemas import (
    RegisterSchema, LoginSchema, OTPSchema, 
    RefreshSchema, ForgotPasswordSchema, ResetPasswordSchema
)
from .utils import (
    format_response, generate_otp, verify_otp,
    generate_access_token, generate_refresh_token,
    get_redis_client, generate_reset_token, verify_reset_token
)
from .decorators import require_auth
from .. import db, limiter
from ..models import User, Store

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = RegisterSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
    
    existing_user = db.session.query(User).filter_by(mobile_number=data['mobile_number']).first()
    if existing_user:
        return format_response(False, error={"code": "DUPLICATE_MOBILE", "message": "Mobile number already registered"}), 400
        
    hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')
    
    role = data.get('role', 'owner')
    
    new_user = User(
        mobile_number=data['mobile_number'],
        password_hash=hashed_password,
        full_name=data['full_name'],
        email=data.get('email'),
        role=role,
        is_active=False
    )
    db.session.add(new_user)
    db.session.flush() # Generate user_id
    
    if role == 'owner':
        store_name = data.get('store_name', f"{data['full_name']}'s Store")
        new_store = Store(
            store_name=store_name,
            owner_user_id=new_user.user_id
        )
        db.session.add(new_store)
        db.session.flush()
        new_user.store_id = new_store.store_id
        
    db.session.commit()
    
    generate_otp(new_user.mobile_number)
    
    return format_response(True, data={"message": "OTP sent successfully."}), 201

@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp_endpoint():
    try:
        data = OTPSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    if verify_otp(data['mobile_number'], data['otp']):
        user = db.session.query(User).filter_by(mobile_number=data['mobile_number']).first()
        if user:
            user.is_active = True
            db.session.commit()
            return format_response(True, data={"message": "Account verified successfully."}), 200
        return format_response(False, error={"code": "USER_NOT_FOUND", "message": "User not found."}), 404
        
    return format_response(False, error={"code": "INVALID_OTP", "message": "Invalid or expired OTP."}), 400

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per 15 minute", key_func=lambda: request.json.get('mobile_number', '') if request.json else '')
def login():
    try:
        data = LoginSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    user = db.session.query(User).filter_by(mobile_number=data['mobile_number']).first()
    if not user or not user.password_hash:
        return format_response(False, error={"code": "INVALID_CREDENTIALS", "message": "Invalid mobile number or password."}), 401
        
    if not bcrypt.checkpw(data['password'].encode('utf-8'), user.password_hash.encode('utf-8')):
        return format_response(False, error={"code": "INVALID_CREDENTIALS", "message": "Invalid mobile number or password."}), 401
        
    if not user.is_active:
        return format_response(False, error={"code": "INACTIVE_ACCOUNT", "message": "Account is not verified."}), 403
        
    access_token = generate_access_token(user.user_id, user.store_id, user.role)
    refresh_token = generate_refresh_token(user.user_id)
    
    return format_response(True, data={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.user_id,
        "role": user.role,
        "store_id": user.store_id
    }), 200

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    try:
        data = RefreshSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    redis_client = get_redis_client()
    user_id = redis_client.get(f"refresh_token:{data['refresh_token']}")
    
    if not user_id:
        return format_response(False, error={"code": "INVALID_TOKEN", "message": "Invalid or expired refresh token."}), 401
        
    user = db.session.query(User).filter_by(user_id=int(user_id)).first()
    if not user or not user.is_active:
        return format_response(False, error={"code": "UNAUTHORIZED", "message": "User inactive or not found."}), 401
        
    # Rotate refresh token
    redis_client.delete(f"refresh_token:{data['refresh_token']}")
    new_refresh = generate_refresh_token(user.user_id)
    new_access = generate_access_token(user.user_id, user.store_id, user.role)
    
    return format_response(True, data={
        "access_token": new_access,
        "refresh_token": new_refresh
    }), 200

@auth_bp.route('/logout', methods=['DELETE'])
@require_auth
def logout():
    from flask import g
    user_id = g.current_user['user_id']
    redis_client = get_redis_client()
    
    # Optional payload with refresh_token to specify which session
    # but since user_id is the source of truth, scanning for tokens or deleting by pattern
    # Wait, with the `refresh_token:{token} = user_id` approach, we don't know tokens for a user.
    # We should delete the refresh token from payload if provided.
    req_data = request.json or {}
    rt = req_data.get('refresh_token')
    if rt:
        stored_user = redis_client.get(f"refresh_token:{rt}")
        if stored_user and int(stored_user) == user_id:
            redis_client.delete(f"refresh_token:{rt}")
            
    return format_response(True, data={"message": "Logged out successfully"}), 200

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = ForgotPasswordSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    user = db.session.query(User).filter_by(mobile_number=data['mobile_number']).first()
    if user:
        generate_reset_token(user.user_id)
        
    return format_response(True, data={"message": "If registered, a reset link/token will be generated."}), 200

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = ResetPasswordSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    user_id = verify_reset_token(data['token'])
    if not user_id:
        return format_response(False, error={"code": "INVALID_TOKEN", "message": "Invalid or expired reset token."}), 400
        
    user = db.session.query(User).filter_by(user_id=int(user_id)).first()
    if not user:
        return format_response(False, error={"code": "USER_NOT_FOUND", "message": "User not found."}), 404
        
    hashed_password = bcrypt.hashpw(data['new_password'].encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')
    user.password_hash = hashed_password
    db.session.commit()
    
    return format_response(True, data={"message": "Password reset successfully."}), 200
