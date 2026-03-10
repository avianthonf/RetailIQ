"""
Tests for WhatsApp Business API Integration (Prompt 8)
"""

from datetime import datetime, timezone

import pytest

from app import db
from app.models import (
    Alert,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Store,
    Supplier,
    User,
    WhatsAppConfig,
    WhatsAppMessageLog,
)
from app.whatsapp.client import send_text_message
from app.whatsapp.formatters import format_po_message
from app.whatsapp.routes import _encrypt_token

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def wa_config(app, test_store):
    """Seed WhatsApp configuration for the test store."""
    config = WhatsAppConfig(
        store_id=test_store.store_id,
        phone_number_id="123456789",
        webhook_verify_token="test_verify_token_123",
        is_active=True,
        waba_id="987654321",
    )
    # Encrypt the dummy token
    config.access_token_encrypted = _encrypt_token("dummy_access_token")
    db.session.add(config)
    db.session.commit()
    return config


@pytest.fixture
def test_alert(app, test_store):
    alert = Alert(
        store_id=test_store.store_id,
        alert_type="manual_alert",
        priority="HIGH",
        message="This is a test alert",
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(alert)
    db.session.commit()
    return alert


@pytest.fixture
def test_supplier(app, test_store):
    supplier = Supplier(store_id=test_store.store_id, name="Test Supplier", contact_name="John Doe", phone="9876543210")
    db.session.add(supplier)
    db.session.commit()
    return supplier


@pytest.fixture
def test_po(app, test_store, test_supplier, test_product):
    po = PurchaseOrder(store_id=test_store.store_id, supplier_id=test_supplier.id, status="DRAFT")
    db.session.add(po)
    db.session.commit()

    po_item = PurchaseOrderItem(po_id=po.id, product_id=test_product.product_id, ordered_qty=50.0, unit_price=100.0)
    db.session.add(po_item)
    db.session.commit()
    return po


@pytest.fixture(autouse=True)
def mock_whatsapp_dry_run(monkeypatch):
    """Force dry-run mode for all WhatsApp tests so we never hit the real Meta API."""
    monkeypatch.setenv("WHATSAPP_DRY_RUN", "true")


# ── Tests ──────────────────────────────────────────────────────────


def test_webhook_verification(client, wa_config):
    """GET with correct verify_token returns challenge."""
    challenge_val = "1158201444"
    resp = client.get(
        f"/api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=test_verify_token_123&hub.challenge={challenge_val}"
    )
    assert resp.status_code == 200
    assert resp.data.decode() == challenge_val


def test_webhook_invalid_token_rejected(client):
    """GET with wrong token returns 403."""
    resp = client.get("/api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=123")
    assert resp.status_code == 403


def test_access_token_encrypted_at_rest(client, owner_headers, test_store):
    """PUT config with token, query DB directly, assert token column is not plaintext."""
    resp = client.put(
        "/api/v1/whatsapp/config",
        headers=owner_headers,
        json={"phone_number_id": "111222", "access_token": "my_secret_token", "is_active": True},
    )
    assert resp.status_code == 200

    config = db.session.query(WhatsAppConfig).filter_by(store_id=test_store.store_id).first()
    assert config is not None
    assert config.access_token_encrypted is not None
    assert config.access_token_encrypted != "my_secret_token"
    # To double check, decrypted token should match
    from app.whatsapp.routes import _decrypt_token

    assert _decrypt_token(config.access_token_encrypted) == "my_secret_token"


def test_po_message_format(app, test_po):
    """Call formatter with seeded PO, assert output contains store name and product names."""
    with app.app_context():
        text = format_po_message(str(test_po.id), db.session)

        # Check if contents are formatted
        assert text.startswith("Purchase Order #"), text
        assert "From: Test Supermart" in text, text
        assert "Test Product x 50 @ ₹100" in text, text
        assert "Total: ₹5000" in text, text
        assert "Please confirm receipt" in text


def test_send_alert_dry_run(client, owner_headers, wa_config, test_alert):
    """Assert no real HTTP call made, log entry created."""
    # The autouse fixture mock_whatsapp_dry_run sets WHATSAPP_DRY_RUN=true
    resp = client.post("/api/v1/whatsapp/send-alert", headers=owner_headers, json={"alert_id": test_alert.alert_id})
    assert resp.status_code == 200, resp.data
    assert "message_id" in resp.json["data"]

    log = db.session.query(WhatsAppMessageLog).filter_by(message_type="alert", store_id=wa_config.store_id).first()
    assert log is not None
    assert log.status == "SENT"
    assert "This is a test alert" in log.content_preview
    assert log.direction == "OUT"
    assert log.recipient_phone == "919000000001"  # Extracted from Owner User mock


def test_send_po_creates_log_entry(client, owner_headers, wa_config, test_po):
    """POST /send-po, assert message_log row created with status QUEUED (or SENT for dry-run)."""
    resp = client.post("/api/v1/whatsapp/send-po", headers=owner_headers, json={"po_id": str(test_po.id)})
    assert resp.status_code == 200
    assert "message_id" in resp.json["data"]

    log = (
        db.session.query(WhatsAppMessageLog)
        .filter_by(message_type="purchase_order", store_id=wa_config.store_id)
        .first()
    )
    assert log is not None
    assert log.status == "QUEUED"  # as per routes.py, PO sets to QUEUED initially on 'messages' success in dry run
    assert "Purchase Order #" in log.content_preview
    assert log.recipient_phone == "919876543210"  # test_supplier phone with 91 prepended
