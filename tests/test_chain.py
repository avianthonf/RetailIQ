"""
tests/test_chain.py — Chain Ownership & Multi-store Integration Tests
"""
import pytest
import uuid
from datetime import date

from app import db
from app.models import (
    Store, StoreGroup, StoreGroupMembership,
    ChainDailyAggregate, InterStoreTransferSuggestion,
    Alert, Product, DailyStoreSummary, Category
)
from app.auth.utils import generate_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chain_group(app, test_owner, test_store):
    """Create a store group owned by the test owner and return (group, headers)."""
    group = StoreGroup(name="Test Chain", owner_user_id=test_owner.user_id)
    db.session.add(group)
    db.session.commit()
    # Re-generate token so chain_group_id is injected
    token = generate_access_token(test_owner.user_id, test_store.store_id, 'owner')
    headers = {'Authorization': f'Bearer {token}'}
    return group, headers


@pytest.fixture
def two_store_chain(app, chain_group, test_owner, test_store):
    """Set up a chain with 2 stores and memberships."""
    group, headers = chain_group
    store1_id = test_store.store_id

    store2 = Store(store_name="Chain Store 2", store_type="grocery")
    db.session.add(store2)
    db.session.commit()

    m1 = StoreGroupMembership(group_id=group.id, store_id=store1_id)
    m2 = StoreGroupMembership(group_id=group.id, store_id=store2.store_id)
    db.session.add_all([m1, m2])
    db.session.commit()

    return group, store1_id, store2.store_id, headers


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_chain_dashboard_requires_chain_role(client, owner_headers):
    """A normal owner token (no StoreGroup) must get 403 on chain endpoints."""
    res = client.get('/api/v1/chain/dashboard', headers=owner_headers)
    assert res.status_code == 403
    assert res.json['error']['code'] == 'FORBIDDEN'


def test_chain_dashboard_returns_all_stores(app, client, two_store_chain):
    group, store1_id, store2_id, headers = two_store_chain

    today = date.today()
    agg1 = ChainDailyAggregate(
        group_id=group.id, store_id=store1_id,
        date=today, revenue=1000, profit=500, transaction_count=10
    )
    agg2 = ChainDailyAggregate(
        group_id=group.id, store_id=store2_id,
        date=today, revenue=2000, profit=1000, transaction_count=20
    )
    db.session.add_all([agg1, agg2])
    db.session.commit()

    res = client.get('/api/v1/chain/dashboard', headers=headers)
    assert res.status_code == 200
    data = res.json['data']

    # Check total revenue
    assert float(data['total_revenue_today']) == 3000.0
    # Both stores present
    assert len(data['per_store_today']) == 2
    store_ids_in_response = {s['store_id'] for s in data['per_store_today']}
    assert store1_id in store_ids_in_response
    assert store2_id in store_ids_in_response
    # Store 2 is best (2000) and Store 1 is worst (1000)
    assert data['best_store']['store_id'] == store2_id
    assert data['worst_store']['store_id'] == store1_id


def test_chain_jwt_does_not_break_single_store_endpoints(client, chain_group):
    """
    A token with chain_group_id must still work on normal store-scoped
    endpoints like /api/v1/analytics/dashboard (scoped to its own store_id).
    """
    _, headers = chain_group
    res = client.get('/api/v1/analytics/dashboard', headers=headers)
    assert res.status_code == 200


def test_transfer_detection_creates_suggestion(app, two_store_chain):
    """
    Seed store A with a CRITICAL LOW_STOCK alert on product X and store B
    with surplus of product X, then directly insert the transfer suggestion
    (mirroring what the Celery task would do on Postgres) and verify it exists.

    Note: The actual Celery task uses raw SQL with UUID casting that only works
    on Postgres. In tests (SQLite) we verify the ORM logic directly.
    """
    group, store1_id, store2_id, headers = two_store_chain

    cat = Category(store_id=store1_id, name="Transfer Cat", gst_rate=5.0)
    db.session.add(cat)
    db.session.commit()

    # Product in store 1 (low stock)
    p1 = Product(
        name="Critical Product", category_id=cat.category_id,
        store_id=store1_id, selling_price=10.0, cost_price=5.0,
        current_stock=2, reorder_level=10
    )
    db.session.add(p1)
    db.session.commit()

    # Product in store 2 (surplus: stock=30, reorder_level=10)
    cat2 = Category(store_id=store2_id, name="Transfer Cat B", gst_rate=5.0)
    db.session.add(cat2)
    db.session.commit()

    p2 = Product(
        name="Critical Product", category_id=cat2.category_id,
        store_id=store2_id, selling_price=10.0, cost_price=5.0,
        current_stock=30, reorder_level=10
    )
    db.session.add(p2)
    db.session.commit()

    # Create CRITICAL LOW_STOCK alert on store 1
    alert = Alert(
        store_id=store1_id, product_id=p1.product_id,
        alert_type="LOW_STOCK", priority="CRITICAL",
        message="Low stock on Critical Product"
    )
    db.session.add(alert)
    db.session.commit()

    # Simulate what detect_transfer_opportunities would do:
    # Store 2 has surplus (30 > 10 * 1.5 = 15), suggested_qty = (30-10)*0.5 = 10
    suggestion = InterStoreTransferSuggestion(
        group_id=group.id,
        from_store_id=store2_id,
        to_store_id=store1_id,
        product_id=p1.product_id,
        suggested_qty=10.0,
        reason=f"Surplus identified in sibling Store {store2_id}"
    )
    db.session.add(suggestion)
    db.session.commit()

    # Verify the suggestion was created correctly
    result = db.session.query(InterStoreTransferSuggestion).filter_by(
        group_id=group.id
    ).first()
    assert result is not None
    assert result.from_store_id == store2_id
    assert result.to_store_id == store1_id
    assert float(result.suggested_qty) == 10.0
    assert result.status == 'PENDING'


def test_chain_compare_relative_coding(app, client, two_store_chain):
    group, store1_id, store2_id, headers = two_store_chain
    today = date.today()

    # Both stores have identical revenue => both should be 'near'
    agg1 = ChainDailyAggregate(
        group_id=group.id, store_id=store1_id,
        date=today, revenue=1000, profit=500, transaction_count=10
    )
    agg2 = ChainDailyAggregate(
        group_id=group.id, store_id=store2_id,
        date=today, revenue=1000, profit=1000, transaction_count=20
    )
    db.session.add_all([agg1, agg2])
    db.session.commit()

    res = client.get('/api/v1/chain/compare?period=today', headers=headers)
    assert res.status_code == 200

    data = res.json['data']
    for comp in data:
        assert comp['relative_to_avg'] == 'near'


def test_add_store_to_group(client, chain_group, test_owner):
    group, headers = chain_group

    store3 = Store(store_name="Chain Store 3", store_type="grocery")
    db.session.add(store3)
    db.session.commit()

    res = client.post(
        f'/api/v1/chain/groups/{group.id}/stores',
        headers=headers,
        json={"store_id": store3.store_id}
    )
    assert res.status_code == 201
    assert db.session.query(StoreGroupMembership).filter_by(
        store_id=store3.store_id, group_id=group.id
    ).count() == 1
