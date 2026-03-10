"""
Integration tests for the Developer Platform & API Ecosystem.

Tests cover:
1. Developer Registration
2. Application Creation (OAuth client provisioning)
3. OAuth Client Credentials token exchange
4. API v2 endpoint access with OAuth token
5. Webhook event broadcasting on transaction creation
"""

from unittest.mock import MagicMock, patch

import pytest

from app import db
from app.models import Developer, DeveloperApplication, Product, Store, User

# ── Fake Redis for OAuth token flows ────────────────────────────────────────


class FakeRedis:
    """Minimal in-memory Redis substitute for testing."""

    def __init__(self):
        self._data = {}
        self._ttl = {}

    def hset(self, key, mapping=None, **kwargs):
        if mapping:
            self._data[key] = {str(k): str(v) for k, v in mapping.items()}

    def hgetall(self, key):
        return self._data.get(key, {})

    def expire(self, key, seconds):
        self._ttl[key] = seconds

    def delete(self, key):
        self._data.pop(key, None)
        self._ttl.pop(key, None)

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, ex=None):
        self._data[key] = value

    def incr(self, key):
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    def hincrby(self, key, field, amount):
        data = self._data.setdefault(key, {})
        val = int(data.get(field, 0)) + amount
        data[field] = str(val)
        return val

    def incrby(self, key, amount):
        val = int(self._data.get(key, 0)) + amount
        self._data[key] = str(val)
        return val

    def incrbyfloat(self, key, amount):
        val = float(self._data.get(key, 0)) + amount
        self._data[key] = str(val)
        return val

    def pipeline(self):
        return self

    def execute(self):
        return []

    def keys(self, pattern="*"):
        import fnmatch

        return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()


_fake_redis_instance = FakeRedis()


@pytest.fixture(autouse=True)
def mock_redis():
    """Patch get_redis_client globally for all developer platform tests."""
    with patch("app.auth.utils.get_redis_client", return_value=_fake_redis_instance):
        with patch("app.auth.oauth.get_redis_client", return_value=_fake_redis_instance):
            with patch("app.developer.gateway.get_redis_client", return_value=_fake_redis_instance):
                with patch("app.auth.routes.get_redis_client", return_value=_fake_redis_instance):
                    yield _fake_redis_instance
    # Clear between tests
    _fake_redis_instance._data.clear()
    _fake_redis_instance._ttl.clear()


# ── Fixtures ────────────────────────────────────────────────────────────────


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


# ── Tests ───────────────────────────────────────────────────────────────────


def test_developer_registration(client, developer_account):
    """Test registering a new developer account."""
    headers = _get_auth_header(developer_account)
    resp = client.post(
        "/api/v1/developer/register",
        json={
            "name": "Acme Corp",
            "email": "acme@example.com",
            "organization": "Acme Inc",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["name"] == "Acme Corp"


def test_duplicate_developer_registration(client, developer_account):
    """Registering the same email twice returns 400."""
    headers = _get_auth_header(developer_account)
    client.post(
        "/api/v1/developer/register",
        json={
            "name": "First",
            "email": "dup@example.com",
        },
        headers=headers,
    )
    resp = client.post(
        "/api/v1/developer/register",
        json={
            "name": "Second",
            "email": "dup@example.com",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "DUPLICATE_EMAIL"


def test_app_creation_with_credentials(client, developer_account):
    """Creating an app returns client_id and client_secret."""
    headers = _get_auth_header(developer_account)
    resp = client.post(
        "/api/v1/developer/apps",
        json={
            "name": "Inventory Sync",
            "description": "Syncs inventory",
            "app_type": "BACKEND",
            "scopes": ["read:inventory", "read:sales"],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert "client_id" in data
    assert "client_secret" in data
    assert data["name"] == "Inventory Sync"
    assert len(data["client_id"]) == 32  # hex(16)


def test_oauth_client_credentials_flow(client, developer_account):
    """Full OAuth client-credentials flow: create app → get token → call V2 API."""
    headers = _get_auth_header(developer_account)

    # 1. Create app
    app_resp = client.post(
        "/api/v1/developer/apps",
        json={
            "name": "Test App",
            "app_type": "BACKEND",
            "scopes": ["read:inventory"],
        },
        headers=headers,
    )
    assert app_resp.status_code == 201
    creds = app_resp.get_json()["data"]

    # 2. Exchange credentials for token
    token_resp = client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
        },
    )
    assert token_resp.status_code == 200
    token_data = token_resp.get_json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] == 3600

    # 3. Seed a product and call V2 inventory endpoint
    p = Product(
        name="Test Gadget",
        sku_code="GAD-001",
        store_id=developer_account.store_id,
        cost_price=100,
        selling_price=150,
        current_stock=10,
    )
    db.session.add(p)
    db.session.commit()

    api_resp = client.get(
        f"/api/v2/inventory?store_id={developer_account.store_id}",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert api_resp.status_code == 200
    inv_data = api_resp.get_json()["data"]
    assert len(inv_data) > 0
    assert inv_data[0]["name"] == "Test Gadget"


def test_oauth_invalid_credentials(client, developer_account):
    """Invalid client_secret returns 401."""
    headers = _get_auth_header(developer_account)
    app_resp = client.post(
        "/api/v1/developer/apps",
        json={
            "name": "Bad Cred App",
            "app_type": "WEB",
            "scopes": ["read:inventory"],
        },
        headers=headers,
    )
    creds = app_resp.get_json()["data"]

    resp = client.post(
        "/oauth/token",
        json={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": "totally_wrong_secret",
        },
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_client"


@patch("app.transactions.services.rebuild_daily_aggregates.delay")
@patch("app.transactions.services.evaluate_alerts.delay")
@patch("app.utils.webhooks.deliver_webhook.delay")
def test_webhook_broadcast_on_transaction(mock_deliver, mock_alerts, mock_rebuild, client, developer_account):
    """Creating a transaction broadcasts a webhook event to subscribed apps."""
    headers = _get_auth_header(developer_account)

    # 1. Create app with webhook URL
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

    # Set webhook URL directly on the model
    dev_app = db.session.query(DeveloperApplication).filter_by(client_id=client_id).first()
    dev_app.webhook_url = "https://example.com/hook"
    dev_app.webhook_secret = "test-secret"
    db.session.commit()

    # 2. Seed a product
    p = Product(
        name="Webhook Item",
        sku_code="WBH-001",
        store_id=developer_account.store_id,
        cost_price=10,
        selling_price=20,
        current_stock=100,
    )
    db.session.add(p)
    db.session.commit()

    # 3. Create transaction (should trigger webhook broadcast)
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

    # 4. Verify webhook delivery was queued
    assert mock_deliver.called


def test_marketplace_empty(client, app):
    """Marketplace returns empty list when no approved apps exist."""
    resp = client.get("/api/v1/developer/marketplace")
    assert resp.status_code == 200
    assert resp.get_json()["data"] == []
