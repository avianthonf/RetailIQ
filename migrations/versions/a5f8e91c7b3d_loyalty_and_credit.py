"""loyalty_and_credit

Revision ID: a5f8e91c7b3d
Revises: 57dd177fb8f4
Create Date: 2026-02-28 13:02:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a5f8e91c7b3d"
down_revision: Union[str, None] = "57dd177fb8f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # loyalty_programs
    op.create_table(
        "loyalty_programs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("points_per_rupee", sa.Numeric(precision=6, scale=4), server_default="1.0"),
        sa.Column("redemption_rate", sa.Numeric(precision=6, scale=4), server_default="0.1"),
        sa.Column("min_redemption_points", sa.Integer(), server_default="100"),
        sa.Column("expiry_days", sa.Integer(), server_default="365"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id"),
    )

    # customer_loyalty_accounts
    op.create_table(
        "customer_loyalty_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("total_points", sa.Numeric(precision=12, scale=2), server_default="0"),
        sa.Column("redeemable_points", sa.Numeric(precision=12, scale=2), server_default="0"),
        sa.Column("lifetime_earned", sa.Numeric(precision=12, scale=2), server_default="0"),
        sa.Column("last_activity_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
    )

    # loyalty_transactions
    op.create_table(
        "loyalty_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("type IN ('EARN', 'REDEEM', 'EXPIRE', 'ADJUST')", name="chk_loyalty_txn_type"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["customer_loyalty_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.transaction_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # credit_ledger
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Numeric(precision=12, scale=2), server_default="0"),
        sa.Column("credit_limit", sa.Numeric(precision=12, scale=2), server_default="0"),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "store_id", name="uq_credit_ledger_cust_store"),
    )

    # credit_transactions
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("type IN ('CREDIT_SALE', 'REPAYMENT', 'ADJUSTMENT')", name="chk_credit_txn_type"),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["credit_ledger.id"],
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.transaction_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("credit_ledger")
    op.drop_table("loyalty_transactions")
    op.drop_table("customer_loyalty_accounts")
    op.drop_table("loyalty_programs")
