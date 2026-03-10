from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from app import db
from app.models.finance_models import FinancialAccount, TreasuryConfig, TreasuryTransaction

from .ledger import record_transaction


class TreasuryError(Exception):
    """Base exception for treasury operations."""
    pass


def set_sweep_config(
    store_id: int,
    strategy: str,
    min_balance: Decimal
) -> TreasuryConfig:
    """Configure treasury sweep strategy for a merchant."""
    config = db.session.execute(
        select(TreasuryConfig).filter_by(store_id=store_id)
    ).scalar_one_or_none()

    if not config:
        config = TreasuryConfig(store_id=store_id)
        db.session.add(config)

    config.sweep_strategy = strategy
    config.min_balance_threshold = min_balance
    config.is_active = (strategy != "OFF")

    db.session.flush()
    return config


def perform_sweep(store_id: int) -> Decimal | None:
    """
    Perform an automated sweep from the Operating account to the Treasury/Reserve account.
    Triggered when operating balance exceeds the min_balance_threshold.
    """
    config = db.session.execute(
        select(TreasuryConfig).filter_by(store_id=store_id, is_active=True)
    ).scalar_one_or_none()

    if not config or config.sweep_strategy == "OFF":
        return None

    # 1. Check operating balance
    operating_account = db.session.execute(
        select(FinancialAccount).filter_by(store_id=store_id, account_type="OPERATING")
    ).scalar_one_or_none()

    if not operating_account or operating_account.balance <= config.min_balance_threshold:
        return None

    # 2. Determine sweep amount
    sweep_amount = operating_account.balance - config.min_balance_threshold

    # 3. Record in Ledger
    record_transaction(
        store_id=store_id,
        debit_account_type="RESERVE",  # Moving to Reserve/Treasury
        credit_account_type="OPERATING", # Moving from Operating
        amount=sweep_amount,
        description=f"Automated treasury sweep ({config.sweep_strategy} strategy)",
        meta_data={"strategy": config.sweep_strategy}
    )

    # 4. Record treasury transaction
    tx = TreasuryTransaction(
        store_id=store_id,
        type="SWEEP_IN",
        amount=sweep_amount,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(tx)

    db.session.flush()
    return sweep_amount


def accrue_yield(store_id: int) -> Decimal:
    """
    Accrue daily yield on the Reserve account.
    In reality, this is based on the day's average balance.
    """
    reserve_account = db.session.execute(
        select(FinancialAccount).filter_by(store_id=store_id, account_type="RESERVE")
    ).scalar_one_or_none()

    if not reserve_account or reserve_account.balance <= 0:
        return Decimal(0)

    # Simplified yield calculation (e.g. 4.5% APY / 365)
    annual_yield_bps = 450
    daily_yield_rate = Decimal(annual_yield_bps) / 10000 / 365
    yield_amount = round(reserve_account.balance * daily_yield_rate, 2)

    if yield_amount <= 0:
        return Decimal(0)

    # Record yield as new Revenue/Equity (system owes merchant more)
    record_transaction(
        store_id=store_id,
        debit_account_type="RESERVE",
        credit_account_type="REVENUE", # System expense, merchant revenue
        amount=yield_amount,
        description="Daily treasury yield accrual"
    )

    # Log treasury action
    tx = TreasuryTransaction(
        store_id=store_id,
        type="YIELD_ACCRUAL",
        amount=yield_amount,
        current_yield_bps=annual_yield_bps,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(tx)

    db.session.flush()
    return yield_amount
