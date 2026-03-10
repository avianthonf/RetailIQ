import secrets

import bcrypt
from flask import g, jsonify, request
from marshmallow import Schema, ValidationError, fields

from app import db, limiter
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.models import Developer, DeveloperApplication, MarketplaceApp

from . import developer_bp

# ── Schemas ──────────────────────────────────────────────────────────────────


class DeveloperRegisterSchema(Schema):
    name = fields.Str(required=True)
    email = fields.Email(required=True)
    organization = fields.Str()


class AppCreateSchema(Schema):
    name = fields.Str(required=True)
    description = fields.Str()
    app_type = fields.Str(required=True)  # WEB, MOBILE, BACKEND, INTEGRATION
    redirect_uris = fields.List(fields.Str())
    scopes = fields.List(fields.Str())


# ── Routes ───────────────────────────────────────────────────────────────────


@developer_bp.route("/register", methods=["POST"])
def register_developer():
    """Register a new developer (optionally linked to a User)."""
    try:
        data = DeveloperRegisterSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

    if db.session.query(Developer).filter_by(email=data["email"]).first():
        return format_response(False, error={"code": "DUPLICATE_EMAIL", "message": "Email already registered"}), 400

    new_dev = Developer(name=data["name"], email=data["email"], organization=data.get("organization"))
    db.session.add(new_dev)
    db.session.commit()

    return format_response(
        True,
        data={
            "id": new_dev.id,
            "name": new_dev.name,
            "email": new_dev.email,
            "message": "Developer registered successfully.",
        },
    ), 201


@developer_bp.route("/apps", methods=["POST"])
@require_auth
def create_app():
    """Create a new developer application."""
    try:
        data = AppCreateSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

    # Find the developer linked to current user
    user_id = g.current_user["user_id"]
    developer = db.session.query(Developer).filter_by(user_id=user_id).first()
    if not developer:
        # Auto-create developer record for the user if it doesn't exist
        from app.models import User

        user = db.session.get(User, user_id)
        developer = Developer(name=user.full_name or "Dev", email=user.email, user_id=user_id)
        db.session.add(developer)
        db.session.flush()

    client_id = secrets.token_hex(16)
    client_secret = secrets.token_urlsafe(32)
    client_secret_hash = bcrypt.hashpw(client_secret.encode(), bcrypt.gensalt()).decode()

    new_app = DeveloperApplication(
        developer_id=developer.id,
        name=data["name"],
        description=data.get("description"),
        app_type=data["app_type"],
        client_id=client_id,
        client_secret_hash=client_secret_hash,
        redirect_uris=data.get("redirect_uris", []),
        scopes=data.get("scopes", ["read:inventory"]),
        rate_limit_rpm=60,
        status="ACTIVE",
    )
    db.session.add(new_app)
    db.session.commit()

    return format_response(
        True,
        data={
            "id": new_app.id,
            "client_id": client_id,
            "client_secret": client_secret,  # Return once
            "name": new_app.name,
            "scopes": new_app.scopes,
        },
    ), 201


@developer_bp.route("/apps", methods=["GET"])
@require_auth
def list_apps():
    """List applications for the current developer."""
    user_id = g.current_user["user_id"]
    developer = db.session.query(Developer).filter_by(user_id=user_id).first()
    if not developer:
        return format_response(True, data=[]), 200

    apps = db.session.query(DeveloperApplication).filter_by(developer_id=developer.id).all()
    return format_response(
        True,
        data=[{"id": a.id, "name": a.name, "client_id": a.client_id, "status": a.status, "tier": a.tier} for a in apps],
    ), 200


@developer_bp.route("/marketplace", methods=["GET"])
def list_marketplace():
    """List apps in the marketplace."""
    apps = db.session.query(MarketplaceApp).filter_by(review_status="APPROVED").all()
    return format_response(
        True,
        data=[
            {
                "id": a.id,
                "name": a.name,
                "tagline": a.tagline,
                "category": a.category,
                "price": str(a.price) if a.price else "0",
                "install_count": a.install_count,
                "avg_rating": str(a.avg_rating) if a.avg_rating else "N/A",
            }
            for a in apps
        ],
    ), 200
