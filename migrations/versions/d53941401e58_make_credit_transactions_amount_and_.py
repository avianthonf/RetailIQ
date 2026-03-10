"""make credit_transactions amount and balance_after not null

Revision ID: d53941401e58
Revises: 121021f2b187
Create Date: 2026-03-10 21:00:17.385953

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d53941401e58"
down_revision: Union[str, None] = "121021f2b187"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credit_transactions", schema=None) as batch_op:
        batch_op.alter_column("amount", existing_type=sa.NUMERIC(precision=12, scale=2), nullable=False)
        batch_op.alter_column("balance_after", existing_type=sa.NUMERIC(precision=12, scale=2), nullable=False)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_column("total_amount")

    with op.batch_alter_table("credit_transactions", schema=None) as batch_op:
        batch_op.alter_column("balance_after", existing_type=sa.NUMERIC(precision=12, scale=2), nullable=True)
        batch_op.alter_column("amount", existing_type=sa.NUMERIC(precision=12, scale=2), nullable=True)
