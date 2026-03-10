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


def enroll_merchant(
    store_id: int,
    product_id: int
) -> InsurancePolicy:
    """Enroll a merchant in an insurance product."""
    product = db.session.get(InsuranceProduct, product_id)
    if not product or not product.is_active:
        raise InsuranceError("Invalid or inactive insurance product.")

    # 1. Charge first month's premium
    record_transaction(
        store_id=store_id,
        debit_account_type="REVENUE",  # Expense for merchant
        credit_account_type="OPERATING", # Paying from operating
        amount=product.premium_monthly,
        description=f"Insurance premium for {product.name}",
        meta_data={"product_id": product.id}
    )

    # 2. Create policy
    policy = InsurancePolicy(
        store_id=store_id,
        product_id=product_id,
        status="ACTIVE",
        enrolled_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)
    )
    db.session.add(policy)
    db.session.flush()

    return policy


def trigger_parametric_claim(
    policy_id: int,
    trigger_type: str,
    payout_amount: Decimal
) -> InsuranceClaim:
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
        trigger_type=trigger_type,
        payout_amount=payout_amount,
        status="APPROVED",
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(claim)
    db.session.flush()

    # 2. Payout to merchant
    record_transaction(
        store_id=policy.store_id,
        debit_account_type="OPERATING",
        credit_account_type="REVENUE", # System payout
        amount=payout_amount,
        description=f"Insurance claim payout for policy #{policy.id} (Trigger: {trigger_type})"
    )

    claim.status = "PAID"
    claim.paid_at = datetime.now(timezone.utc)

    db.session.flush()
    return claim
