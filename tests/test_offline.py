import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import AnalyticsSnapshot, DailySkuSummary, DailyStoreSummary, Product
from app.offline.builder import build_snapshot


@pytest.fixture(autouse=True)
def mock_celery_task_session(monkeypatch):
    @contextmanager
    def mock_session(*args, **kwargs):
        yield db.session

    monkeypatch.setattr("app.tasks.tasks.task_session", mock_session)


def test_snapshot_builder_structure(app, test_store):
    with app.app_context():
        store_id = test_store.store_id
        snapshot = build_snapshot(store_id, db)

        # Verify required top-level keys
        assert "kpis" in snapshot
        assert "revenue_30d" in snapshot
        assert "top_products_7d" in snapshot
        assert "alerts_open" in snapshot
        assert "low_stock_products" in snapshot
        assert "built_at" in snapshot

        # specific subkeys
        assert "today_revenue" in snapshot["kpis"]
        assert "today_profit" in snapshot["kpis"]
        assert "today_transactions" in snapshot["kpis"]
        assert "yesterday_revenue" in snapshot["kpis"]
        assert "this_week_revenue" in snapshot["kpis"]
        assert "this_month_revenue" in snapshot["kpis"]


def test_snapshot_size_enforcement(app, test_store):
    with app.app_context():
        store_id = test_store.store_id
        today = datetime.now(timezone.utc).date()

        # Seed 40 days of history and many products to force a 50KB overflow
        # Actually it takes a LOT of products to hit 50KB.
        # Let's mock a very large dataset directly into the builder's loop return

        # Instead of injecting 500 fake records into sqlite (which is slow),
        # we can just run the builder on an empty store, and manipulate the 50KB check artificially
        # or we can insert exactly 40 days and see if it clips to 14.

        for i in range(40):
            dss = DailyStoreSummary(
                store_id=store_id,
                date=today - timedelta(days=i),
                revenue=1000.55 * (i + 1),
                profit=300.22,
                transaction_count=50,
            )
            db.session.add(dss)

        category_id = 1
        for i in range(500):
            p = Product(
                store_id=store_id,
                category_id=category_id,
                name=f"Super Long Tiring Testing Product Name {i}" * 5,
                sku_code=f"SKU-{i}",
                barcode=f"1000{i}",
                cost_price=10.0,
                selling_price=20.0,
                current_stock=2,
                reorder_level=10,
            )
            db.session.add(p)

        db.session.commit()

        snapshot = build_snapshot(store_id, db)

        serialized = json.dumps(snapshot)
        assert len(serialized.encode("utf-8")) <= 51200  # 50 KB strict allowance


def test_snapshot_endpoint_returns_202_when_missing(client, owner_headers):
    # Get standard missing store without any snapshots
    resp = client.get("/api/v1/offline/snapshot", headers=owner_headers)
    assert resp.status_code == 202
    assert resp.json["error"]["message"] == "Snapshot is currently building"


def test_snapshot_endpoint_returns_200_after_task(app, client, owner_headers, test_store):
    # Run task
    with app.app_context():
        from app.tasks.tasks import build_analytics_snapshot

        build_analytics_snapshot(test_store.store_id)

    # hit API
    resp = client.get("/api/v1/offline/snapshot", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert "built_at" in resp.json["data"]
    assert "size_bytes" in resp.json["data"]
    assert "snapshot" in resp.json["data"]
    assert "kpis" in resp.json["data"]["snapshot"]


def test_snapshot_upsert_idempotent(app, test_store):
    with app.app_context():
        store_id = test_store.store_id
        from app.tasks.tasks import build_analytics_snapshot

        build_analytics_snapshot(store_id)
        db.session.expire_all()
        count1 = db.session.query(AnalyticsSnapshot).filter_by(store_id=store_id).count()
        assert count1 == 1

        build_analytics_snapshot(store_id)
        db.session.expire_all()
        count2 = db.session.query(AnalyticsSnapshot).filter_by(store_id=store_id).count()
        assert count2 == 1
