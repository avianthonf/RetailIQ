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


def apply_for_loan(store_id: int, product_id: int, amount: Decimal, term_days: int) -> LoanApplication:
    """Submit a new loan application."""
    product = db.session.get(LoanProduct, product_id)
    if not product or not product.is_active:
        raise LoanError("Invalid or inactive loan product.")

    if not (product.min_amount <= amount <= product.max_amount):
        raise LoanError(f"Amount {amount} is outside allowed range for this product.")

    if term_days > product.max_tenure_days:
        raise LoanError(f"Term {term_days} days exceeds maximum allowed.")

    application = LoanApplication(
        store_id=store_id,
        loan_product_id=product_id,
        requested_amount=amount,
        status="PENDING",
        tenure_days=term_days,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(application)
    db.session.flush()
    return application


def approve_loan(application_id: int, approved_amount: Decimal) -> LoanApplication:
    """Approve a loan application and set terms."""
    app = db.session.get(LoanApplication, application_id)
    if not app or app.status != "PENDING":
        raise LoanError("Application not in a state that can be approved.")

    product = db.session.get(LoanProduct, app.loan_product_id)

    app.status = "APPROVED"
    app.approved_amount = approved_amount
    app.interest_rate = float(product.base_interest_rate)
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
    app.disbursed_at = datetime.now(timezone.utc)
    app.disbursement_date = app.disbursed_at.date()
    # Assuming maturity is tenure from disbursement
    app.due_date = app.disbursed_at + timedelta(days=app.tenure_days)
    app.outstanding_principal = app.approved_amount

    # 2. Record ledger transaction
    # We move money from a systemic 'RESERVE' (or bank-partner) account to merchant 'OPERATING'
    # For now, let's treat the 'REVENUE' account of the system or a specific bank-link account
    # as the source.

    txn_id = record_transaction(
        store_id=app.store_id,
        debit_account_type="OPERATING",
        credit_account_type="REVENUE",
        amount=app.approved_amount,
        description=f"Disbursement for Loan #{app.id}",
    )
    return txn_id


def record_repayment(loan_id: int, amount: Decimal) -> uuid.UUID:
    """Record a repayment against a loan."""
    app = db.session.get(LoanApplication, loan_id)
    if not app or app.status not in ("DISBURSED", "REPAYING"):
        raise LoanError("Loan is not in an active repayment state.")

    if amount <= 0:
        raise LoanError("Repayment amount must be positive.")

    # Extremely simplified interest/principal split
    interest_component = round(app.outstanding_principal * Decimal((app.interest_rate or 0) / 100 / 12), 2)
    principal_component = amount - interest_component

    if principal_component > app.outstanding_principal:
        principal_component = app.outstanding_principal
        interest_component = amount - principal_component

    # 1. Update ledger
    txn_id = record_transaction(
        store_id=app.store_id,
        debit_account_type="REVENUE",
        credit_account_type="OPERATING",
        amount=amount,
        description=f"Repayment for Loan #{app.id}",
    )

    # 2. Update loan record
    app.outstanding_principal -= principal_component
    app.total_interest_paid += interest_component

    if app.outstanding_principal <= 0:
        app.status = "CLOSED"
    else:
        app.status = "REPAYING"

    repayment = LoanRepayment(
        loan_application_id=app.id,
        amount=amount,
        principal_component=principal_component,
        interest_component=interest_component,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(repayment)

    db.session.flush()
    return txn_id
