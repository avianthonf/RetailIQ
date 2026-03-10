import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select

from app import db
from app.models.finance_models import FinancialAccount, LoanApplication, LoanProduct, LoanRepayment

from .ledger import record_transaction


class LoanError(Exception):
    """Base exception for loan operations."""
    pass


def apply_for_loan(
    store_id: int,
    product_id: int,
    amount: Decimal,
    term_days: int
) -> LoanApplication:
    """Submit a new loan application."""
    product = db.session.get(LoanProduct, product_id)
    if not product or not product.is_active:
        raise LoanError("Invalid or inactive loan product.")

    if not (product.min_amount <= amount <= product.max_amount):
        raise LoanError(f"Amount {amount} is outside allowed range for this product.")

    if term_days > product.max_term_days:
        raise LoanError(f"Term {term_days} days exceeds maximum allowed.")

    application = LoanApplication(
        store_id=store_id,
        product_id=product_id,
        requested_amount=amount,
        status="APPLIED",
        term_days=term_days,
        applied_at=datetime.now(timezone.utc)
    )
    db.session.add(application)
    db.session.flush()
    return application


def approve_loan(application_id: int, approved_amount: Decimal) -> LoanApplication:
    """Approve a loan application and set terms."""
    app = db.session.get(LoanApplication, application_id)
    if not app or app.status != "APPLIED":
        raise LoanError("Application not in a state that can be approved.")

    product = db.session.get(LoanProduct, app.product_id)

    app.status = "APPROVED"
    app.approved_amount = approved_amount
    app.interest_rate_at_origination = product.interest_rate_bps
    app.decision_at = datetime.now(timezone.utc)

    db.session.flush()
    return app


def disburse_loan(application_id: int) -> uuid.UUID:
    """Disburse an approved loan to the merchant's operating account."""
    app = db.session.get(LoanApplication, application_id)
    if not app or app.status != "APPROVED":
        raise LoanError("Loan must be approved before disbursement.")

    # 1. Update loan status
    app.status = "DISBURSED"
    app.disbursement_date = datetime.now(timezone.utc).date()
    app.maturity_date = app.disbursement_date + timedelta(days=app.term_days)
    app.outstanding_principal = app.approved_amount

    # 2. Record ledger transaction
    # We move money from a systemic 'RESERVE' (or bank-partner) account to merchant 'OPERATING'
    # For now, let's treat the 'REVENUE' account of the system or a specific bank-link account
    # as the source.

    txn_id = record_transaction(
        store_id=app.store_id,
        debit_account_type="OPERATING",
        credit_account_type="ESCROW",  # Liability: the merchant now owes this money
        amount=app.approved_amount,
        description=f"Disbursement for Loan #{app.id}",
        meta_data={"loan_id": app.id}
    )

    db.session.flush()
    return txn_id


def record_repayment(loan_id: int, amount: Decimal) -> uuid.UUID:
    """Record a repayment against a loan."""
    app = db.session.get(LoanApplication, loan_id)
    if not app or app.status not in ("DISBURSED", "REPAYING"):
        raise LoanError("Loan is not in an active repayment state.")

    if amount <= 0:
        raise LoanError("Repayment amount must be positive.")

    # Extremely simplified interest/principal split
    # In reality, this used an amortization schedule
    interest_component = round(app.outstanding_principal * Decimal(app.interest_rate_at_origination / 10000 / 12), 2)
    principal_component = amount - interest_component

    if principal_component > app.outstanding_principal:
        principal_component = app.outstanding_principal
        interest_component = amount - principal_component

    # 1. Update ledger
    txn_id = record_transaction(
        store_id=app.store_id,
        debit_account_type="ESCROW",  # Decreasing liability
        credit_account_type="OPERATING", # Decreasing cash/operating
        amount=amount,
        description=f"Repayment for Loan #{app.id}",
        meta_data={"loan_id": app.id}
    )

    # 2. Update loan record
    app.outstanding_principal -= principal_component
    app.total_interest_paid += interest_component
    app.status = "REPAYING"

    if app.outstanding_principal <= 0:
        app.status = "PAID_OFF"
        app.outstanding_principal = 0

    repayment = LoanRepayment(
        loan_id=app.id,
        ledger_transaction_id=txn_id,
        amount=amount,
        principal_component=principal_component,
        interest_component=interest_component,
        repaid_at=datetime.now(timezone.utc)
    )
    db.session.add(repayment)

    db.session.flush()
    return txn_id
