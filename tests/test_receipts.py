"""
Tests for /api/v1/ barcodes and receipts endpoints.
Standardized to match the unified API structure.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app import db
from app.auth.utils import generate_access_token
from app.models import Barcode, Product, ReceiptTemplate, Store, Transaction, User


@pytest.fixture
def setup(app):
    store = Store(store_name="Receipt Store", store_type="grocery")
    db.session.add(store)
    db.session.commit()

    owner = User(mobile_number="9800000001", full_name="Owner", role="owner", store_id=store.store_id, is_active=True)
    db.session.add(owner)
    db.session.commit()

    product = Product(store_id=store.store_id, name="Milk", selling_price=30.0, cost_price=20.0, current_stock=50.0)
    db.session.add(product)
    db.session.commit()

    token = generate_access_token(owner.user_id, store.store_id, "owner")
    headers = {"Authorization": f"Bearer {token}"}

    return {"store": store, "owner": owner, "product": product, "headers": headers}


@pytest.fixture
def seeded_barcode(setup):
    barcode = Barcode(
        product_id=setup["product"].product_id,
        store_id=setup["store"].store_id,
        barcode_value="1234567890",
        barcode_type="EAN13",
    )
    db.session.add(barcode)
    db.session.commit()
    return barcode


def test_barcode_lookup_found(client, setup, seeded_barcode):
    resp = client.get(f"/api/v1/barcodes/lookup?value={seeded_barcode.barcode_value}", headers=setup["headers"])
    assert resp.status_code == 200
    assert resp.json["data"]["barcode_value"] == seeded_barcode.barcode_value


def test_barcode_lookup_not_found(client, setup):
    resp = client.get("/api/v1/barcodes/lookup?value=99999", headers=setup["headers"])
    assert resp.status_code == 404


def test_receipt_template_upsert(client, setup):
    payload = {"header_text": "Welcome", "footer_text": "Thanks", "paper_width_mm": 80}
    resp = client.put("/api/v1/receipts/template", json=payload, headers=setup["headers"])
    assert resp.status_code == 200
    assert resp.json["data"]["header_text"] == "Welcome"


def test_print_job_created(client, setup):
    resp = client.post("/api/v1/receipts/print", json={"printer_mac_address": "AA:BB"}, headers=setup["headers"])
    assert resp.status_code == 201
    assert "job_id" in resp.json["data"]
