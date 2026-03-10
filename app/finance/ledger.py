import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import func, select

from app import db
from app.models.finance_models import FinancialAccount, LedgerEntry


class LedgerError(Exception):
    """Base exception for ledger operations."""

    pass


def get_or_create_account(store_id: int, account_type: str, account_name: str | None = None) -> FinancialAccount:
    """Get an existing financial account or create a new one for a store."""
    account = db.session.execute(
        select(FinancialAccount).filter_by(store_id=store_id, account_type=account_type)
    ).scalar_one_or_none()

    if not account:
        if not account_name:
            account_name = f"{account_type.title()} Account"

        account = FinancialAccount(store_id=store_id, account_type=account_type, account_name=account_name, balance=0)
        db.session.add(account)
        db.session.flush()  # Get ID without committing

    return account


def record_transaction(
    store_id: int,
    debit_account_type: str,
    credit_account_type: str,
    amount: Decimal,
    description: str,
    meta_data: dict | None = None,
) -> uuid.UUID:
    """
    Record a balanced double-entry transaction.

    DEBIT: Increases asset/expense, decreases liability/equity/revenue.
    CREDIT: Decreases asset/expense, increases liability/equity/revenue.

    In our simplified merchant ledger:
    - DEBIT 'OPERATING' (Asset) increases store's available cash.
    - CREDIT 'REVENUE' (Revenue) increases store's total earned revenue.
    """
    if amount <= 0:
        raise LedgerError("Transaction amount must be positive.")

    # 1. Get/Create accounts
    debit_account = get_or_create_account(store_id, debit_account_type)
    credit_account = get_or_create_account(store_id, credit_account_type)

    if debit_account.id == credit_account.id:
        raise LedgerError("Debit and credit accounts must be different.")

    txn_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 2. Create ledger entries
    debit_entry = LedgerEntry(
        transaction_id=txn_id,
        account_id=debit_account.id,
        entry_type="DEBIT",
        amount=amount,
        description=description,
        meta_data=meta_data,
        created_at=now,
    )

    credit_entry = LedgerEntry(
        transaction_id=txn_id,
        account_id=credit_account.id,
        entry_type="CREDIT",
        amount=amount,
        description=description,
        meta_data=meta_data,
        created_at=now,
    )

    db.session.add(debit_entry)
    db.session.add(credit_entry)

    # 3. Update account balances (simplified denormalization)
    # Assets (Operating, Reserve): Balance = Credits - Debits?
    # Actually, let's keep it simple: scale-independent balance.
    # In accounting:
    # Asset: Balance = Debits - Credits
    # Revenue/Liability: Balance = Credits - Debits

    if debit_account_type in ("OPERATING", "RESERVE"):
        debit_account.balance += amount
    else:
        # For Revenue/Liability/Escrow, a Debit decreases the balance
        debit_account.balance -= amount

    if credit_account_type in ("OPERATING", "RESERVE"):
        credit_account.balance -= amount
    else:
        # For Revenue/Liability/Escrow, a Credit increases the balance
        credit_account.balance += amount

    return txn_id


def get_account_balance(account_id: int) -> Decimal:
    """Calculate account balance directly from ledger entries for audit."""
    debits = db.session.execute(
        select(func.sum(LedgerEntry.amount)).filter_by(account_id=account_id, entry_type="DEBIT")
    ).scalar() or Decimal(0)

    credits = db.session.execute(
        select(func.sum(LedgerEntry.amount)).filter_by(account_id=account_id, entry_type="CREDIT")
    ).scalar() or Decimal(0)

    # Logic depends on account type, but let's assume we fetch the account to decide
    account = db.session.get(FinancialAccount, account_id)
    if not account:
        return Decimal(0)

    if account.account_type in ("OPERATING", "RESERVE"):
        return Decimal(debits) - Decimal(credits)
    else:
        return Decimal(credits) - Decimal(debits)
