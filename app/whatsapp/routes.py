import base64
import contextlib
import hashlib
import hmac
import json
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from flask import current_app, g, jsonify, request
from marshmallow import ValidationError
from sqlalchemy import desc

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import Alert, PurchaseOrder, Store, Supplier, User, WhatsAppConfig, WhatsAppMessageLog, WhatsAppTemplate
from . import whatsapp_bp
from .client import send_template_message, send_text_message
from .formatters import format_po_message
from .schemas import SendAlertSchema, SendPOSchema, WhatsAppConfigUpsertSchema


def _get_fernet() -> Fernet:
    """Create a Fernet instance using the app SECRET_KEY hashed to 32 bytes."""
    secret_key = current_app.config.get("SECRET_KEY", "default-dev-secret")
    # Fernet requires a 32 url-safe base64-encoded byte key.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt_token(token: str) -> str:
    if not token:
        return None
    f = _get_fernet()
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def _decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return None
    f = _get_fernet()
    try:
        return f.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


# ── Config ─────────────────────────────────────────────────────────


@whatsapp_bp.route("/whatsapp/config", methods=["GET"])
@require_auth
@require_role("owner")
def get_config():
    store_id = g.current_user["store_id"]
    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id).first()
    if not config:
        return format_response(
            True,
            data={
                "phone_number_id": None,
                "is_active": False,
                "waba_id": None,
                "has_access_token": False,
                "webhook_verify_token": None,
            },
        )

    return format_response(
        True,
        data={
            "phone_number_id": config.phone_number_id,
            "waba_id": config.waba_id,
            "webhook_verify_token": config.webhook_verify_token,
            "is_active": config.is_active,
            "has_access_token": bool(config.access_token_encrypted),
        },
    )


@whatsapp_bp.route("/whatsapp/config", methods=["PUT"])
@require_auth
@require_role("owner")
def update_config():
    try:
        data = WhatsAppConfigUpsertSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}, status_code=422)

    store_id = g.current_user["store_id"]
    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id).first()

    if not config:
        config = WhatsAppConfig(store_id=store_id)
        db.session.add(config)

    if "phone_number_id" in data:
        config.phone_number_id = data["phone_number_id"]
    if "waba_id" in data:
        config.waba_id = data["waba_id"]
    if "webhook_verify_token" in data:
        config.webhook_verify_token = data["webhook_verify_token"]
    if "is_active" in data:
        config.is_active = data["is_active"]
    if "access_token" in data and data["access_token"]:
        config.access_token_encrypted = _encrypt_token(data["access_token"])

    db.session.commit()
    return format_response(
        True,
        data={
            "phone_number_id": config.phone_number_id,
            "waba_id": config.waba_id,
            "webhook_verify_token": config.webhook_verify_token,
            "is_active": config.is_active,
            "has_access_token": bool(config.access_token_encrypted),
        },
    )


# ── Webhook ────────────────────────────────────────────────────────


@whatsapp_bp.route("/whatsapp/webhook", methods=["GET"])
def webhook_verify():
    """
    Meta webhook verification.
    Requires matching `hub.verify_token` with at least one active store configuration.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token:
        # Check if the token matches any store's configured webhook token
        config = db.session.query(WhatsAppConfig).filter_by(webhook_verify_token=token, is_active=True).first()
        if config:
            return challenge, 200
        else:
            return "Forbidden", 403
    return "BadRequest", 400


@whatsapp_bp.route("/whatsapp/webhook", methods=["POST"])
def webhook_receive():
    """
    Meta webhook incoming statuses and messages.
    """
    data = request.json
    if not data or "object" not in data or data["object"] != "whatsapp_business_account":
        return jsonify({"status": "ignored"}), 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Handle status updates (delivered, read, failed)
            if "statuses" in value:
                for status_update in value["statuses"]:
                    wa_message_id = status_update.get("id")
                    status_text = status_update.get("status")
                    timestamp = status_update.get("timestamp")

                    if wa_message_id and status_text:
                        log_entry = db.session.query(WhatsAppMessageLog).filter_by(wa_message_id=wa_message_id).first()
                        if log_entry:
                            log_entry.status = status_text.upper()
                            if status_text in ("delivered", "read"):
                                with contextlib.suppress(Exception):
                                    log_entry.delivered_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)

                            errors = status_update.get("errors", [])
                            if errors:
                                log_entry.error_message = json.dumps(errors)

            # (We could also handle incoming messages here if required by future feature sets)
            # if 'messages' in value: ...

    db.session.commit()
    return jsonify({"status": "ok"}), 200


# ── Dispatching ────────────────────────────────────────────────────


@whatsapp_bp.route("/whatsapp/send-alert", methods=["POST"])
@require_auth
@require_role("owner")
def send_alert():
    try:
        data = SendAlertSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}, status_code=422)

    store_id = g.current_user["store_id"]
    alert_id = data["alert_id"]

    alert = db.session.query(Alert).filter_by(alert_id=alert_id, store_id=store_id).first()
    if not alert:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Alert not found"}, status_code=404)

    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id, is_active=True).first()
    if not config or not config.phone_number_id or not config.access_token_encrypted:
        return format_response(
            False,
            error={"code": "WA_NOT_CONFIGURED", "message": "WhatsApp API is not configured or active for this store"}, status_code=422
        )

    # Find owner phone
    owner = db.session.query(User).filter_by(store_id=store_id, role="owner", is_active=True).first()
    if not owner or not owner.mobile_number:
        return format_response(
            False, error={"code": "NO_RECIPIENT", "message": "Could not find owner phone number"}, status_code=422
        )

    access_token = _decrypt_token(config.access_token_encrypted)
    text = f"RetailIQ Alert ({alert.priority}):\n\n{alert.message}"

    # Send
    resp = send_text_message(config.phone_number_id, access_token, f"91{owner.mobile_number}", text)

    # Log
    log_entry = WhatsAppMessageLog(
        store_id=store_id,
        recipient_phone=f"91{owner.mobile_number}",
        direction="OUT",
        message_type="alert",
        content_preview=text[:200],
        status="SENT" if "messages" in resp else "FAILED",
        error_message=resp.get("error"),
        wa_message_id=resp.get("messages", [{}])[0].get("id") if "messages" in resp else None,
        sent_at=datetime.now(timezone.utc) if "messages" in resp else None,
    )
    db.session.add(log_entry)
    db.session.commit()

    if "error" in resp:
        return format_response(False, error={"code": "WA_API_ERROR", "message": resp["error"]}, status_code=502)

    return format_response(True, data={"message_id": log_entry.wa_message_id}, status_code=200)


@whatsapp_bp.route("/whatsapp/send-po", methods=["POST"])
@require_auth
@require_role("owner")
def send_po():
    try:
        data = SendPOSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}, status_code=422)

    store_id = g.current_user["store_id"]
    po_id_str = data["po_id"]
    import uuid

    try:
        po_uuid = uuid.UUID(po_id_str)
    except ValueError:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": "Invalid PO ID format"}, status_code=422)

    po = db.session.query(PurchaseOrder).filter_by(id=po_uuid, store_id=store_id).first()
    if not po:
        return format_response(False, error={"code": "NOT_FOUND", "message": "PO not found"}, status_code=404)

    supplier = db.session.query(Supplier).filter_by(id=po.supplier_id).first()
    if not supplier or not supplier.phone:
        return format_response(
            False, error={"code": "NO_RECIPIENT", "message": "Supplier phone number not available"}, status_code=422
        )

    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id, is_active=True).first()
    if not config or not config.phone_number_id or not config.access_token_encrypted:
        return format_response(False, error={"code": "WA_NOT_CONFIGURED", "message": "WhatsApp is not configured"}, status_code=422)

    text = format_po_message(po_id_str, db.session)
    if not text:
        return format_response(False, error={"code": "FORMAT_ERROR", "message": "Could not format PO"}), 500

    access_token = _decrypt_token(config.access_token_encrypted)
    # Supplier phones could already have country codes, but assume 10 digit Indian for demo
    phone = supplier.phone
    if len(phone) == 10:
        phone = f"91{phone}"

    resp = send_text_message(config.phone_number_id, access_token, phone, text)

    log_entry = WhatsAppMessageLog(
        store_id=store_id,
        recipient_phone=phone,
        direction="OUT",
        message_type="purchase_order",
        content_preview=text[:200],
        status="QUEUED" if "messages" in resp else "FAILED",
        error_message=resp.get("error"),
        wa_message_id=resp.get("messages", [{}])[0].get("id") if "messages" in resp else None,
        sent_at=datetime.now(timezone.utc) if "messages" in resp else None,
    )
    db.session.add(log_entry)
    db.session.commit()

    if "error" in resp:
        return format_response(False, error={"code": "WA_API_ERROR", "message": resp["error"]}, status_code=502)

    return format_response(True, data={"message_id": log_entry.wa_message_id}, status_code=200)


# ── Message Log ────────────────────────────────────────────────────


@whatsapp_bp.route("/whatsapp/message-log", methods=["GET"])
@require_auth
@require_role("owner")
def get_message_log():
    store_id = g.current_user["store_id"]
    direction = request.args.get("direction")
    status = request.args.get("status")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    query = db.session.query(WhatsAppMessageLog).filter_by(store_id=store_id)
    if direction:
        query = query.filter_by(direction=direction)
    if status:
        query = query.filter_by(status=status)

    query = query.order_by(desc(WhatsAppMessageLog.created_at))
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    data = [
        {
            "id": str(log.id),
            "recipient_phone": log.recipient_phone,
            "direction": log.direction,
            "message_type": log.message_type,
            "template_name": log.template_name,
            "content_preview": log.content_preview,
            "status": log.status,
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "error_message": log.error_message,
        }
        for log in pagination.items
    ]

    return format_response(
        True, data={"logs": data, "total": pagination.total, "pages": pagination.pages, "current_page": page}
    )
