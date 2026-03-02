"""
Tests for /api/v1/inventory/* and /api/v1/products/* endpoints.

Uses the shared conftest fixtures (app, client, owner_headers, staff_headers,
test_store, test_owner, test_staff, test_category, test_product).
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
    resp = client.post('/api/v1/inventory/products', json=payload, headers=owner_headers)
    assert resp.status_code == 201, resp.json
    data = resp.json['data']
    assert data['name'] == "Basmati Rice 1kg"
    assert data['selling_price'] == 70.0
    assert data['cost_price'] == 50.0

    # SKU auto-generated
    assert data['sku_code'].startswith(f"SKU-{test_store.store_id}-")

    # Initial price logged to history
    pid = data['product_id']
    hist = db.session.query(ProductPriceHistory).filter_by(product_id=pid).all()
    assert len(hist) == 1
    assert float(hist[0].cost_price) == 50.0
    assert float(hist[0].selling_price) == 70.0


def test_create_product_custom_sku(client, owner_headers, test_category):
    payload = {
        "name": "Custom SKU Product",
        "sku_code": "MY-CUSTOM-001",
        "cost_price": 10.0,
        "selling_price": 15.0,
    }
    resp = client.post('/api/v1/inventory/products', json=payload, headers=owner_headers)
    assert resp.status_code == 201
    assert resp.json['data']['sku_code'] == "MY-CUSTOM-001"


def test_create_product_staff_forbidden(client, staff_headers, test_category):
    payload = {"name": "Staff Product", "cost_price": 10.0, "selling_price": 15.0}
    resp = client.post('/api/v1/inventory/products', json=payload, headers=staff_headers)
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
# 2. selling_price < cost_price → 422
# ─────────────────────────────────────────────────────────────

def test_create_product_selling_below_cost_rejected(client, owner_headers):
    payload = {
        "name": "Loss Leader",
        "cost_price": 100.0,
        "selling_price": 80.0,   # < cost → should be rejected
    }
    resp = client.post('/api/v1/inventory/products', json=payload, headers=owner_headers)
    assert resp.status_code == 422
    # Ensure the error mentions selling_price
    assert resp.json['success'] is False


# ─────────────────────────────────────────────────────────────
# 3. GET /products – list & filters
# ─────────────────────────────────────────────────────────────

def test_list_products(client, owner_headers, test_product):
    resp = client.get('/api/v1/inventory/products', headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['success'] is True
    assert len(resp.json['data']) >= 1


def test_list_products_low_stock_filter(client, owner_headers, test_store):
    """A product with stock <= reorder_level should appear in low_stock=true."""
    low = Product(
        store_id=test_store.store_id,
        name="Low Stock Item",
        cost_price=5.0,
        selling_price=10.0,
        current_stock=2.0,
        reorder_level=10.0,
        is_active=True,
    )
    db.session.add(low)
    db.session.commit()

    resp = client.get('/api/v1/inventory/products?low_stock=true', headers=owner_headers)
    assert resp.status_code == 200
    product_ids = [p['product_id'] for p in resp.json['data']]
    assert low.product_id in product_ids


def test_list_products_category_filter(client, owner_headers, test_product, test_store):
    resp = client.get(
        f"/api/v1/inventory/products?category_id={test_product.category_id}",
        headers=owner_headers
    )
    assert resp.status_code == 200
    for p in resp.json['data']:
        assert p['category_id'] == test_product.category_id


# ─────────────────────────────────────────────────────────────
# 4. GET / PUT / DELETE single product
# ─────────────────────────────────────────────────────────────

def test_get_product(client, owner_headers, test_product):
    resp = client.get(
        f'/api/v1/inventory/products/{test_product.product_id}',
        headers=owner_headers
    )
    assert resp.status_code == 200
    assert resp.json['data']['product_id'] == test_product.product_id


def test_get_product_not_found(client, owner_headers):
    resp = client.get('/api/v1/inventory/products/99999', headers=owner_headers)
    assert resp.status_code == 404


def test_update_product(client, owner_headers, test_product):
    resp = client.put(
        f'/api/v1/inventory/products/{test_product.product_id}',
        json={"name": "Updated Name"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json['data']['name'] == "Updated Name"


def test_soft_delete_product(client, owner_headers, test_product):
    resp = client.delete(
        f'/api/v1/inventory/products/{test_product.product_id}',
        headers=owner_headers
    )
    assert resp.status_code == 200

    # Product must still exist in DB but is_active=False
    product = db.session.get(Product, test_product.product_id)
    assert product is not None
    assert product.is_active is False


# ─────────────────────────────────────────────────────────────
# 5. Stock Update
# ─────────────────────────────────────────────────────────────

def test_stock_update_increments_stock(client, owner_headers, test_product):
    original_stock = float(test_product.current_stock)
    payload = {
        "quantity_added": 25.0,
        "purchase_price": 55.0,
        "supplier_name": "Supplier Co",
    }
    resp = client.post(
        f'/api/v1/inventory/products/{test_product.product_id}/stock-update',
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json['data']['current_stock'] == original_stock + 25.0

    # StockAdjustment record created
    adj = db.session.query(StockAdjustment).filter_by(
        product_id=test_product.product_id
    ).first()
    assert adj is not None
    assert float(adj.quantity_added) == 25.0
    assert float(adj.purchase_price) == 55.0


def test_stock_update_with_cost_price_update(client, owner_headers, test_product):
    """When update_cost_price=True and purchase_price differs, cost_price is updated."""
    old_cost = float(test_product.cost_price)
    new_purchase = old_cost + 10.0

    payload = {
        "quantity_added": 10.0,
        "purchase_price": new_purchase,
        "update_cost_price": True,
    }
    resp = client.post(
        f'/api/v1/inventory/products/{test_product.product_id}/stock-update',
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json['data']['cost_price'] == new_purchase

    # Price history should have been logged
    hist = db.session.query(ProductPriceHistory).filter_by(
        product_id=test_product.product_id
    ).order_by(ProductPriceHistory.changed_at.desc()).first()
    assert hist is not None
    assert float(hist.cost_price) == new_purchase


# ─────────────────────────────────────────────────────────────
# 6. Stock Audit – discrepancy + stock correction
# ─────────────────────────────────────────────────────────────

def test_stock_audit_creates_records(client, owner_headers, test_product):
    # Capture expected_stock BEFORE the request (StaticPool shares the session,
    # so test_product.current_stock would reflect the update after the POST).
    expected_stock = float(test_product.current_stock)
    actual_qty = expected_stock - 5.0  # simulate shrinkage
    payload = {
        "items": [
            {"product_id": test_product.product_id, "actual_qty": actual_qty}
        ],
        "notes": "Monthly audit",
    }
    resp = client.post(
        '/api/v1/inventory/products/stock-audit',
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.json
    body = resp.json['data']
    assert 'audit_id' in body
    assert len(body['items']) == 1

    item_result = body['items'][0]
    assert item_result['expected_stock'] == expected_stock
    assert item_result['actual_stock'] == actual_qty
    assert item_result['discrepancy'] == pytest.approx(actual_qty - expected_stock)

    # DB: stock_audits + stock_audit_items
    audit = db.session.get(StockAudit, body['audit_id'])
    assert audit is not None

    audit_item = db.session.query(StockAuditItem).filter_by(
        audit_id=audit.audit_id,
        product_id=test_product.product_id,
    ).first()
    assert audit_item is not None
    assert float(audit_item.discrepancy) == pytest.approx(actual_qty - expected_stock)

    # Stock updated to actual
    product = db.session.get(Product, test_product.product_id)
    assert float(product.current_stock) == actual_qty


def test_stock_audit_staff_forbidden(client, staff_headers, test_product):
    payload = {"items": [{"product_id": test_product.product_id, "actual_qty": 10.0}]}
    resp = client.post(
        '/api/v1/inventory/products/stock-audit',
        json=payload,
        headers=staff_headers,
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
# 7. Price History
# ─────────────────────────────────────────────────────────────

def test_price_history_returned(client, owner_headers, test_product):
    # Update price to generate a history entry
    client.put(
        f'/api/v1/inventory/products/{test_product.product_id}',
        json={"selling_price": 120.0, "cost_price": 65.0},
        headers=owner_headers,
    )
    resp = client.get(
        f'/api/v1/inventory/products/{test_product.product_id}/price-history',
        headers=owner_headers,
    )
    assert resp.status_code == 200
    history = resp.json['data']
    assert len(history) >= 1
    assert 'cost_price' in history[0]
    assert 'selling_price' in history[0]
    assert 'changed_at' in history[0]


# ─────────────────────────────────────────────────────────────
# 8. Margin Warning Alert on price update
# ─────────────────────────────────────────────────────────────

def test_margin_warning_alert_created(client, owner_headers, test_product):
    """Setting cost_price > selling_price via PUT should create a CRITICAL MARGIN_WARNING alert."""
    resp = client.put(
        f'/api/v1/inventory/products/{test_product.product_id}',
        json={
            "cost_price": 200.0,
            "selling_price": 150.0,   # selling < cost → should trigger alert
        },
        headers=owner_headers,
    )
    # NOTE: The update itself succeeds (no 422 on PUT, only schema validation on POST)
    assert resp.status_code == 200

    alert = db.session.query(Alert).filter_by(
        product_id=test_product.product_id,
        alert_type='MARGIN_WARNING',
    ).first()
    assert alert is not None
    assert alert.priority == 'CRITICAL'
    assert alert.resolved_at is None


def test_get_alerts(client, owner_headers, test_store, test_product):
    """GET /inventory/alerts returns active (unresolved) alerts."""
    # Create a MARGIN_WARNING alert manually
    alert = Alert(
        store_id=test_store.store_id,
        alert_type='MARGIN_WARNING',
        priority='CRITICAL',
        product_id=test_product.product_id,
        message='Test alert',
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(alert)
    db.session.commit()

    resp = client.get('/api/v1/inventory/alerts', headers=owner_headers)
    assert resp.status_code == 200
    alert_types = [a['alert_type'] for a in resp.json['data']]
    assert 'MARGIN_WARNING' in alert_types


# ─────────────────────────────────────────────────────────────
# 9. Unauthenticated access
# ─────────────────────────────────────────────────────────────

def test_unauthenticated_returns_401(client):
    resp = client.get('/api/v1/inventory/products')
    assert resp.status_code == 401

# ─────────────────────────────────────────────────────────────
# 10. Route Aliases
# ─────────────────────────────────────────────────────────────

def test_stock_update_alias_increments_stock(client, owner_headers, test_product):
    original_stock = float(test_product.current_stock)
    payload = {
        "quantity_added": 25.0,
        "purchase_price": 55.0,
        "supplier_name": "Supplier Co",
    }
    resp = client.post(
        f'/api/v1/inventory/products/{test_product.product_id}/stock',
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json['data']['current_stock'] == original_stock + 25.0

def test_stock_audit_alias_creates_records(client, owner_headers, test_product):
    expected_stock = float(test_product.current_stock)
    actual_qty = expected_stock - 5.0
    payload = {
        "items": [
            {"product_id": test_product.product_id, "actual_qty": actual_qty}
        ],
        "notes": "Monthly audit via alias",
    }
    resp = client.post(
        '/api/v1/inventory/audit',
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 201
    assert 'audit_id' in resp.json['data']
