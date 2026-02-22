import pytest
from datetime import datetime, date, timezone
from unittest.mock import patch
import json

from app.tasks.tasks import (
    rebuild_daily_aggregates,
    evaluate_alerts,
    detect_slow_movers,
)
from app.models import Transaction, TransactionItem, Product, Alert, DailyStoreSummary
from app import db
import uuid

# Mocks
@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    class MockRedisLock:
        def __init__(self, key, ttl=900):
            self.acquired = True
            
        def __enter__(self):
            return self.acquired
            
        def __exit__(self, *_):
            pass
    monkeypatch.setattr('app.tasks.tasks._RedisLock', MockRedisLock)

    import contextlib
    @contextlib.contextmanager
    def mock_task_session(isolation_level=None):
        from app import db
        try:
            yield db.session
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    
    monkeypatch.setattr('app.tasks.tasks.task_session', mock_task_session)

def _create_transaction(store_id, items, dt):
    txn_id = uuid.uuid4()
    txn = Transaction(
        transaction_id=txn_id,
        store_id=store_id,
        payment_mode="CASH",
        created_at=dt,
        is_return=False,
    )
    db.session.add(txn)
    for prod_id, qty, price, disc in items:
        ti = TransactionItem(
            transaction_id=txn_id,
            product_id=prod_id,
            quantity=qty,
            selling_price=price,
            original_price=price,
            discount_amount=disc,
            cost_price_at_time=price-10
        )
        db.session.add(ti)
    db.session.commit()
    return txn

def test_rebuild_daily_aggregates_and_evaluate_alerts(app, test_store, test_product):
    # Base dt
    dt = datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc)
    date_str = dt.strftime('%Y-%m-%d')
    date_obj = dt.date()

    _create_transaction(test_store.store_id, [(test_product.product_id, 2, 100.0, 0)], dt)

    # Rebuild twice to check idempotency and correctness
    for _ in range(2):
        rebuild_daily_aggregates(test_store.store_id, date_str)

    summary = db.session.query(DailyStoreSummary).filter_by(
        store_id=test_store.store_id, date=date_obj
    ).first()

    assert summary is not None
    assert summary.revenue == 200.0
    assert summary.units_sold == 2.0

    # Test Evaluate alerts - Low stock
    test_product.current_stock = 0
    test_product.reorder_level = 10
    db.session.commit()

    # Evaluate multiple times for deduplication checks
    for _ in range(3):
        evaluate_alerts(test_store.store_id)

    alerts = db.session.query(Alert).filter_by(
        store_id=test_store.store_id, alert_type="LOW_STOCK"
    ).all()
    # Deduplication should keep it at 1
    assert len(alerts) == 1
    assert alerts[0].product_id == test_product.product_id

    # Test Slow Movers
    detect_slow_movers()
    detect_slow_movers() # another call to verify idempotency 
