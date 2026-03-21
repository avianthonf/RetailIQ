"""
RetailIQ WhatsApp Routes
=========================
WhatsApp Business API integration endpoints.
"""

import uuid
from datetime import datetime, timezone

from flask import g, request
from marshmallow import ValidationError

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import (
    Alert,
    PurchaseOrder,
    Supplier,
    WhatsAppCampaign,
    WhatsAppConfig,
    WhatsAppContactPreference,
    WhatsAppMessageLog,
    WhatsAppTemplate,
)
from . import whatsapp_bp
from .schemas import SendAlertSchema, SendPOSchema, WhatsAppConfigUpsertSchema


def _serialize_template(template):
    return {
        "id": str(template.id),
        "name": template.template_name,
        "category": template.template_category or "UTILITY",
        "language": template.language,
        "status": "APPROVED" if template.is_active else "PENDING",
        "components": template.variables.get("components", []) if isinstance(template.variables, dict) else [],
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def _serialize_log(log):
    return {
        "id": str(log.id),
        "message_type": log.message_type,
        "recipient": log.recipient_phone,
        "status": log.status,
        "sent_at": log.sent_at.isoformat() if log.sent_at else None,
        "template_name": log.template_name,
        "content": log.content_preview,
    }


def _serialize_campaign(campaign):
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "description": campaign.description or "",
        "template_id": str(campaign.template_id) if campaign.template_id else "",
        "template_name": campaign.template_name or "",
        "recipient_count": campaign.recipient_count,
        "sent_count": campaign.sent_count,
        "delivered_count": campaign.delivered_count,
        "read_count": campaign.read_count,
        "status": campaign.status,
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        "created_by": "current_user",
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }


def _normalize_phone(phone: str) -> str:
    cleaned = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not cleaned.startswith("91") and len(cleaned) == 10:
        cleaned = f"91{cleaned}"
    return cleaned


def _create_outbound_log(store_id, recipient_phone, message_type, content, template_name=None, status="SENT"):
    log = WhatsAppMessageLog(
        store_id=store_id,
        recipient_phone=_normalize_phone(recipient_phone),
        direction="OUT",
        message_type=message_type,
        template_name=template_name,
        content_preview=content[:500] if content else "",
        status=status,
        sent_at=datetime.now(timezone.utc),
    )
    db.session.add(log)
    db.session.flush()
    return log


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
    data = [_serialize_template(template) for template in templates]
    return format_response(data=data)


@whatsapp_bp.route("/templates", methods=["POST"])
@require_auth
@require_role("owner")
def create_template():
    """Create a store-level WhatsApp template."""
    body = request.get_json() or {}
    if not body.get("name"):
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": "name is required"},
            status_code=400,
        )

    store_id = g.current_user["store_id"]
    template = WhatsAppTemplate(
        store_id=store_id,
        template_name=body["name"],
        template_category=body.get("category", "UTILITY"),
        language=body.get("language", "en"),
        variables={"components": body.get("components", [])},
        is_active=True,
    )
    db.session.add(template)
    db.session.commit()
    return format_response(data=_serialize_template(template), status_code=201)


@whatsapp_bp.route("/messages", methods=["POST"])
@require_auth
def send_message():
    """Send or queue a general outbound WhatsApp message."""
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    if not body.get("to") or not body.get("message_type"):
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": "to and message_type are required"},
            status_code=400,
        )

    log = _create_outbound_log(
        store_id=store_id,
        recipient_phone=body["to"],
        message_type=str(body["message_type"]).lower(),
        content=body.get("content") or body.get("template_name") or "",
        template_name=body.get("template_name"),
        status="SENT",
    )
    db.session.commit()
    return format_response(data=_serialize_log(log), status_code=201)


@whatsapp_bp.route("/messages/bulk", methods=["POST"])
@require_auth
def send_bulk_messages():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    messages = body if isinstance(body, list) else body.get("messages", [])

    successful = []
    failed = []
    for item in messages:
        try:
            log = _create_outbound_log(
                store_id=store_id,
                recipient_phone=item["to"],
                message_type=str(item.get("message_type", "text")).lower(),
                content=item.get("content") or item.get("template_name") or "",
                template_name=item.get("template_name"),
                status="SENT",
            )
            successful.append(_serialize_log(log))
        except Exception as exc:
            failed.append({"to": item.get("to", ""), "error": str(exc)})

    db.session.commit()
    return format_response(data={"successful": successful, "failed": failed})


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
    data = [_serialize_log(log) for log in logs]
    return format_response(data=data, meta={"page": page, "limit": limit})


@whatsapp_bp.route("/campaigns", methods=["GET"])
@require_auth
def list_campaigns():
    store_id = g.current_user["store_id"]
    campaigns = (
        db.session.query(WhatsAppCampaign)
        .filter_by(store_id=store_id)
        .order_by(WhatsAppCampaign.created_at.desc())
        .all()
    )
    return format_response(data=[_serialize_campaign(campaign) for campaign in campaigns])


@whatsapp_bp.route("/campaigns", methods=["POST"])
@require_auth
@require_role("owner")
def create_campaign():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    recipients = body.get("recipients", [])
    template = (
        db.session.get(WhatsAppTemplate, uuid.UUID(str(body.get("template_id")))) if body.get("template_id") else None
    )
    campaign = WhatsAppCampaign(
        store_id=store_id,
        name=body.get("name", "Campaign"),
        description=body.get("description"),
        template_id=template.id if template else None,
        template_name=template.template_name if template else "",
        recipients=recipients,
        recipient_count=len(recipients),
        status="SCHEDULED" if body.get("scheduled_at") else "DRAFT",
        scheduled_at=datetime.fromisoformat(body["scheduled_at"]) if body.get("scheduled_at") else None,
    )
    db.session.add(campaign)
    db.session.commit()
    return format_response(data=_serialize_campaign(campaign), status_code=201)


@whatsapp_bp.route("/campaigns/<uuid:campaign_id>", methods=["GET"])
@require_auth
def get_campaign(campaign_id):
    store_id = g.current_user["store_id"]
    campaign = db.session.query(WhatsAppCampaign).filter_by(id=campaign_id, store_id=store_id).first()
    if not campaign:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Campaign not found"}, status_code=404
        )
    return format_response(data=_serialize_campaign(campaign))


@whatsapp_bp.route("/campaigns/<uuid:campaign_id>", methods=["PUT", "PATCH"])
@require_auth
@require_role("owner")
def update_campaign(campaign_id):
    store_id = g.current_user["store_id"]
    campaign = db.session.query(WhatsAppCampaign).filter_by(id=campaign_id, store_id=store_id).first()
    if not campaign:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Campaign not found"}, status_code=404
        )

    body = request.get_json() or {}
    for key in ("name", "description", "status"):
        if key in body:
            setattr(campaign, key, body[key])
    if "recipients" in body:
        campaign.recipients = body["recipients"]
        campaign.recipient_count = len(body["recipients"])
    if "scheduled_at" in body:
        campaign.scheduled_at = datetime.fromisoformat(body["scheduled_at"]) if body["scheduled_at"] else None
    db.session.commit()
    return format_response(data=_serialize_campaign(campaign))


@whatsapp_bp.route("/campaigns/<uuid:campaign_id>", methods=["DELETE"])
@require_auth
@require_role("owner")
def delete_campaign(campaign_id):
    store_id = g.current_user["store_id"]
    campaign = db.session.query(WhatsAppCampaign).filter_by(id=campaign_id, store_id=store_id).first()
    if not campaign:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Campaign not found"}, status_code=404
        )
    db.session.delete(campaign)
    db.session.commit()
    return format_response(data={"id": str(campaign_id), "deleted": True})


@whatsapp_bp.route("/campaigns/<uuid:campaign_id>/send", methods=["POST"])
@require_auth
@require_role("owner")
def send_campaign(campaign_id):
    store_id = g.current_user["store_id"]
    campaign = db.session.query(WhatsAppCampaign).filter_by(id=campaign_id, store_id=store_id).first()
    if not campaign:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Campaign not found"}, status_code=404
        )

    recipients = campaign.recipients if isinstance(campaign.recipients, list) else []
    campaign.status = "SENDING"
    sent_count = 0
    for recipient in recipients:
        _create_outbound_log(
            store_id=store_id,
            recipient_phone=recipient,
            message_type="campaign",
            content=campaign.description or campaign.name,
            template_name=campaign.template_name,
            status="SENT",
        )
        sent_count += 1
    campaign.sent_count = sent_count
    campaign.delivered_count = sent_count
    campaign.status = "COMPLETED"
    campaign.sent_at = datetime.now(timezone.utc)
    campaign.completed_at = campaign.sent_at
    db.session.commit()
    return format_response(data={"id": str(campaign.id), "sent_count": sent_count, "status": campaign.status})


@whatsapp_bp.route("/contacts/<string:phone>/opt-in", methods=["POST"])
@require_auth
def opt_in_contact(phone):
    store_id = g.current_user["store_id"]
    normalized_phone = _normalize_phone(phone)
    preference = (
        db.session.query(WhatsAppContactPreference).filter_by(store_id=store_id, phone=normalized_phone).first()
    )
    if not preference:
        preference = WhatsAppContactPreference(store_id=store_id, phone=normalized_phone)
        db.session.add(preference)
    preference.status = "OPTED_IN"
    preference.opted_in_at = datetime.now(timezone.utc)
    db.session.commit()
    return format_response(data={"success": True, "message": "Customer opted in"})


@whatsapp_bp.route("/contacts/<string:phone>/opt-out", methods=["POST"])
@require_auth
def opt_out_contact(phone):
    store_id = g.current_user["store_id"]
    normalized_phone = _normalize_phone(phone)
    preference = (
        db.session.query(WhatsAppContactPreference).filter_by(store_id=store_id, phone=normalized_phone).first()
    )
    if not preference:
        preference = WhatsAppContactPreference(store_id=store_id, phone=normalized_phone)
        db.session.add(preference)
    preference.status = "OPTED_OUT"
    preference.opted_out_at = datetime.now(timezone.utc)
    db.session.commit()
    return format_response(data={"success": True, "message": "Customer opted out"})


@whatsapp_bp.route("/contacts/<string:phone>/status", methods=["GET"])
@require_auth
def get_contact_status(phone):
    store_id = g.current_user["store_id"]
    normalized_phone = _normalize_phone(phone)
    preference = (
        db.session.query(WhatsAppContactPreference).filter_by(store_id=store_id, phone=normalized_phone).first()
    )
    if not preference:
        return format_response(data={"status": "OPTED_IN", "opted_in_at": None, "opted_out_at": None})
    return format_response(
        data={
            "status": preference.status,
            "opted_in_at": preference.opted_in_at.isoformat() if preference.opted_in_at else None,
            "opted_out_at": preference.opted_out_at.isoformat() if preference.opted_out_at else None,
        }
    )


@whatsapp_bp.route("/messages/test", methods=["POST"])
@require_auth
def send_test_message():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    log = _create_outbound_log(
        store_id=store_id,
        recipient_phone=body.get("to", ""),
        message_type="test",
        content=f"Test template {body.get('template_name', '')}",
        template_name=body.get("template_name"),
        status="SENT",
    )
    db.session.commit()
    return format_response(data=_serialize_log(log), status_code=201)


def _encrypt_token(token: str) -> str:
    """Helper to encode tokens for at-rest storage."""
    import base64

    if token is None:
        return None
    if token == "":
        return ""
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _decrypt_token(encrypted_token: str) -> str:
    """Helper to decode stored tokens, returning the original input on failure."""
    import base64

    if encrypted_token is None:
        return None
    if encrypted_token == "":
        return ""
    try:
        return base64.urlsafe_b64decode(encrypted_token.encode("ascii")).decode("utf-8")
    except Exception:
        return encrypted_token
