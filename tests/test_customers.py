"""
Tests for /api/v1/customers/* endpoints.

Reuses shared conftest fixtures (app, client, owner_headers, staff_headers,
test_store, test_owner, test_category, test_product).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import Customer, Transaction, TransactionItem

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _create_customer(store_id, name="Alice", mobile="9000000099"):
    c = Customer(
        store_id=store_id,
        name=name,
        mobile_number=mobile,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(c)
    db.session.commit()
    return c


def _make_txn(store_id, customer_id, product, qty=1.0, price=100.0,
              days_ago=0, payment_mode="CASH"):
    """Create a transaction with one line item."""
    tid = uuid.uuid4()
    txn = Transaction(
        transaction_id=tid,
        store_id=store_id,
        customer_id=customer_id,
        payment_mode=payment_mode,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        is_return=False,
    )
    db.session.add(txn)
    db.session.flush()

    item = TransactionItem(
        transaction_id=tid,
        product_id=product.product_id,
        quantity=qty,
        selling_price=price,
        original_price=price,
        discount_amount=0.0,
        cost_price_at_time=float(product.cost_price),
    )
    db.session.add(item)
    db.session.commit()
    return txn


# ─────────────────────────────────────────────────────────────
# 1. Create customer – happy path
# ─────────────────────────────────────────────────────────────

def test_create_customer_success(client, owner_headers, test_store):
    payload = {
        "name": "Bob Smith",
        "mobile_number": "9876543210",
        "email": "bob@example.com",
        "gender": "male",
    }
    resp = client.post('/api/v1/customers', json=payload, headers=owner_headers)
    assert resp.status_code == 201, resp.json
    data = resp.json['data']
    assert data['name'] == "Bob Smith"
    assert data['mobile_number'] == "9876543210"
    assert data['store_id'] == test_store.store_id


def test_create_customer_invalid_mobile(client, owner_headers):
    resp = client.post('/api/v1/customers',
                       json={"name": "Bad", "mobile_number": "abc"},
                       headers=owner_headers)
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────
# 2. Duplicate mobile – same store rejected, different store allowed
# ─────────────────────────────────────────────────────────────

def test_duplicate_mobile_same_store_rejected(client, owner_headers, test_store):
    _create_customer(test_store.store_id, mobile="9111111111")

    resp = client.post('/api/v1/customers',
                       json={"name": "Another", "mobile_number": "9111111111"},
                       headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json['error']['code'] == "DUPLICATE_MOBILE"


def test_duplicate_mobile_different_store_allowed(client, app, owner_headers, test_store):
    """Same mobile as a customer in test_store but inserted directly into a NEW store."""
    from app.auth.utils import generate_access_token
    from app.models import Store, User

    # create another store + owner
    other_store = Store(store_name="Other Shop", store_type="general")
    db.session.add(other_store)
    db.session.commit()

    other_owner = User(
        mobile_number="9000099000",
        full_name="Other Owner",
        role="owner",
        store_id=other_store.store_id,
        is_active=True,
    )
    db.session.add(other_owner)
    db.session.commit()

    other_token = generate_access_token(
        other_owner.user_id, other_store.store_id, "owner"
    )
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # insert mobile into test_store
    _create_customer(test_store.store_id, mobile="9222222222")

    # same mobile but via other_store owner → should succeed
    resp = client.post('/api/v1/customers',
                       json={"name": "Different Store Customer",
                             "mobile_number": "9222222222"},
                       headers=other_headers)
    assert resp.status_code == 201, resp.json


# ─────────────────────────────────────────────────────────────
# 3. GET / PUT single customer
# ─────────────────────────────────────────────────────────────

def test_get_customer(client, owner_headers, test_store):
    c = _create_customer(test_store.store_id, mobile="9300000001")
    resp = client.get(f'/api/v1/customers/{c.customer_id}', headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['data']['customer_id'] == c.customer_id


def test_get_customer_not_found(client, owner_headers):
    resp = client.get('/api/v1/customers/99999', headers=owner_headers)
    assert resp.status_code == 404


def test_update_customer(client, owner_headers, test_store):
    c = _create_customer(test_store.store_id, name="Old Name", mobile="9300000002")
    resp = client.put(f'/api/v1/customers/{c.customer_id}',
                      json={"name": "New Name", "notes": "VIP"},
                      headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['data']['name'] == "New Name"
    assert resp.json['data']['notes'] == "VIP"


# ─────────────────────────────────────────────────────────────
# 4. List customers with filters
# ─────────────────────────────────────────────────────────────

def test_list_customers(client, owner_headers, test_store):
    _create_customer(test_store.store_id, name="Carol", mobile="9400000001")
    _create_customer(test_store.store_id, name="Dave",  mobile="9400000002")

    resp = client.get('/api/v1/customers', headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['meta']['total'] >= 2


def test_list_customers_name_search(client, owner_headers, test_store):
    _create_customer(test_store.store_id, name="Unique XYZ Name", mobile="9400000003")
    resp = client.get('/api/v1/customers?name=Unique+XYZ', headers=owner_headers)
    assert resp.status_code == 200
    assert any("Unique XYZ" in p['name'] for p in resp.json['data'])


# ─────────────────────────────────────────────────────────────
# 5. Customer transactions history
# ─────────────────────────────────────────────────────────────

def test_customer_transactions(client, owner_headers, test_store, test_product):
    c = _create_customer(test_store.store_id, mobile="9500000001")
    _make_txn(test_store.store_id, c.customer_id, test_product, price=50.0)
    _make_txn(test_store.store_id, c.customer_id, test_product, price=80.0)

    resp = client.get(f'/api/v1/customers/{c.customer_id}/transactions',
                      headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['meta']['total'] == 2


# ─────────────────────────────────────────────────────────────
# 6. Customer summary – basic
# ─────────────────────────────────────────────────────────────

def test_customer_summary_basic(client, owner_headers, test_store, test_product):
    c = _create_customer(test_store.store_id, mobile="9600000001")
    _make_txn(test_store.store_id, c.customer_id, test_product, qty=1.0, price=100.0)
    _make_txn(test_store.store_id, c.customer_id, test_product, qty=2.0, price=100.0)

    resp = client.get(f'/api/v1/customers/{c.customer_id}/summary',
                      headers=owner_headers)
    assert resp.status_code == 200
    d = resp.json['data']

    # 1*100 + 2*100 = 300 total spend
    assert d['total_lifetime_spend'] == pytest.approx(300.0)
    assert d['visit_count'] == 2
    assert d['avg_basket_size'] == pytest.approx(150.0)
    assert d['last_visit_date'] is not None


# ─────────────────────────────────────────────────────────────
# 7. Repeat customer detection
#    is_repeat_customer = 3+ txns within ANY rolling 90-day window
# ─────────────────────────────────────────────────────────────

def test_not_repeat_customer_two_txns(client, owner_headers, test_store, test_product):
    c = _create_customer(test_store.store_id, mobile="9700000001")
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=5)
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=2)

    resp = client.get(f'/api/v1/customers/{c.customer_id}/summary',
                      headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['data']['is_repeat_customer'] is False


def test_repeat_customer_three_txns_in_window(client, owner_headers,
                                               test_store, test_product):
    c = _create_customer(test_store.store_id, mobile="9700000002")
    # Three transactions within 90 days
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=60)
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=30)
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=5)

    resp = client.get(f'/api/v1/customers/{c.customer_id}/summary',
                      headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['data']['is_repeat_customer'] is True


def test_repeat_customer_spread_over_multiple_windows(client, owner_headers,
                                                       test_store, test_product):
    """3 txns total but none within a 90-day window → NOT repeat."""
    c = _create_customer(test_store.store_id, mobile="9700000003")
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=200)
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=100)
    _make_txn(test_store.store_id, c.customer_id, test_product, days_ago=5)

    resp = client.get(f'/api/v1/customers/{c.customer_id}/summary',
                      headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json['data']['is_repeat_customer'] is False


# ─────────────────────────────────────────────────────────────
# 8. Top customers endpoint
# ─────────────────────────────────────────────────────────────

def test_top_customers_revenue(client, owner_headers, test_store, test_product):
    c1 = _create_customer(test_store.store_id, name="Big Spender", mobile="9800000001")
    c2 = _create_customer(test_store.store_id, name="Small Spender", mobile="9800000002")

    _make_txn(test_store.store_id, c1.customer_id, test_product, price=500.0)
    _make_txn(test_store.store_id, c2.customer_id, test_product, price=50.0)

    resp = client.get('/api/v1/customers/top?metric=revenue&limit=5',
                      headers=owner_headers)
    assert resp.status_code == 200
    top_ids = [r['customer_id'] for r in resp.json['data']]
    assert c1.customer_id in top_ids
    # Big Spender should come first
    assert top_ids.index(c1.customer_id) < top_ids.index(c2.customer_id)


def test_top_customers_visits(client, owner_headers, test_store, test_product):
    c1 = _create_customer(test_store.store_id, name="Frequent Visitor", mobile="9800000003")
    c2 = _create_customer(test_store.store_id, name="Rare Visitor",     mobile="9800000004")

    for _ in range(3):
        _make_txn(test_store.store_id, c1.customer_id, test_product, price=10.0)
    _make_txn(test_store.store_id, c2.customer_id, test_product, price=1000.0)

    resp = client.get('/api/v1/customers/top?metric=visits&limit=5',
                      headers=owner_headers)
    assert resp.status_code == 200
    top_ids = [r['customer_id'] for r in resp.json['data']]
    assert c1.customer_id in top_ids
    assert top_ids.index(c1.customer_id) < top_ids.index(c2.customer_id)


# ─────────────────────────────────────────────────────────────
# 9. Analytics endpoint
# ─────────────────────────────────────────────────────────────

def test_analytics_new_customer(client, owner_headers, test_store, test_product):
    """A customer with only a purchase this month should count as new."""
    c = _create_customer(test_store.store_id, mobile="9900000001")
    _make_txn(test_store.store_id, c.customer_id, test_product,
              days_ago=0, price=100.0)

    resp = client.get('/api/v1/customers/analytics', headers=owner_headers)
    assert resp.status_code == 200
    d = resp.json['data']
    assert d['new_customers'] >= 1
    assert d['unique_customers_month'] >= 1
    assert d['new_revenue'] >= 100.0


def test_analytics_repeat_customer(client, owner_headers, test_store, test_product):
    """A customer with a prior purchase + one this month should count as repeat."""
    c = _create_customer(test_store.store_id, mobile="9900000002")
    # Prior purchase definitively outside this month (60 days ago)
    _make_txn(test_store.store_id, c.customer_id, test_product,
              days_ago=60, price=80.0)
    # This month purchase — use days_ago=0 (today) to avoid month-boundary ambiguity
    _make_txn(test_store.store_id, c.customer_id, test_product,
              days_ago=0, price=120.0)

    resp = client.get('/api/v1/customers/analytics', headers=owner_headers)
    assert resp.status_code == 200
    d = resp.json['data']
    assert d['repeat_customers'] >= 1
    assert d['repeat_revenue'] >= 120.0


def test_analytics_repeat_rate(client, owner_headers, test_store, test_product):
    """repeat_rate_pct = repeat_customers / unique_customers_month * 100."""
    c_new = _create_customer(test_store.store_id, mobile="9900000003")
    c_rep = _create_customer(test_store.store_id, mobile="9900000004")

    _make_txn(test_store.store_id, c_new.customer_id, test_product, days_ago=0)
    _make_txn(test_store.store_id, c_rep.customer_id, test_product, days_ago=40)
    _make_txn(test_store.store_id, c_rep.customer_id, test_product, days_ago=0)

    resp = client.get('/api/v1/customers/analytics', headers=owner_headers)
    assert resp.status_code == 200
    d = resp.json['data']
    # At least one repeat customer out of these two buyers → rate > 0
    assert d['repeat_rate_pct'] > 0


# ─────────────────────────────────────────────────────────────
# 10. Auth guard
# ─────────────────────────────────────────────────────────────

def test_unauthenticated_returns_401(client):
    resp = client.get('/api/v1/customers')
    assert resp.status_code == 401
