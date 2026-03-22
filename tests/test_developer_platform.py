"""
Integration tests for the Developer Platform.

Coverage:
1. Developer registration
2. Developer application CRUD
3. Webhook event broadcasting on transaction creation
4. Marketplace visibility
"""

from unittest.mock import patch

import pytest

from app import db
from app.models import Category, DeveloperApplication, Product, Store, User


@pytest.fixture
def developer_account(app):
    user = User(
        mobile_number="9876543210",
        full_name="Dev User",
        email="dev@example.com",
        role="owner",
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()

    store = Store(store_name="Dev Store", owner_user_id=user.user_id)
    db.session.add(store)
    db.session.commit()

    user.store_id = store.store_id
    db.session.commit()
    return user


def _get_auth_header(user):
    from app.auth.utils import generate_access_token

    token = generate_access_token(user.user_id, user.store_id, "owner")
    return {"Authorization": f"Bearer {token}"}


def test_developer_registration(client):
    """Test registering a new developer account."""
    resp = client.post(
        "/api/v1/developer/register",
        json={
            "name": "Acme Corp",
            "email": "acme@example.com",
            "organization": "Acme Inc",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "Acme Corp"


def test_duplicate_developer_registration(client):
    """Registering the same email twice returns 400."""
    client.post(
        "/api/v1/developer/register",
        json={
            "name": "First",
            "email": "dup@example.com",
        },
    )
    resp = client.post(
        "/api/v1/developer/register",
        json={
            "name": "Second",
            "email": "dup@example.com",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "DUPLICATE_EMAIL"


def test_app_creation_update_delete_and_secret_rotation(client, developer_account):
    """Creating an app returns credentials and the app can be managed afterwards."""
    headers = _get_auth_header(developer_account)
    create_resp = client.post(
        "/api/v1/developer/apps",
        json={
            "name": "Inventory Sync",
            "description": "Syncs inventory",
            "app_type": "BACKEND",
            "scopes": ["read:inventory", "read:sales"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    data = create_resp.get_json()["data"]
    assert "client_id" in data
    assert "client_secret" in data
    assert data["name"] == "Inventory Sync"
    assert len(data["client_id"]) == 32

    client_id = data["client_id"]

    update_resp = client.patch(
        f"/api/v1/developer/apps/{client_id}",
        json={"name": "Inventory Sync v2", "scopes": ["read:inventory"]},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["data"]["name"] == "Inventory Sync v2"

    rotate_resp = client.post(f"/api/v1/developer/apps/{client_id}/regenerate-secret", headers=headers)
    assert rotate_resp.status_code == 200
    assert rotate_resp.get_json()["data"]["client_secret"]

    delete_resp = client.delete(f"/api/v1/developer/apps/{client_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()["data"]["deleted"] is True


@patch("app.transactions.services.rebuild_daily_aggregates.delay")
@patch("app.transactions.services.evaluate_alerts.delay")
@patch("app.utils.webhooks.deliver_webhook.delay")
def test_webhook_broadcast_on_transaction(mock_deliver, mock_alerts, mock_rebuild, client, developer_account):
    """Creating a transaction broadcasts a webhook event to subscribed apps."""
    headers = _get_auth_header(developer_account)

    app_resp = client.post(
        "/api/v1/developer/apps",
        json={
            "name": "Webhook App",
            "app_type": "BACKEND",
            "scopes": ["read:sales"],
        },
        headers=headers,
    )
    client_id = app_resp.get_json()["data"]["client_id"]

    dev_app = db.session.query(DeveloperApplication).filter_by(client_id=client_id).first()
    dev_app.webhook_url = "https://example.com/hook"
    dev_app.webhook_secret = "test-secret"
    db.session.commit()

    cat = Category(name="Misc", store_id=developer_account.store_id)
    db.session.add(cat)
    db.session.flush()

    p = Product(
        name="Webhook Item",
        sku_code="WBH-001",
        store_id=developer_account.store_id,
        category_id=cat.category_id,
        cost_price=10,
        selling_price=20,
        current_stock=100,
    )
    db.session.add(p)
    db.session.commit()

    txn_resp = client.post(
        "/api/v1/transactions",
        json={
            "transaction_id": "550e8400-e29b-41d4-a716-446655440099",
            "timestamp": "2026-03-09T12:00:00",
            "payment_mode": "CASH",
            "line_items": [{"product_id": p.product_id, "quantity": 1, "selling_price": 20}],
        },
        headers=headers,
    )
    assert txn_resp.status_code == 201, f"Expected 201, got {txn_resp.status_code}: {txn_resp.get_data(as_text=True)}"
    assert mock_deliver.called


def test_marketplace_empty(client):
    """Marketplace returns empty list when no approved apps exist."""
    resp = client.get("/api/v1/developer/marketplace")
    assert resp.status_code == 200
    assert resp.get_json()["data"] == []
