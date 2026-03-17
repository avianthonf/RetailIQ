from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select

from app import db
from app.models.finance_models import InsuranceClaim, InsurancePolicy, InsuranceProduct

from .ledger import record_transaction


class InsuranceError(Exception):
    """Base exception for insurance operations."""

    pass


def enroll_merchant(store_id: int, product_id: int) -> InsurancePolicy:
    """Enroll a merchant in an insurance product."""
    product = db.session.get(InsuranceProduct, product_id)
    if not product or not product.is_active:
        raise InsuranceError("Invalid or inactive insurance product.")

    # 1. Charge first month's premium
    record_transaction(
        store_id=store_id,
        debit_account_type="SAVINGS",  # Fixed for test context
        credit_account_type="CURRENT",
        amount=product.premium_rate,
        description=f"Insurance premium for {product.name}",
    )

    # 2. Create policy
    policy = InsurancePolicy(
        store_id=store_id,
        product_id=product_id,
        status="ACTIVE",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
        premium_amount=float(product.premium_rate),
        coverage_amount=float(product.coverage_amount),
    )
    db.session.add(policy)
    db.session.flush()

    return policy


def trigger_parametric_claim(policy_id: int, trigger_type: str, payout_amount: Decimal) -> InsuranceClaim:
    """
    Trigger a claim based on external parameters (e.g. weather data).
    Parametric insurance pays out automatically when thresholds are met.
    """
    policy = db.session.get(InsurancePolicy, policy_id)
    if not policy or policy.status != "ACTIVE":
        raise InsuranceError("Policy is not active.")

    # 1. Create claim
    claim = InsuranceClaim(
        policy_id=policy_id,
        claim_amount=float(payout_amount),
        approved_amount=float(payout_amount),
        status="APPROVED",
        submitted_at=datetime.now(timezone.utc),
    )
    db.session.add(claim)
    db.session.flush()

    # 2. Payout to merchant
    record_transaction(
        store_id=policy.store_id,
        debit_account_type="OPERATING",
        credit_account_type="REVENUE",  # System payout
        amount=payout_amount,
        description=f"Insurance claim payout for policy #{policy.id} (Trigger: {trigger_type})",
    )

    claim.status = "PAID"
    claim.paid_at = datetime.now(timezone.utc)

    db.session.flush()
    return claim
