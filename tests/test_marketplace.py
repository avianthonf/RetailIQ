import pytest

from app.models import Supplier
from app.models.marketplace_models import (
    RFQ,
    CatalogItem,
    MarketplacePOItem,
    MarketplacePurchaseOrder,
    ProcurementRecommendation,
    RFQResponse,
    SupplierProfile,
)


def test_onboard_supplier(client, owner_headers):
    """Test onboarding a new supplier to the marketplace."""
    # First, let's create a supplier to attach the profile to, or the endpoint will create one
    rv = client.post(
        "/api/v2/marketplace/suppliers/onboard",
        headers=owner_headers,
        json={"business_name": "Acme Corp", "business_type": "MANUFACTURER"}
    )
    assert rv.status_code == 201
    data = rv.get_json()["data"]
    assert "id" in data
    assert data["business_name"] == "Acme Corp"

def test_search_catalog_empty(client, owner_headers):
    """Test searching catalog when empty."""
    rv = client.get("/api/v2/marketplace/search", headers=owner_headers)
    assert rv.status_code == 200
    data = rv.get_json()["data"]
    assert len(data["items"]) == 0
    assert data["total"] == 0

def test_create_rfq(client, owner_headers):
    """Test creating an RFQ."""
    rv = client.post(
        "/api/v2/marketplace/rfq",
        headers=owner_headers,
        json={"items": [{"category": "Electronics", "quantity": 100}]}
    )
    assert rv.status_code == 201
    data = rv.get_json()["data"]
    assert "rfq_id" in data

    # Get it back
    rv = client.get(f"/api/v2/marketplace/rfq/{data['rfq_id']}", headers=owner_headers)
    assert rv.status_code == 200
    rfq_data = rv.get_json()["data"]
    assert rfq_data["status"] == "OPEN"
    assert len(rfq_data["items"]) == 1

def test_create_order_missing_fields(client, owner_headers):
    """Test creating an order with missing fields."""
    rv = client.post(
        "/api/v2/marketplace/orders",
        headers=owner_headers,
        json={"supplier_id": 1} # missing items
    )
    assert rv.status_code == 422

def test_create_order(client, owner_headers, app):
    """Test creating a legitimate order."""
    # Setup: Create a SupplierProfile and CatalogItem manually
    with app.app_context():
        from app import db
        s = Supplier(store_id=1, name="Test Supplier")
        db.session.add(s)
        db.session.flush()

        sp = SupplierProfile(supplier_id=s.id, business_name="Test Business", business_type="WHOLESALER")
        db.session.add(sp)
        db.session.flush()

        ci = CatalogItem(supplier_profile_id=sp.id, name="Test Item", unit_price=10.0, available_quantity=100)
        db.session.add(ci)
        db.session.commit()

        sp_id = sp.id
        ci_id = ci.id

    rv = client.post(
        "/api/v2/marketplace/orders",
        headers=owner_headers,
        json={
            "supplier_id": sp_id,
            "items": [{"catalog_item_id": ci_id, "quantity": 5}],
            "finance_requested": True
        }
    )
    assert rv.status_code == 201
    data = rv.get_json()["data"]
    assert "order_id" in data
    assert "order_number" in data
    assert data["financing_decision"] == "APPROVED"

    order_id = data["order_id"]

    # Get the order back
    rv = client.get(f"/api/v2/marketplace/orders/{order_id}", headers=owner_headers)
    assert rv.status_code == 200
    order_data = rv.get_json()["data"]
    assert order_data["status"] == "SUBMITTED"
    assert order_data["financed"] is True
    assert order_data["loan_id"] is not None
    assert len(order_data["items"]) == 1
    assert order_data["items"][0]["quantity"] == 5
    assert order_data["items"][0]["subtotal"] == 50.0 # 5 * 10.0

    # Test getting tracking
    rv = client.get(f"/api/v2/marketplace/orders/{order_id}/track", headers=owner_headers)
    assert rv.status_code == 200
    track_data = rv.get_json()["data"]
    assert "tracking_events" in track_data

def test_recommendations(client, owner_headers):
    """Test fetching recommendations."""
    rv = client.get("/api/v2/marketplace/recommendations", headers=owner_headers)
    assert rv.status_code == 200
    data = rv.get_json()["data"]
    assert isinstance(data, list)

def test_supplier_dashboard(client, owner_headers, app):
    """Test getting supplier dashboard."""
    with app.app_context():
        from app import db
        s = Supplier(store_id=1, name="Dash Supplier")
        db.session.add(s)
        db.session.flush()
        sp = SupplierProfile(supplier_id=s.id, business_name="Dash Biz", business_type="MANUFACTURER")
        db.session.add(sp)
        db.session.commit()
        sp_id = sp.id

    rv = client.get(f"/api/v2/marketplace/suppliers/dashboard?supplier_id={sp_id}", headers=owner_headers)
    assert rv.status_code == 200
    data = rv.get_json()["data"]
    assert "total_orders" in data
    assert "revenue" in data

def test_supplier_catalog(client, owner_headers, app):
    """Test fetching a supplier's catalog."""
    with app.app_context():
        from app import db
        s = Supplier(store_id=1, name="Cat Supplier")
        db.session.add(s)
        db.session.flush()
        sp = SupplierProfile(supplier_id=s.id, business_name="Cat Biz", business_type="MANUFACTURER")
        db.session.add(sp)
        db.session.flush()
        ci1 = CatalogItem(supplier_profile_id=sp.id, name="Item 1", unit_price=10.0)
        ci2 = CatalogItem(supplier_profile_id=sp.id, name="Item 2", unit_price=20.0)
        db.session.add_all([ci1, ci2])
        db.session.commit()
        sp_id = sp.id

    rv = client.get(f"/api/v2/marketplace/suppliers/{sp_id}/catalog", headers=owner_headers)
    assert rv.status_code == 200
    data = rv.get_json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
