"""
Tests for /api/v1/ inventory and products endpoints.
Standardized to match the unified API structure.
"""

from datetime import datetime, timezone

import pytest

from app import db
from app.models import Alert, Product, ProductPriceHistory, StockAdjustment, StockAudit, StockAuditItem

# ─────────────────────────────────────────────────────────────
# 1. Create product – happy path
# ─────────────────────────────────────────────────────────────


def test_create_product_success(client, owner_headers, test_store, test_category):
    payload = {
        "name": "Basmati Rice 1kg",
        "category_id": test_category.category_id,
        "cost_price": 50.0,
        "selling_price": 70.0,
        "current_stock": 100.0,
        "reorder_level": 20.0,
        "uom": "kg",
    }
    # Unified route is /api/v1/inventory
    resp = client.post("/api/v1/inventory", json=payload, headers=owner_headers)

    assert resp.status_code == 201, f"Expected 201 but got {resp.status_code}: {resp.data}"
    data = resp.json["data"]
    assert data["name"] == "Basmati Rice 1kg"
    assert data["selling_price"] == 70.0
    assert data["cost_price"] == 50.0

    # SKU auto-generated with zero-padded store_id
    assert data["sku_code"].startswith(f"SKU-{test_store.store_id:04d}-")


# ─────────────────────────────────────────────────────────────
# 2. selling_price < cost_price → 422
# ─────────────────────────────────────────────────────────────


def test_create_product_selling_below_cost_rejected(client, owner_headers):
    payload = {
        "name": "Loss Leader",
        "cost_price": 100.0,
        "selling_price": 80.0,  # < cost → should be rejected
    }
    resp = client.post("/api/v1/inventory", json=payload, headers=owner_headers)
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────
# 3. GET /products – list & filters
# ─────────────────────────────────────────────────────────────


def test_list_products_enhanced(client, owner_headers, test_product):
    resp = client.get("/api/v1/inventory", headers=owner_headers)
    assert resp.status_code == 200
    data = resp.json["data"]
    assert len(data) >= 1


def test_get_alerts(client, owner_headers, test_store, test_product):
    # Unified route is /api/v1/alerts (based on inventory blueprint registration)
    alert = Alert(
        store_id=test_store.store_id,
        alert_type="LOW_STOCK",
        priority="HIGH",
        product_id=test_product.product_id,
        message="Test alert",
    )
    db.session.add(alert)
    db.session.commit()

    resp = client.get("/api/v1/inventory/alerts", headers=owner_headers)
    assert resp.status_code == 200
    assert len(resp.json["data"]) >= 1


def test_unauthenticated_returns_401(client):
    resp = client.get("/api/v1/inventory")
    assert resp.status_code == 401
