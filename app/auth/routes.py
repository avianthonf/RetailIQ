import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import bcrypt
from flask import request
from marshmallow import ValidationError

from .. import db, limiter
from ..models import Store, User
from ..utils.audit import audit_log
from ..utils.security import (
    generate_mfa_secret,
    get_mfa_provisioning_uri,
    verify_mfa_code,
)
from . import auth_bp
from .decorators import require_auth
from .schemas import ForgotPasswordSchema, LoginSchema, OTPSchema, RefreshSchema, RegisterSchema, ResetPasswordSchema
from .utils import (
    format_response,
    generate_access_token,
    generate_otp,
    generate_refresh_token,
    generate_reset_token,
    get_redis_client,
    get_user_chain_info,
    verify_otp,
    verify_reset_token,
)


@auth_bp.route("/register", methods=["POST"])
# @limiter.limit("5/hour")
def register():
    try:
        data = RegisterSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    existing_user = db.session.query(User).filter_by(mobile_number=data["mobile_number"]).first()
    if existing_user:
        return format_response(
            success=False,
            message="Mobile number already registered",
            status_code=422,
            error={"code": "DUPLICATE_MOBILE"},
        )

    hashed_password = bcrypt.hashpw(data["password"].encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

    role = data.get("role", "owner")

    new_user = User(
        mobile_number=data["mobile_number"],
        password_hash=hashed_password,
        full_name=data["full_name"],
        email=data.get("email"),
        role=role,
        is_active=False,
    )
    db.session.add(new_user)
    db.session.flush()  # Generate user_id

    if role == "owner":
        store_name = data.get("store_name", f"{data['full_name']}'s Store")
        new_store = Store(store_name=store_name, owner_user_id=new_user.user_id)
        db.session.add(new_store)
        db.session.flush()
        new_user.store_id = new_store.store_id

    db.session.commit()

    generate_otp(new_user.mobile_number, email=new_user.email)

    return format_response(data={"message": "OTP sent to your email."}, status_code=201)


@auth_bp.route("/verify-otp", methods=["POST"])
# @limiter.limit("5/minute")
def verify_otp_endpoint():
    try:
        data = OTPSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    if verify_otp(data["mobile_number"], data["otp"]):
        user = db.session.query(User).filter_by(mobile_number=data["mobile_number"]).first()
        if user:
            user.is_active = True
            db.session.commit()
            cg_id, cg_role = get_user_chain_info(user.user_id)
            access_token = generate_access_token(
                user.user_id, user.store_id, user.role, chain_group_id=cg_id, chain_role=cg_role
            )
            refresh_token = generate_refresh_token(user.user_id)
            return format_response(
                data={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "user_id": user.user_id,
                    "role": user.role,
                    "store_id": user.store_id,
                }
            )
        return format_response(
            success=False, message="User not found", status_code=404, error={"code": "USER_NOT_FOUND"}
        )

    return format_response(
        success=False, message="Invalid or expired OTP", status_code=422, error={"code": "INVALID_OTP"}
    )


@auth_bp.route("/resend-otp", methods=["POST"])
# @limiter.limit("5/minute")
def resend_otp():
    try:
        data = request.json or {}
        contact = data.get("contact") or data.get("mobile_number")
        purpose = data.get("purpose", "registration")

        if not contact:
            return format_response(
                success=False, message="Contact number is required", status_code=422, error={"code": "CONTACT_REQUIRED"}
            )

        user = db.session.query(User).filter_by(mobile_number=contact).first()
        if not user:
            return format_response(
                success=False, message="User not found", status_code=404, error={"code": "USER_NOT_FOUND"}
            )

        generate_otp(user.mobile_number, email=user.email)

        return format_response(
            data={"message": "OTP sent successfully", "contact": contact, "otp_ttl": 120, "resend_after": 45}
        )
    except Exception as e:
        return format_response(
            success=False, message="Failed to resend OTP", status_code=500, error={"code": "RESEND_FAILED"}
        )


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10/minute")
def login():
    try:
        data = LoginSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    user = db.session.query(User).filter_by(mobile_number=data["mobile_number"]).first()
    if not user or not user.password_hash:
        return format_response(
            success=False,
            message="Invalid mobile number or password",
            status_code=401,
            error={"code": "INVALID_CREDENTIALS"},
        )

    # Check account lock
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return format_response(
            success=False,
            message="Account temporarily locked due to too many failed attempts",
            status_code=423,
            error={"code": "ACCOUNT_LOCKED"},
        )

    if not bcrypt.checkpw(data["password"].encode("utf-8"), user.password_hash.encode("utf-8")):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            from datetime import timedelta as _td

            user.locked_until = datetime.now(timezone.utc) + _td(minutes=15)
        db.session.commit()
        audit_log("LOGIN", "USER", user.user_id, result="FAILURE", meta_data={"reason": "wrong_password"})
        return format_response(
            success=False,
            message="Invalid mobile number or password",
            status_code=401,
            error={"code": "INVALID_CREDENTIALS"},
        )

    if not user.is_active:
        audit_log("LOGIN", "USER", user.user_id, result="FAILURE", meta_data={"reason": "inactive_account"})
        return format_response(
            success=False, message="Account is not verified", status_code=403, error={"code": "INACTIVE_ACCOUNT"}
        )

    # MFA Check
    if user.mfa_enabled:
        mfa_code = data.get("mfa_code")
        if not mfa_code:
            return format_response(data={"mfa_required": True, "message": "MFA code required."})

        if not verify_mfa_code(user.mfa_secret, mfa_code):
            audit_log("LOGIN", "USER", user.user_id, result="FAILURE", meta_data={"reason": "invalid_mfa"})
            return format_response(
                success=False, message="Invalid MFA code", status_code=401, error={"code": "INVALID_MFA"}
            )

    cg_id, cg_role = get_user_chain_info(user.user_id)
    access_token = generate_access_token(
        user.user_id, user.store_id, user.role, chain_group_id=cg_id, chain_role=cg_role
    )
    refresh_token = generate_refresh_token(user.user_id)

    # Update login stats
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_login_attempts = 0
    db.session.commit()

    audit_log("LOGIN", "USER", user.user_id, result="SUCCESS")

    return format_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user.user_id,
            "role": user.role,
            "store_id": user.store_id,
        }
    )


@auth_bp.route("/mfa/setup", methods=["POST"])
@require_auth
def mfa_setup():
    from flask import g

    user_id = g.current_user["user_id"]
    user = db.session.query(User).filter_by(user_id=user_id).first()

    # Verify password before setup
    data = request.json or {}
    password = data.get("password")
    if not password or not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return format_response(
            success=False, message="Password verification failed", status_code=401, error={"code": "INVALID_PASSWORD"}
        )

    if user.mfa_enabled:
        return format_response(
            success=False, message="MFA is already enabled", status_code=422, error={"code": "MFA_ALREADY_ENABLED"}
        )

    secret = generate_mfa_secret()
    user.mfa_secret = secret
    db.session.commit()

    provisioning_uri = get_mfa_provisioning_uri(secret, user.email or user.mobile_number)

    return format_response(
        data={
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "message": "Verify the MFA code to complete setup.",
        }
    )


@auth_bp.route("/mfa/verify", methods=["POST"])
@require_auth
def mfa_verify():
    from flask import g

    user_id = g.current_user["user_id"]
    user = db.session.query(User).filter_by(user_id=user_id).first()

    data = request.json or {}
    code = data.get("mfa_code")

    if not code:
        return format_response(
            success=False, message="MFA code is required", status_code=422, error={"code": "MISSING_CODE"}
        )

    if verify_mfa_code(user.mfa_secret, code):
        user.mfa_enabled = True
        db.session.commit()
        audit_log("MFA_ENABLED", "USER", user.user_id, result="SUCCESS")
        return format_response(data={"message": "MFA enabled successfully"})

    return format_response(success=False, message="Invalid MFA code", status_code=422, error={"code": "INVALID_MFA"})


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    try:
        data = RefreshSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    try:
        redis_client = get_redis_client()
        user_id = redis_client.get(f"refresh_token:{data['refresh_token']}")
    except Exception as e:
        print(f"[DEV] Redis not available for refresh token: {e}")
        return format_response(
            success=False,
            message="Token refresh not available without Redis",
            status_code=503,
            error={"code": "REDIS_UNAVAILABLE"},
        )

    if not user_id:
        return format_response(
            success=False, message="Invalid or expired refresh token", status_code=401, error={"code": "INVALID_TOKEN"}
        )

    user = db.session.query(User).filter_by(user_id=int(user_id)).first()
    if not user or not user.is_active:
        return format_response(
            success=False, message="User inactive or not found", status_code=401, error={"code": "UNAUTHORIZED"}
        )

    # Rotate refresh token
    try:
        redis_client.delete(f"refresh_token:{data['refresh_token']}")
        new_refresh = generate_refresh_token(user.user_id)
    except Exception as e:
        print(f"[DEV] Could not rotate refresh token: {e}")
        new_refresh = generate_refresh_token(user.user_id)

    cg_id, cg_role = get_user_chain_info(user.user_id)
    new_access = generate_access_token(user.user_id, user.store_id, user.role, chain_group_id=cg_id, chain_role=cg_role)

    return format_response(data={"access_token": new_access, "refresh_token": new_refresh})


@auth_bp.route("/logout", methods=["DELETE"])
@require_auth
def logout():
    from flask import g

    user_id = g.current_user["user_id"]

    try:
        redis_client = get_redis_client()
    except Exception as e:
        print(f"[DEV] Redis not available for logout: {e}")
        return format_response(data={"message": "Logged out successfully"})

    # Optional payload with refresh_token to specify which session
    # but since user_id is the source of truth, scanning for tokens or deleting by pattern
    # Wait, with the `refresh_token:{token} = user_id` approach, we don't know tokens for a user.
    # We should delete the refresh token from payload if provided.
    req_data = request.json or {}
    rt = req_data.get("refresh_token")
    if rt:
        try:
            stored_user = redis_client.get(f"refresh_token:{rt}")
            if stored_user and int(stored_user) == user_id:
                redis_client.delete(f"refresh_token:{rt}")
        except Exception as e:
            print(f"[DEV] Could not delete refresh token during logout: {e}")

    return format_response(data={"message": "Logged out successfully"})


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    try:
        data = ForgotPasswordSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", error=err.messages, status_code=422)

    user = db.session.query(User).filter_by(mobile_number=data["mobile_number"]).first()
    if user:
        token = generate_reset_token(user.user_id, email=user.email)

    return format_response(data={"message": "Password reset token sent to your email."})


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    try:
        data = ResetPasswordSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    user_id = verify_reset_token(data["token"])
    if not user_id:
        return format_response(
            success=False, message="Invalid or expired reset token", status_code=422, error={"code": "INVALID_TOKEN"}
        )

    user = db.session.query(User).filter_by(user_id=int(user_id)).first()
    if not user:
        return format_response(
            success=False, message="User not found", status_code=404, error={"code": "USER_NOT_FOUND"}
        )

    hashed_password = bcrypt.hashpw(data["new_password"].encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")
    user.password_hash = hashed_password
    db.session.commit()

    return format_response(data={"message": "Password reset successfully."})
