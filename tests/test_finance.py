import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import db
from app.models import Customer, DailyStoreSummary, Product, Store, User
from app.models.finance_models import (
    FinancialAccount,
    InsuranceClaim,
    InsurancePolicy,
    InsuranceProduct,
    LedgerEntry,
    LoanApplication,
    LoanProduct,
    MerchantCreditProfile,
)


@pytest.fixture
def seeded_finance(app, test_store):
    """Seed base financial products for testing."""
    with app.app_context():
        # 1. Loan Products
        term_loan = LoanProduct(
            name="Starter Term Loan",
            product_type="TERM_LOAN",
            min_amount=1000,
            max_amount=50000,
            interest_rate_bps=1200,  # 12%
            max_term_days=365
        )
        rev_advance = LoanProduct(
            name="Revenue Advance",
            product_type="REVENUE_ADVANCE",
            min_amount=500,
            max_amount=10000,
            interest_rate_bps=1500,  # 15%
            max_term_days=90
        )

        # 2. Insurance Products
        weather_ins = InsuranceProduct(
            name="Rainfall Protection",
            category="WEATHER",
            description="Pays out if rainfall exceeds 50mm",
            premium_monthly=500,
            max_coverage=10000
        )

        db.session.add_all([term_loan, rev_advance, weather_ins])
        db.session.commit()

        return {
            "term_loan_id": term_loan.id,
            "rev_advance_id": rev_advance.id,
            "weather_ins_id": weather_ins.id
        }


def test_kyc_flow(client, owner_headers):
    """Test the KYC submission and status flow."""
    # 1. Submit KYC
    resp = client.post("/api/v2/finance/kyc/submit", json={
        "business_type": "LLP",
        "tax_id": "ABCDE1234F",
        "document_urls": {"identity": "https://s3.com/id.jpg"}
    }, headers=owner_headers)
    assert resp.status_code == 201
    assert resp.json["status"] == "PENDING"

    # 2. Check status
    resp = client.get("/api/v2/finance/kyc/status", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["status"] == "PENDING"
    assert resp.json["tax_id"] == "ABCDE1234F"


def test_credit_scoring_logic(app, client, owner_headers, test_store):
    """Test credit score calculation and retrieval."""
    with app.app_context():
        # Seed some transaction history for the store
        for i in range(10):
            summary = DailyStoreSummary(
                store_id=test_store.store_id,
                date=datetime.now(timezone.utc).date() - timedelta(days=i),
                revenue=Decimal("1000.00"),
                profit=Decimal("200.00"),
                transaction_count=20
            )
            db.session.add(summary)
        db.session.commit()

    # 1. Get score
    resp = client.get("/api/v2/finance/credit-score", headers=owner_headers)
    assert resp.status_code == 200
    assert "score" in resp.json
    assert resp.json["score"] > 300

    # 2. Refresh score
    resp = client.post("/api/v2/finance/credit-score/refresh", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["score"] > 300


def test_ledger_double_entry(app, test_store):
    """Verify double-entry ledger consistency."""
    from app.finance.ledger import get_account_balance, record_transaction

    with app.app_context():
        # Record a payment (Revenue up, Operating up)
        record_transaction(
            store_id=test_store.store_id,
            debit_account_type="OPERATING",
            credit_account_type="REVENUE",
            amount=Decimal("100.00"),
            description="Test entry"
        )
        db.session.commit()

        # Check balances
        op_acc = db.session.query(FinancialAccount).filter_by(store_id=test_store.store_id, account_type="OPERATING").one()
        rev_acc = db.session.query(FinancialAccount).filter_by(store_id=test_store.store_id, account_type="REVENUE").one()

        assert op_acc.balance == Decimal("100.00")
        assert rev_acc.balance == Decimal("100.00")

        # Verify direct sum of entries matches
        assert get_account_balance(op_acc.id) == Decimal("100.00")
        assert get_account_balance(rev_acc.id) == Decimal("100.00")


def test_loan_lifecycle(app, client, owner_headers, seeded_finance):
    """Test applying, approving, disbursing, and repaying a loan."""
    # 1. Apply
    resp = client.post("/api/v2/finance/loans/apply", json={
        "product_id": seeded_finance["term_loan_id"],
        "amount": 5000,
        "term_days": 180
    }, headers=owner_headers)
    assert resp.status_code == 201
    loan_id = resp.json["application_id"]

    # 2. Approve (Admin-like internal action, using service directly)
    from app.finance.loan_engine import approve_loan
    with app.app_context():
        approve_loan(loan_id, Decimal("5000.00"))
        db.session.commit()

    # 3. Disburse
    resp = client.post(f"/api/v2/finance/loans/{loan_id}/disburse", headers=owner_headers)
    assert resp.status_code == 200

    # 4. Verify Account Balance
    resp = client.get("/api/v2/finance/accounts", headers=owner_headers)
    op_acc = next(a for a in resp.json if a["type"] == "OPERATING")
    assert op_acc["balance"] == 5000.00

    # 5. Check Dashboard
    resp = client.get("/api/v2/finance/dashboard", headers=owner_headers)
    assert resp.json["cash_on_hand"] == 5000.00
    assert resp.json["total_debt"] == 5000.00


def test_payment_processing(client, owner_headers):
    """Test card payment processing and fee deduction."""
    resp = client.post("/api/v2/finance/payments/process", json={
        "amount": 1000.00,
        "payment_method": "UPI"
    }, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["net_amount"] == 1000.00 - (1000.00 * 0.029 + 0.30)
    assert resp.json["fees"] == (1000.00 * 0.029 + 0.30)


def test_treasury_sweeps(app, client, owner_headers, test_store):
    """Test automated treasury sweeps."""
    # 1. Set config
    client.put("/api/v2/finance/treasury/sweep-config", json={
        "strategy": "BALANCED",
        "min_balance": 1000.00
    }, headers=owner_headers)

    from app.finance.ledger import record_transaction
    from app.finance.treasury_manager import perform_sweep

    with app.app_context():
        # 2. Give operating account 5000 in cash
        record_transaction(
            store_id=test_store.store_id,
            debit_account_type="OPERATING",
            credit_account_type="REVENUE",
            amount=Decimal("5000.00"),
            description="Initial seed"
        )
        db.session.commit()

        # 3. Perform sweep
        sweep_amount = perform_sweep(test_store.store_id)
        assert sweep_amount == Decimal("4000.00")
        db.session.commit()

    # 4. Check treasury balance
    resp = client.get("/api/v2/finance/treasury/balance", headers=owner_headers)
    assert resp.json["available"] == 4000.00


def test_parametric_insurance(app, test_store, seeded_finance):
    """Test insurance enrollment and parametric payout."""
    from app.finance.insurance_engine import enroll_merchant, trigger_parametric_claim

    with app.app_context():
        # Give some cash for premium
        from app.finance.ledger import record_transaction
        record_transaction(
            store_id=test_store.store_id,
            debit_account_type="OPERATING",
            credit_account_type="REVENUE",
            amount=Decimal("1000.00"),
            description="Cash for premium"
        )

        # 1. Enroll
        policy = enroll_merchant(test_store.store_id, seeded_finance["weather_ins_id"])
        db.session.commit()
        assert policy.status == "ACTIVE"

        # 2. Trigger Claim (Remote parameter met)
        claim = trigger_parametric_claim(policy.id, "HEAVY_RAIN_55MM", Decimal("5000.00"))
        db.session.commit()
        assert claim.status == "PAID"
        assert claim.payout_amount == Decimal("5000.00")
