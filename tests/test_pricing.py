"""
Comprehensive tests for the Pricing blueprint (engine + API routes + Celery task).

Uses the shared in-memory SQLite conftest fixtures (app, client, test_store, test_owner,
owner_headers, test_product, test_category).
"""
import contextlib
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import db
from app.models import (
    DailySkuSummary,
    DailyStoreSummary,
    PricingRule,
    PricingSuggestion,
    Product,
    ProductPriceHistory,
)
from app.pricing.engine import generate_price_suggestions

# ────────────────────────────────────────────────────────────────────────────
# Helper: mock Redis lock & task_session so Celery tasks run in-process
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_task_infra(monkeypatch):
    """Bypass Redis lock and Celery task-session in all pricing tests."""
    class _MockLock:
        def __init__(self, key, ttl=900):
            self.acquired = True
        def __enter__(self):
            return self.acquired
        def __exit__(self, *_):
            pass

    monkeypatch.setattr('app.tasks.tasks._RedisLock', _MockLock)

    @contextlib.contextmanager
    def _mock_session(isolation_level=None):
        try:
            yield db.session
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    monkeypatch.setattr('app.tasks.tasks.task_session', _mock_session)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _seed_sku_history(store_id, product_id, n_days, units_per_day, avg_price):
    """Seed n_days of daily_sku_summary rows (most recent = today - 1)."""
    today = date.today()
    for i in range(n_days, 0, -1):
        d = today - timedelta(days=i)
        row = DailySkuSummary(
            date=d,
            store_id=store_id,
            product_id=product_id,
            units_sold=units_per_day,
            avg_selling_price=avg_price,
            revenue=units_per_day * avg_price,
            profit=units_per_day * (avg_price - avg_price * 0.5),
        )
        db.session.add(row)
    db.session.commit()


def _seed_store_summary(store_id, n_days, revenue_per_day=500.0):
    """Seed daily_store_summary so the anomaly check sees active store."""
    today = date.today()
    for i in range(n_days, 0, -1):
        d = today - timedelta(days=i)
        row = DailyStoreSummary(
            date=d,
            store_id=store_id,
            revenue=revenue_per_day,
            profit=revenue_per_day * 0.3,
            transaction_count=5,
            avg_basket=revenue_per_day / 5,
            units_sold=20.0,
        )
        db.session.add(row)
    db.session.commit()


def _make_pending_suggestion(store_id, product_id, created_at=None):
    """Create a PENDING pricing suggestion directly in the DB."""
    s = PricingSuggestion(
        product_id=product_id,
        store_id=store_id,
        suggested_price=105.0,
        current_price=100.0,
        price_change_pct=5.0,
        reason="Test suggestion",
        confidence="MEDIUM",
        status="PENDING",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.session.add(s)
    db.session.commit()
    return s


# ════════════════════════════════════════════════════════════════════════════
# 1. test_low_margin_raises_suggestion
# ════════════════════════════════════════════════════════════════════════════

def test_low_margin_raises_suggestion(app, test_store, test_category):
    """Product with 10% margin and inelastic demand should get a RAISE suggestion."""
    # margin = (selling - cost) / selling = (110 - 99) / 110 ≈ 10%
    product = Product(
        store_id=test_store.store_id,
        category_id=test_category.category_id,
        name="Low Margin Product",
        selling_price=110.0,
        cost_price=99.0,
        current_stock=50.0,
        is_active=True,
    )
    db.session.add(product)
    db.session.commit()

    # Seed 35 days of history where units are HIGH regardless of price
    # (inelastic demand: price above/below median doesn't matter for units_sold)
    # To get elasticity_proxy > -0.3, we need corr(above_median_flag, units) > -0.3
    # Seeding constant units_sold=5 and constant price → corr is 0 (undefined → None)
    # Use a non-constant series: alternate high/low price with constant units
    today = date.today()
    for i in range(35, 0, -1):
        d = today - timedelta(days=i)
        # Alternating price above/below median (110) but constant units → corr ≈ 0
        price = 115.0 if i % 2 == 0 else 105.0
        row = DailySkuSummary(
            date=d, store_id=test_store.store_id, product_id=product.product_id,
            units_sold=5.0, avg_selling_price=price,
            revenue=5 * price, profit=5 * (price - 99),
        )
        db.session.add(row)
    db.session.commit()

    suggestions = generate_price_suggestions(test_store.store_id, db.session)

    assert len(suggestions) >= 1
    raise_sg = next(
        (s for s in suggestions
         if s['product_id'] == product.product_id and s['suggestion_type'] == 'RAISE'),
        None
    )
    assert raise_sg is not None, "Expected RAISE suggestion for low-margin product"
    assert raise_sg['suggested_price'] > raise_sg['current_price']


# ════════════════════════════════════════════════════════════════════════════
# 2. test_zero_velocity_with_high_margin_lowers_suggestion
# ════════════════════════════════════════════════════════════════════════════

def test_zero_velocity_with_high_margin_lowers_suggestion(app, test_store, test_category):
    """Product with 40% margin and 0 sales in last 14 days → LOWER suggestion."""
    # margin = (200 - 120) / 200 = 40%
    product = Product(
        store_id=test_store.store_id,
        category_id=test_category.category_id,
        name="Zero Velocity Product",
        selling_price=200.0,
        cost_price=120.0,
        current_stock=30.0,
        is_active=True,
    )
    db.session.add(product)
    db.session.commit()

    # Seed 36 days of history: sales from 50 to 15 days ago, zero in last 14 days
    today = date.today()
    for i in range(50, 14, -1):
        d = today - timedelta(days=i)
        row = DailySkuSummary(
            date=d, store_id=test_store.store_id, product_id=product.product_id,
            units_sold=3.0, avg_selling_price=200.0,
            revenue=600.0, profit=240.0,
        )
        db.session.add(row)
    # Last 14 days: zero sales (no rows → sum = 0)
    db.session.commit()

    # Seed store summary so anomaly check doesn't trigger
    _seed_store_summary(test_store.store_id, 20)

    suggestions = generate_price_suggestions(test_store.store_id, db.session)

    lower_sg = next(
        (s for s in suggestions
         if s['product_id'] == product.product_id and s['suggestion_type'] == 'LOWER'),
        None
    )
    assert lower_sg is not None, "Expected LOWER suggestion for zero-velocity high-margin product"
    assert lower_sg['suggested_price'] < lower_sg['current_price']


# ════════════════════════════════════════════════════════════════════════════
# 3. test_apply_suggestion_updates_price
# ════════════════════════════════════════════════════════════════════════════

def test_apply_suggestion_updates_price(app, client, test_store, test_owner,
                                         test_product, owner_headers):
    """Apply a suggestion: products.selling_price updated + price_history row created."""
    suggestion = _make_pending_suggestion(
        test_store.store_id, test_product.product_id
    )

    resp = client.post(
        f"/api/v1/pricing/suggestions/{suggestion.id}/apply",
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["status"] == "APPLIED"
    assert data["new_price"] == 105.0

    # Verify product price updated in DB
    db.session.expire_all()
    product = db.session.query(Product).filter_by(
        product_id=test_product.product_id
    ).first()
    assert float(product.selling_price) == 105.0

    # Verify price history row created
    history = db.session.query(ProductPriceHistory).filter_by(
        product_id=test_product.product_id
    ).first()
    assert history is not None
    assert float(history.new_price) == 105.0
    assert history.store_id == test_store.store_id


# ════════════════════════════════════════════════════════════════════════════
# 4. test_apply_suggestion_idempotent
# ════════════════════════════════════════════════════════════════════════════

def test_apply_suggestion_idempotent(app, client, test_store, test_owner,
                                      test_product, owner_headers):
    """Applying an already-applied suggestion returns 409."""
    suggestion = _make_pending_suggestion(
        test_store.store_id, test_product.product_id
    )

    resp1 = client.post(
        f"/api/v1/pricing/suggestions/{suggestion.id}/apply",
        headers=owner_headers,
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        f"/api/v1/pricing/suggestions/{suggestion.id}/apply",
        headers=owner_headers,
    )
    assert resp2.status_code == 409
    err = resp2.get_json()["error"]
    assert err["code"] == "ALREADY_ACTIONED"


# ════════════════════════════════════════════════════════════════════════════
# 5. test_dismiss_suggestion
# ════════════════════════════════════════════════════════════════════════════

def test_dismiss_suggestion(app, client, test_store, test_owner,
                             test_product, owner_headers):
    """Dismissing a PENDING suggestion marks it DISMISSED."""
    suggestion = _make_pending_suggestion(
        test_store.store_id, test_product.product_id
    )

    resp = client.post(
        f"/api/v1/pricing/suggestions/{suggestion.id}/dismiss",
        headers=owner_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["status"] == "DISMISSED"

    # Verify DB state
    db.session.expire_all()
    s = db.session.query(PricingSuggestion).filter_by(id=suggestion.id).first()
    assert s.status == "DISMISSED"
    assert s.actioned_at is not None

    # Second dismiss should return 409
    resp2 = client.post(
        f"/api/v1/pricing/suggestions/{suggestion.id}/dismiss",
        headers=owner_headers,
    )
    assert resp2.status_code == 409


# ════════════════════════════════════════════════════════════════════════════
# 6. test_weekly_task_skips_recent_suggestion
# ════════════════════════════════════════════════════════════════════════════

def test_weekly_task_skips_recent_suggestion(app, test_store, test_category):
    """
    If a PENDING suggestion for a product exists from 3 days ago,
    the weekly task should NOT create a duplicate.
    """
    from app.tasks.tasks import run_weekly_pricing_analysis

    # Low-margin product that would qualify for a RAISE suggestion
    product = Product(
        store_id=test_store.store_id,
        category_id=test_category.category_id,
        name="Recent Suggestion Product",
        selling_price=110.0,
        cost_price=99.0,  # 10% margin
        current_stock=50.0,
        is_active=True,
    )
    db.session.add(product)
    db.session.commit()

    # Seed 35 days for qualifying history
    today = date.today()
    for i in range(35, 0, -1):
        d = today - timedelta(days=i)
        price = 115.0 if i % 2 == 0 else 105.0
        row = DailySkuSummary(
            date=d, store_id=test_store.store_id, product_id=product.product_id,
            units_sold=5.0, avg_selling_price=price,
            revenue=5 * price, profit=5 * (price - 99),
        )
        db.session.add(row)
    db.session.commit()

    # Pre-seed a PENDING suggestion from 3 days ago
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    _make_pending_suggestion(
        test_store.store_id, product.product_id, created_at=three_days_ago
    )

    count_before = db.session.query(PricingSuggestion).filter_by(
        product_id=product.product_id, status="PENDING"
    ).count()

    # Run the weekly task
    run_weekly_pricing_analysis()

    count_after = db.session.query(PricingSuggestion).filter_by(
        product_id=product.product_id, status="PENDING"
    ).count()

    assert count_after == count_before, (
        f"Weekly task should not have created a duplicate suggestion; "
        f"before={count_before}, after={count_after}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 7. Additional API coverage: list suggestions + price history + rules
# ════════════════════════════════════════════════════════════════════════════

def test_list_suggestions_returns_pending(app, client, test_store, test_owner,
                                           test_product, owner_headers):
    """GET /api/v1/pricing/suggestions returns PENDING suggestions for the store."""
    _make_pending_suggestion(test_store.store_id, test_product.product_id)

    resp = client.get("/api/v1/pricing/suggestions", headers=owner_headers)
    assert resp.status_code == 200
    items = resp.get_json()["data"]
    assert len(items) >= 1
    assert items[0]["status"] == "PENDING"
    assert "suggested_price" in items[0]
    assert "current_margin_pct" in items[0]


def test_price_history_endpoint(app, client, test_store, test_owner,
                                 test_product, owner_headers):
    """GET /api/v1/pricing/history returns price history for a given product."""
    history = ProductPriceHistory(
        product_id=test_product.product_id,
        store_id=test_store.store_id,
        old_price=90.0,
        new_price=100.0,
        reason="manual_update",
        changed_by=test_owner.user_id,
    )
    db.session.add(history)
    db.session.commit()

    resp = client.get(
        f"/api/v1/pricing/history?product_id={test_product.product_id}",
        headers=owner_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data) >= 1
    assert data[0]["old_price"] == 90.0
    assert data[0]["new_price"] == 100.0


def test_pricing_rules_crud(app, client, test_store, test_owner, owner_headers):
    """PUT then GET /api/v1/pricing/rules persists a rule."""
    payload = {
        "rule_type": "MIN_MARGIN",
        "parameters": {"min_margin_pct": 15},
        "is_active": True,
    }
    resp = client.put(
        "/api/v1/pricing/rules",
        json=payload,
        headers=owner_headers,
    )
    assert resp.status_code == 200
    rule_data = resp.get_json()["data"]
    assert rule_data["rule_type"] == "MIN_MARGIN"

    # GET should now return it
    resp2 = client.get("/api/v1/pricing/rules", headers=owner_headers)
    assert resp2.status_code == 200
    rules = resp2.get_json()["data"]
    assert any(r["rule_type"] == "MIN_MARGIN" for r in rules)
