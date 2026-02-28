import pytest
from app import db
from app.models import (
    LoyaltyProgram, CustomerLoyaltyAccount, LoyaltyTransaction,
    CreditLedger, CreditTransaction, Customer, Transaction, TransactionItem
)
from app.transactions.services import process_single_transaction
import uuid
from datetime import datetime, timezone, timedelta

@pytest.fixture
def mock_celery_task_session(monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def mock_session(*args, **kwargs):
        yield db.session
        db.session.commit()
    monkeypatch.setattr('app.tasks.tasks.task_session', mock_session)

@pytest.fixture
def loyalty_customer_id(app, test_store):
    customer = Customer(store_id=test_store.store_id, mobile_number="9999999999", name="Loyalty Tester")
    db.session.add(customer)
    db.session.commit()
    db.session.refresh(customer)
    return customer.customer_id

@pytest.fixture
def loyalty_program_id(app, test_store):
    lp = LoyaltyProgram(store_id=test_store.store_id, points_per_rupee=1.0, redemption_rate=0.1, min_redemption_points=100)
    db.session.add(lp)
    db.session.commit()
    return lp.id

# a. test_points_earned_on_transaction
def test_points_earned_on_transaction(app, test_store, test_product, loyalty_customer_id, loyalty_program_id):
    txn_data = {
        "transaction_id": uuid.uuid4(),
        "timestamp": datetime.now(timezone.utc),
        "payment_mode": "CASH",
        "customer_id": loyalty_customer_id,
        "line_items": [
            {"product_id": test_product.product_id, "quantity": 1, "selling_price": 150.0}
        ]
    }
    process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    # Check account
    acc = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=loyalty_customer_id).first()
    assert acc is not None
    assert float(acc.total_points) == 150.0
    
    # Check transaction
    ltx = db.session.query(LoyaltyTransaction).filter_by(account_id=acc.id).first()
    assert ltx is not None
    assert ltx.type == 'EARN'
    assert float(ltx.points) == 150.0

# b. test_points_accrual_is_atomic
def test_points_accrual_is_atomic(app, test_store, test_product, loyalty_customer_id, loyalty_program_id, monkeypatch):
    original_init = LoyaltyTransaction.__init__
    def failing_init(self, *args, **kwargs):
        raise ValueError("Simulated DB failure")

    monkeypatch.setattr(LoyaltyTransaction, '__init__', failing_init)

    txn_data = {
        "transaction_id": uuid.uuid4(),
        "timestamp": datetime.now(timezone.utc),
        "payment_mode": "CASH",
        "customer_id": loyalty_customer_id,
        "line_items": [
            {"product_id": test_product.product_id, "quantity": 1, "selling_price": 150.0}
        ]
    }

    with pytest.raises(ValueError, match="Simulated DB failure"):
        with db.session.begin_nested():
            process_single_transaction(txn_data, test_store.store_id)

    db.session.rollback()
    assert db.session.query(Transaction).count() == 0

# Redeem Tests (c, d)
def test_redeem_points_reduces_balance(client, owner_headers, test_store, loyalty_customer_id, loyalty_program_id):
    acc = CustomerLoyaltyAccount(customer_id=loyalty_customer_id, store_id=test_store.store_id, total_points=500, redeemable_points=500, lifetime_earned=500)
    db.session.add(acc)
    db.session.commit()
        
    resp = client.post(f"/api/v1/loyalty/customers/{loyalty_customer_id}/redeem", 
                       headers=owner_headers, json={"points_to_redeem": 200})
    assert resp.status_code == 200
    
    acc = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=loyalty_customer_id).first()
    assert float(acc.total_points) == 300.0
    assert float(acc.redeemable_points) == 300.0

def test_redeem_below_minimum_rejected(client, owner_headers, test_store, loyalty_customer_id, loyalty_program_id):
    acc = CustomerLoyaltyAccount(customer_id=loyalty_customer_id, store_id=test_store.store_id, total_points=500, redeemable_points=500, lifetime_earned=500)
    db.session.add(acc)
    db.session.commit()
    
    resp = client.post(f"/api/v1/loyalty/customers/{loyalty_customer_id}/redeem", 
                       headers=owner_headers, json={"points_to_redeem": 50})
    assert resp.status_code == 422
    assert "below minimum" in resp.json["error"]["message"].lower()

# Credit Sale Tests (e, f, g)
def test_credit_sale_increments_balance(app, test_store, test_product, loyalty_customer_id):
    ledger = CreditLedger(customer_id=loyalty_customer_id, store_id=test_store.store_id, credit_limit=1000)
    db.session.add(ledger)
    db.session.commit()
    
    txn_data = {
        "transaction_id": uuid.uuid4(),
        "timestamp": datetime.now(timezone.utc),
        "payment_mode": "CREDIT",
        "customer_id": loyalty_customer_id,
        "line_items": [
            {"product_id": test_product.product_id, "quantity": 1, "selling_price": 400.0}
        ]
    }
    process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()
    
    l = db.session.query(CreditLedger).filter_by(customer_id=loyalty_customer_id).first()
    assert float(l.balance) == 400.0
    
    ctx = db.session.query(CreditTransaction).filter_by(ledger_id=l.id).first()
    assert ctx.type == 'CREDIT_SALE'
    assert float(ctx.amount) == 400.0

def test_credit_sale_blocked_over_limit(app, test_store, test_product, loyalty_customer_id):
    ledger = CreditLedger(customer_id=loyalty_customer_id, store_id=test_store.store_id, credit_limit=500, balance=200)
    db.session.add(ledger)
    db.session.commit()
    
    txn_data = {
        "transaction_id": uuid.uuid4(),
        "timestamp": datetime.now(timezone.utc),
        "payment_mode": "CREDIT",
        "customer_id": loyalty_customer_id,
        "line_items": [
            {"product_id": test_product.product_id, "quantity": 1, "selling_price": 400.0}
        ]
    }
    
    with pytest.raises(ValueError, match="Credit limit"):
        process_single_transaction(txn_data, test_store.store_id)

def test_repayment_reduces_balance(client, owner_headers, test_store, loyalty_customer_id):
    ledger = CreditLedger(customer_id=loyalty_customer_id, store_id=test_store.store_id, credit_limit=1000, balance=500)
    db.session.add(ledger)
    db.session.commit()
        
    resp = client.post(f"/api/v1/credit/customers/{loyalty_customer_id}/repay",
                       headers=owner_headers, json={"amount": 200, "notes": "paid via upi"})
    assert resp.status_code == 200
    
    l = db.session.query(CreditLedger).filter_by(customer_id=loyalty_customer_id).first()
    assert float(l.balance) == 300.0

# Tasks Tests (h, i)
def test_overdue_credit_alert_task(app, test_store, loyalty_customer_id, mock_celery_task_session):
    from app.tasks.tasks import credit_overdue_alerts
    from app.models import Alert
    
    old_date = datetime.utcnow() - timedelta(days=35)
    ledger = CreditLedger(customer_id=loyalty_customer_id, store_id=test_store.store_id, balance=500, updated_at=old_date)
    db.session.add(ledger)
    db.session.commit()
    
    credit_overdue_alerts()
    
    alert = db.session.query(Alert).filter_by(store_id=test_store.store_id, alert_type="credit_overdue").first()
    assert alert is not None
    assert alert.priority == 'HIGH'

def test_points_expiry_task(app, test_store, loyalty_customer_id, loyalty_program_id, mock_celery_task_session):
    from app.tasks.tasks import expire_loyalty_points

    old_date = datetime.utcnow() - timedelta(days=400)  # Past 365 expiry
    acc = CustomerLoyaltyAccount(customer_id=loyalty_customer_id, store_id=test_store.store_id,
                                 total_points=500, redeemable_points=500, lifetime_earned=500,
                                 last_activity_at=old_date)
    db.session.add(acc)
    db.session.flush()
    db.session.commit()

    # Verify the program is_active flag is True before the task runs
    prog = db.session.query(LoyaltyProgram).filter_by(store_id=test_store.store_id).first()
    assert prog is not None
    assert prog.is_active is True

    expire_loyalty_points()

    db.session.expire_all()
    acc = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=loyalty_customer_id).first()
    assert acc is not None
    assert float(acc.redeemable_points) == 0.0
    assert float(acc.total_points) == 0.0

    ltx = db.session.query(LoyaltyTransaction).filter_by(account_id=acc.id, type='EXPIRE').first()
    assert ltx is not None
    assert float(ltx.points) == -500.0
