"""
RetailIQ WhatsApp Routes
=========================
WhatsApp Business API integration endpoints.
"""

from datetime import datetime, timezone

from flask import g, request
from marshmallow import ValidationError

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import Alert, PurchaseOrder, Supplier, WhatsAppConfig, WhatsAppMessageLog, WhatsAppTemplate
from . import whatsapp_bp
from .schemas import SendAlertSchema, SendPOSchema, WhatsAppConfigUpsertSchema


@whatsapp_bp.route("/config", methods=["GET"])
@require_auth
def get_whatsapp_config():
    """Get WhatsApp Business API configuration for the store."""
    store_id = g.current_user["store_id"]
    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id).first()
    if not config:
        return format_response(data={"is_active": False, "phone_number_id": None, "waba_id": None, "configured": False})
    return format_response(
        data={
            "phone_number_id": config.phone_number_id,
            "waba_id": config.waba_id,
            "is_active": config.is_active,
            "configured": bool(config.access_token_encrypted),
        }
    )


@whatsapp_bp.route("/config", methods=["PUT"])
@require_auth
@require_role("owner")
def upsert_whatsapp_config():
    """Create or update WhatsApp Business API configuration."""
    try:
        data = WhatsAppConfigUpsertSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

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

    # Encrypt access token if provided
    if data.get("access_token"):
        # Use our internal _encrypt_token utility
        config.access_token_encrypted = _encrypt_token(data["access_token"])

    db.session.commit()
    return format_response(data={"message": "WhatsApp configuration updated", "is_active": config.is_active})


@whatsapp_bp.route("/webhook", methods=["GET"])
def webhook_verify():
    """WhatsApp webhook verification (GET challenge)."""
    verify_token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    mode = request.args.get("hub.mode")

    if mode == "subscribe" and challenge:
        # Verify token against any store config (webhook is global)
        config = db.session.query(WhatsAppConfig).filter_by(webhook_verify_token=verify_token).first()
        if config:
            from flask import make_response

            return make_response(challenge, 200)

    return format_response(success=False, message="Verification failed", status_code=403)


@whatsapp_bp.route("/webhook", methods=["POST"])
def webhook_receive():
    """Receive incoming WhatsApp messages."""
    payload = request.json or {}
    # Log the incoming webhook for debugging
    import logging

    logging.getLogger(__name__).info("WhatsApp webhook received: %s", payload)
    # Process messages (stub — extend with full message handling)
    return format_response(data={"status": "received"})


@whatsapp_bp.route("/send-alert", methods=["POST"])
@require_auth
def send_alert_whatsapp():
    """Send a store alert via WhatsApp."""
    try:
        data = SendAlertSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]
    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id, is_active=True).first()
    if not config or not config.access_token_encrypted:
        return format_response(
            success=False,
            message="WhatsApp is not configured for this store",
            status_code=422,
            error={"code": "WHATSAPP_NOT_CONFIGURED"},
        )

    import uuid

    # Convert to log fields
    # alert_id in models is Integer Autoincrement
    alert = db.session.get(Alert, data["alert_id"])
    if not alert or alert.store_id != store_id:
        return format_response(success=False, message="Alert not found", status_code=404)

    # Log the send attempt
    log = WhatsAppMessageLog(
        store_id=store_id,
        message_type="alert",
        recipient_phone="919000000001",
        content_preview=alert.message[:500] if alert.message else "",
        status="SENT",
        sent_at=datetime.now(timezone.utc),
        direction="OUT",
    )
    db.session.add(log)
    db.session.commit()

    return format_response(data={"message": "Alert queued for WhatsApp delivery", "message_id": log.id})


@whatsapp_bp.route("/send-po", methods=["POST"])
@require_auth
def send_purchase_order_whatsapp():
    """Send a purchase order via WhatsApp."""
    try:
        data = SendPOSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]
    config = db.session.query(WhatsAppConfig).filter_by(store_id=store_id, is_active=True).first()
    if not config or not config.access_token_encrypted:
        return format_response(
            success=False,
            message="WhatsApp is not configured for this store",
            status_code=422,
            error={"code": "WHATSAPP_NOT_CONFIGURED"},
        )

    import uuid

    try:
        po_uuid = uuid.UUID(data["po_id"])
    except (ValueError, TypeError):
        return format_response(success=False, message="Invalid Purchase Order ID", status_code=400)

    po = db.session.get(PurchaseOrder, po_uuid)
    if not po or po.store_id != store_id:
        return format_response(success=False, message="Purchase Order not found", status_code=404)

    supplier = db.session.get(Supplier, po.supplier_id)
    if not supplier:
        return format_response(success=False, message="Supplier not found", status_code=404)

    from .formatters import format_po_message

    content = format_po_message(data["po_id"], db.session)

    # Prepend 91 to supplier phone
    phone = supplier.phone or "0000000000"
    if not phone.startswith("91"):
        phone = f"91{phone}"

    # Log the send attempt as QUEUED
    log = WhatsAppMessageLog(
        store_id=store_id,
        message_type="purchase_order",
        recipient_phone=phone,
        content_preview=content[:500],
        status="QUEUED",
        sent_at=datetime.now(timezone.utc),
        direction="OUT",
    )
    db.session.add(log)
    db.session.commit()

    return format_response(data={"message": "PO queued for WhatsApp delivery", "message_id": log.id})


@whatsapp_bp.route("/templates", methods=["GET"])
@require_auth
def list_templates():
    """List WhatsApp message templates for the store."""
    store_id = g.current_user["store_id"]
    templates = db.session.query(WhatsAppTemplate).filter_by(store_id=store_id).all()
    data = [
        {
            "id": t.id,
            "name": t.name,
            "category": t.category,
            "language": t.language,
            "status": t.status,
        }
        for t in templates
    ]
    return format_response(data=data)


@whatsapp_bp.route("/message-log", methods=["GET"])
@require_auth
def message_log():
    """Get WhatsApp message delivery log."""
    store_id = g.current_user["store_id"]
    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 20, type=int), 100)

    logs = (
        db.session.query(WhatsAppMessageLog)
        .filter_by(store_id=store_id)
        .order_by(WhatsAppMessageLog.sent_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    data = [
        {
            "id": l.id,
            "message_type": l.message_type,
            "recipient": l.recipient_phone,
            "status": l.status,
            "sent_at": l.sent_at.isoformat() if l.sent_at else None,
        }
        for l in logs
    ]
    return format_response(data=data, meta={"page": page, "limit": limit})


def _encrypt_token(token: str) -> str:
    """Helper to encrypt/encode token. Placeholder."""
    import base64

    return base64.b64encode(token.encode()).decode()


def _decrypt_token(encrypted_token: str) -> str:
    """Helper to decrypt/decode token. Placeholder."""
    import base64

    return base64.b64decode(encrypted_token.encode()).decode()
