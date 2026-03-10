import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app import db
from app.models.finance_models import PaymentTransaction

from .ledger import record_transaction


class PaymentError(Exception):
    """Base exception for payment operations."""
    pass


def process_merchant_payment(
    store_id: int,
    amount: Decimal,
    payment_method: str,
    transaction_id: uuid.UUID | None = None
) -> PaymentTransaction:
    """
    Process an incoming payment for a merchant.
    Simulates integration with Stripe/Unit.
    """
    if amount <= 0:
        raise PaymentError("Payment amount must be positive.")

    # 1. Calculate fees (e.g. 2.9% + 0.30)
    fee_percentage = Decimal("0.029")
    fixed_fee = Decimal("0.30")
    total_fees = round(amount * fee_percentage + fixed_fee, 2)
    net_amount = amount - total_fees

    # 2. Record in Ledger
    # Gross amount to OPERATING, then Fee to a SYSTEM/OPERATING expense?
    # Actually, let's record Net to OPERATING and specify the fee in meta.

    ledger_txn = record_transaction(
        store_id=store_id,
        debit_account_type="OPERATING",
        credit_account_type="REVENUE",
        amount=net_amount,
        description=f"Payment received via {payment_method}",
        meta_data={
            "gross_amount": str(amount),
            "fees": str(total_fees),
            "source_txn": str(transaction_id) if transaction_id else None
        }
    )

    # 3. Save payment record
    payment = PaymentTransaction(
        store_id=store_id,
        transaction_id=transaction_id,
        external_id=f"pay_{uuid.uuid4().hex[:12]}",
        amount=amount,
        fees=total_fees,
        status="SETTLED",
        payment_method=payment_method,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(payment)
    db.session.flush()

    return payment
