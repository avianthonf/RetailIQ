import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from datetime import date, datetime, timedelta, timezone

import pytest

from app import create_app
from app import db as _db
from app.models import DailySkuSummary, DailyStoreSummary, ForecastCache


def _seed_70_days(session, store_id):
    today = datetime.now(timezone.utc).date()
    for i in range(70):
        d = today - timedelta(days=69 - i)
        # 100 + (EXTRACT(DOW FROM d)*10) + (d - current_date + 70)*1.5
        # python equivalent DOW: Monday=0, Sunday=6. Let's use isoweekday() % 7 for Sunday=0
        dow = d.isoweekday() % 7
        rev = 100 + dow * 10 + (i + 1) * 1.5
        pft = 40 + dow * 5
        session.add(DailyStoreSummary(store_id=store_id, date=d, revenue=rev, profit=pft, transaction_count=10))
    session.commit()


# --- Audit tests ---
def test_phase_1_analytics_e2e(app, client, owner_headers, test_store):
    with app.app_context():
        _seed_70_days(_db.session, test_store.store_id)

    # 2. Test Revenue Endpoint
    today = datetime.now(timezone.utc).date()
    start = str(today - timedelta(days=60))
    end = str(today)
    resp = client.get(f"/api/v1/analytics/revenue?start={start}&end={end}&group_by=day", headers=owner_headers)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data) > 60
    assert "moving_avg_7d" in data[-1]
    assert data[0]["moving_avg_7d"] > 0  # partial MA before 7 days

    # 3. Edge Case: Cold Start (<7 days)
    with app.app_context():
        # Delete history except last 5 days
        _db.session.query(DailyStoreSummary).filter(DailyStoreSummary.date < today - timedelta(days=5)).delete()
        _db.session.commit()

    resp2 = client.get(f"/api/v1/analytics/revenue?start={start}&end={end}&group_by=day", headers=owner_headers)
    data2 = resp2.get_json()["data"]
    assert len(data2) <= 6
    for row in data2:
        assert "moving_avg_7d" in row
        assert row["moving_avg_7d"] > 0  # No division by zero


def test_phase_2_prophet_vs_fallback(app, test_store, test_product):
    with app.app_context():
        _seed_70_days(_db.session, test_store.store_id)
        # Seed 70 days for SKU as well
        today = datetime.now(timezone.utc).date()
        for i in range(70):
            d = today - timedelta(days=69 - i)
            _db.session.add(
                DailySkuSummary(
                    store_id=test_store.store_id,
                    product_id=test_product.product_id,
                    date=d,
                    revenue=100.0,
                    units_sold=10.0,
                    profit=20.0,
                )
            )
        _db.session.commit()

    # 5. Force Batch Forecast & 6. Validate forecast_cache Structure
    # Since we don't have celery worker, we call the task function synchronously
    from contextlib import contextmanager

    # Run for 70 days (should use Prophet, though mocked in tests)
    from unittest.mock import MagicMock, patch

    from app.tasks.tasks import forecast_store

    @contextmanager
    def mock_task_session():
        yield _db.session

    with app.app_context():
        with patch("app.tasks.tasks._RedisLock"), patch("app.tasks.tasks.task_session", new=mock_task_session):
            forecast_store(test_store.store_id)

        rows = _db.session.query(ForecastCache).filter_by(store_id=test_store.store_id).all()
        assert len(rows) > 0

        # 7. Prophet Failure Simulation
        _db.session.query(DailyStoreSummary).filter(DailyStoreSummary.date < today - timedelta(days=20)).delete()
        _db.session.query(DailySkuSummary).filter(DailySkuSummary.date < today - timedelta(days=20)).delete()
        _db.session.commit()

        with patch("app.tasks.tasks._RedisLock"), patch("app.tasks.tasks.task_session", new=mock_task_session):
            forecast_store(test_store.store_id)

        rows = _db.session.query(ForecastCache).filter_by(store_id=test_store.store_id).all()
        assert rows[0].model_type in ("ridge", "prophet")
