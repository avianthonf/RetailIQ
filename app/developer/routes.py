import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from flask import g, jsonify, request
from marshmallow import Schema, ValidationError, fields
from sqlalchemy import func

from .. import db, limiter
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import APIUsageRecord, Developer, DeveloperApplication, MarketplaceApp, WebhookEvent
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


class AppUpdateSchema(Schema):
    name = fields.Str()
    description = fields.Str()
    redirect_uris = fields.List(fields.Str())
    scopes = fields.List(fields.Str())
    status = fields.Str()


class WebhookCreateSchema(Schema):
    url = fields.Url(required=True)
    events = fields.List(fields.Str(), required=True)
    secret = fields.Str(load_default=None)
    name = fields.Str(load_default=None)
    app_id = fields.Str(load_default=None)
    client_id = fields.Str(load_default=None)


class WebhookUpdateSchema(Schema):
    url = fields.Url(load_default=None)
    events = fields.List(fields.Str(), load_default=None)
    secret = fields.Str(load_default=None)
    is_active = fields.Bool(load_default=None)


def _current_developer():
    user_id = g.current_user["user_id"]
    developer = db.session.query(Developer).filter_by(user_id=user_id).first()
    if developer:
        return developer

    from app.models import User

    user = db.session.get(User, user_id)
    if not user:
        return None

    developer = Developer(name=user.full_name or "Developer", email=user.email, user_id=user_id)
    db.session.add(developer)
    db.session.flush()
    return developer


def _issue_credentials():
    client_id = secrets.token_hex(16)
    client_secret = secrets.token_urlsafe(32)
    client_secret_hash = bcrypt.hashpw(client_secret.encode(), bcrypt.gensalt()).decode()
    return client_id, client_secret, client_secret_hash


def _normalize_events(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _serialize_app(app, client_secret=None):
    return {
        "id": app.id,
        "client_id": app.client_id,
        "client_secret": client_secret,
        "name": app.name,
        "description": app.description,
        "app_type": app.app_type,
        "redirect_uris": app.redirect_uris or [],
        "scopes": app.scopes or [],
        "status": app.status,
        "tier": app.tier,
        "rate_limit_rpm": app.rate_limit_rpm,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }


def _serialize_webhook(app):
    return {
        "id": str(app.id),
        "app_id": app.id,
        "client_id": app.client_id,
        "name": app.name,
        "url": app.webhook_url,
        "events": _normalize_events(app.redirect_uris),
        "secret": app.webhook_secret or "",
        "is_active": app.status == "ACTIVE",
        "last_triggered_at": None,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "created_by": "current_user",
    }


def _find_app_for_developer(developer_id, app_ref):
    query = db.session.query(DeveloperApplication).filter_by(developer_id=developer_id)

    app = None
    try:
        app = query.filter_by(id=int(app_ref)).first()
    except (TypeError, ValueError):
        app = None

    if app:
        return app

    return query.filter_by(client_id=app_ref).first()


# ── Routes ───────────────────────────────────────────────────────────────────


@developer_bp.route("/register", methods=["POST"])
def register_developer():
    """Register a new developer (optionally linked to a User)."""
    try:
        data = DeveloperRegisterSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": err.messages})

    if db.session.query(Developer).filter_by(email=data["email"]).first():
        return format_response(success=False, error={"code": "DUPLICATE_EMAIL", "message": "Email already registered"})

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
        status_code=201,
    )


@developer_bp.route("/apps", methods=["POST"])
@require_auth
def create_app():
    """Create a new developer application."""
    try:
        data = AppCreateSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": err.messages})

    # Find the developer linked to current user
    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    client_id, client_secret, client_secret_hash = _issue_credentials()

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
            **_serialize_app(new_app, client_secret=client_secret),
        },
        status_code=201,
    )


@developer_bp.route("/apps", methods=["GET"])
@require_auth
def list_apps():
    """List applications for the current developer."""
    developer = _current_developer()
    if not developer:
        return format_response(success=True, data=[])

    apps = db.session.query(DeveloperApplication).filter_by(developer_id=developer.id).all()
    return format_response(True, data=[_serialize_app(app) for app in apps])


@developer_bp.route("/apps/<app_ref>", methods=["PATCH", "PUT"])
@require_auth
def update_app(app_ref):
    try:
        data = AppUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": err.messages},
            status_code=400,
        )

    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Application not found"}, status_code=404
        )

    for key in ("name", "description", "redirect_uris", "scopes", "status"):
        if key in data:
            setattr(app, key, data[key])

    db.session.commit()
    return format_response(True, data=_serialize_app(app))


@developer_bp.route("/apps/<app_ref>", methods=["DELETE"])
@require_auth
def delete_app(app_ref):
    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Application not found"}, status_code=404
        )

    db.session.delete(app)
    db.session.commit()
    return format_response(True, data={"id": str(app_ref), "deleted": True})


@developer_bp.route("/apps/<app_ref>/regenerate-secret", methods=["POST"])
@require_auth
def regenerate_app_secret(app_ref):
    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Application not found"}, status_code=404
        )

    _, client_secret, client_secret_hash = _issue_credentials()
    app.client_secret_hash = client_secret_hash
    db.session.commit()
    return format_response(True, data={"client_secret": client_secret})


@developer_bp.route("/webhooks", methods=["GET"])
@require_auth
def list_webhooks():
    developer = _current_developer()
    if not developer:
        return format_response(True, data=[])

    apps = (
        db.session.query(DeveloperApplication)
        .filter(DeveloperApplication.developer_id == developer.id, DeveloperApplication.webhook_url.isnot(None))
        .order_by(DeveloperApplication.created_at.desc())
        .all()
    )
    return format_response(True, data=[_serialize_webhook(app) for app in apps])


@developer_bp.route("/webhooks", methods=["POST"])
@require_auth
def create_webhook():
    try:
        data = WebhookCreateSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": err.messages},
            status_code=400,
        )

    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = None
    for ref_key in ("app_id", "client_id"):
        if data.get(ref_key):
            app = _find_app_for_developer(developer.id, data[ref_key])
            break

    if not app:
        client_id, _, client_secret_hash = _issue_credentials()
        app = DeveloperApplication(
            developer_id=developer.id,
            name=data.get("name") or f"Webhook {datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            description="Webhook subscription",
            app_type="INTEGRATION",
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            redirect_uris=data["events"],
            scopes=[],
            rate_limit_rpm=60,
            status="ACTIVE",
        )
        db.session.add(app)

    app.webhook_url = data["url"]
    app.webhook_secret = data.get("secret")
    app.redirect_uris = data["events"]
    db.session.commit()

    return format_response(True, data=_serialize_webhook(app), status_code=201)


@developer_bp.route("/webhooks/<app_ref>", methods=["PATCH", "PUT"])
@require_auth
def update_webhook(app_ref):
    try:
        data = WebhookUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": err.messages},
            status_code=400,
        )

    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app or not app.webhook_url:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Webhook not found"}, status_code=404
        )

    if data.get("url") is not None:
        app.webhook_url = data["url"]
    if data.get("events") is not None:
        app.redirect_uris = data["events"]
    if data.get("secret") is not None:
        app.webhook_secret = data["secret"]
    if data.get("is_active") is not None:
        app.status = "ACTIVE" if data["is_active"] else "SUSPENDED"

    db.session.commit()
    return format_response(True, data=_serialize_webhook(app))


@developer_bp.route("/webhooks/<app_ref>", methods=["DELETE"])
@require_auth
def delete_webhook(app_ref):
    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app or not app.webhook_url:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Webhook not found"}, status_code=404
        )

    app.webhook_url = None
    app.webhook_secret = None
    app.redirect_uris = []
    db.session.commit()
    return format_response(True, data={"id": str(app_ref), "deleted": True})


@developer_bp.route("/webhooks/<app_ref>/test", methods=["POST"])
@require_auth
def test_webhook(app_ref):
    developer = _current_developer()
    if not developer:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Developer account not found"})

    app = _find_app_for_developer(developer.id, app_ref)
    if not app or not app.webhook_url:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Webhook not found"}, status_code=404
        )

    event = WebhookEvent(
        app_id=app.id,
        event_type="developer.webhook.test",
        payload={"message": "RetailIQ webhook connectivity test", "timestamp": datetime.now(timezone.utc).isoformat()},
        delivery_url=app.webhook_url,
        status="PENDING",
    )
    db.session.add(event)
    db.session.commit()

    from app.tasks.webhook_tasks import deliver_webhook

    deliver_webhook.delay(event.id)
    return format_response(
        True,
        data={"success": True, "message": "Webhook test queued", "event_id": event.id},
    )


@developer_bp.route("/usage", methods=["GET"])
@require_auth
def get_usage_stats():
    developer = _current_developer()
    if not developer:
        return format_response(
            True,
            data={
                "total_requests": 0,
                "total_errors": 0,
                "avg_response_time": 0,
                "top_endpoints": [],
                "daily_usage": [],
            },
        )

    app_ids = db.session.query(DeveloperApplication.id).filter_by(developer_id=developer.id).subquery()
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    query = db.session.query(APIUsageRecord).filter(APIUsageRecord.app_id.in_(db.session.query(app_ids.c.id)))
    if from_date:
        query = query.filter(APIUsageRecord.minute_bucket >= datetime.fromisoformat(from_date))
    if to_date:
        query = query.filter(APIUsageRecord.minute_bucket <= datetime.fromisoformat(to_date) + timedelta(days=1))

    rows = query.all()
    total_requests = sum(row.request_count or 0 for row in rows)
    total_errors = sum(row.error_count or 0 for row in rows)
    total_latency = sum(float(row.avg_latency_ms or 0) * (row.request_count or 0) for row in rows)
    avg_response_time = (total_latency / total_requests) if total_requests else 0

    endpoint_counts = {}
    daily_usage = {}
    for row in rows:
        endpoint_counts[row.endpoint] = endpoint_counts.get(row.endpoint, 0) + int(row.request_count or 0)
        day_key = row.minute_bucket.date().isoformat()
        bucket = daily_usage.setdefault(day_key, {"requests": 0, "errors": 0, "latency_total": 0.0})
        bucket["requests"] += int(row.request_count or 0)
        bucket["errors"] += int(row.error_count or 0)
        bucket["latency_total"] += float(row.avg_latency_ms or 0) * int(row.request_count or 0)

    return format_response(
        True,
        data={
            "total_requests": total_requests,
            "total_errors": total_errors,
            "avg_response_time": round(avg_response_time, 2),
            "top_endpoints": [
                {"path": path, "requests": count}
                for path, count in sorted(endpoint_counts.items(), key=lambda item: item[1], reverse=True)[:5]
            ],
            "daily_usage": [
                {
                    "date": date_key,
                    "requests": bucket["requests"],
                    "errors": bucket["errors"],
                    "avg_response_time": round(
                        bucket["latency_total"] / bucket["requests"],
                        2,
                    )
                    if bucket["requests"]
                    else 0,
                }
                for date_key, bucket in sorted(daily_usage.items())
            ],
        },
    )


@developer_bp.route("/rate-limits", methods=["GET"])
@require_auth
def get_rate_limits():
    developer = _current_developer()
    if not developer:
        return format_response(True, data=[])

    now = datetime.now(timezone.utc)
    minute_bucket = now.replace(second=0, microsecond=0)
    apps = db.session.query(DeveloperApplication).filter_by(developer_id=developer.id).all()

    data = []
    for app in apps:
        current_requests = (
            db.session.query(func.coalesce(func.sum(APIUsageRecord.request_count), 0))
            .filter_by(app_id=app.id, minute_bucket=minute_bucket)
            .scalar()
        )
        limit = app.rate_limit_rpm or 60
        data.append(
            {
                "endpoint": app.name,
                "client_id": app.client_id,
                "limit": limit,
                "remaining": max(limit - int(current_requests or 0), 0),
                "reset_at": (minute_bucket + timedelta(minutes=1)).isoformat(),
            }
        )

    return format_response(True, data=data)


@developer_bp.route("/logs", methods=["GET"])
@require_auth
def get_api_logs():
    developer = _current_developer()
    if not developer:
        return format_response(True, data={"logs": [], "total": 0})

    level = request.args.get("level")
    limit = min(request.args.get("limit", 50, type=int), 200)
    apps = (
        db.session.query(DeveloperApplication.id, DeveloperApplication.name).filter_by(developer_id=developer.id).all()
    )
    app_ids = [app.id for app in apps]
    app_names = {app.id: app.name for app in apps}

    logs = []
    usage_rows = (
        db.session.query(APIUsageRecord)
        .filter(APIUsageRecord.app_id.in_(app_ids), APIUsageRecord.error_count > 0)
        .order_by(APIUsageRecord.minute_bucket.desc())
        .limit(limit)
        .all()
    )
    for row in usage_rows:
        logs.append(
            {
                "timestamp": row.minute_bucket.isoformat(),
                "level": "error",
                "message": f"{app_names.get(row.app_id, 'App')} returned {row.error_count} errors on {row.endpoint}",
                "request_id": f"usage-{row.id}",
                "ip_address": "aggregated",
                "user_agent": row.method,
            }
        )

    webhook_rows = (
        db.session.query(WebhookEvent)
        .filter(WebhookEvent.app_id.in_(app_ids))
        .order_by(WebhookEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    for row in webhook_rows:
        log_level = "error" if row.status in {"FAILED", "DEAD_LETTERED"} else "info"
        logs.append(
            {
                "timestamp": row.created_at.isoformat(),
                "level": log_level,
                "message": f"Webhook {row.event_type} delivery is {row.status.lower()}",
                "request_id": f"webhook-{row.id}",
                "ip_address": row.delivery_url,
                "user_agent": "RetailIQ-Webhook/1.0",
            }
        )

    if level:
        logs = [log for log in logs if log["level"] == level]

    logs = sorted(logs, key=lambda item: item["timestamp"], reverse=True)[:limit]
    return format_response(True, data={"logs": logs, "total": len(logs)})


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
    )
