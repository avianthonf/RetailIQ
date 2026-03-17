"""
WhatsApp Meta Cloud API Client.
"""

import logging
import os
import uuid

import requests

logger = logging.getLogger(__name__)


def get_redis_client():
    from ..utils.redis import get_redis_client as _get

    return _get()


def send_template_message(
    phone_number_id: str,
    access_token: str,
    to_phone: str,
    template_name: str,
    language: str = "en",
    components: list = None,
) -> dict:
    """
    Send a WhatsApp template message via Meta Cloud API.
    If WHATSAPP_DRY_RUN is set, skips the actual HTTP call and returns a mocked response.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {"name": template_name, "language": {"code": language}},
    }
    if components:
        payload["template"]["components"] = components

    return _send_payload(phone_number_id, access_token, payload)


def send_text_message(phone_number_id: str, access_token: str, to_phone: str, text: str) -> dict:
    """
    Send a WhatsApp plain text message via Meta Cloud API.
    If WHATSAPP_DRY_RUN is set, skips the actual HTTP call and returns a mocked response.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    return _send_payload(phone_number_id, access_token, payload)


def _send_payload(phone_number_id: str, access_token: str, payload: dict) -> dict:
    if os.environ.get("WHATSAPP_DRY_RUN", "").lower() == "true":
        logger.info(f"[DRY_RUN] Sending WA message to {payload.get('to')}: {payload}")
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": payload.get("to"), "wa_id": payload.get("to")}],
            "messages": [{"id": f"wamid.{uuid.uuid4().hex}"}],
            "_dry_run": True,
        }

    url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending WA message to {payload.get('to')}: {e}")
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            error_msg = e.response.text
        return {"error": error_msg}
