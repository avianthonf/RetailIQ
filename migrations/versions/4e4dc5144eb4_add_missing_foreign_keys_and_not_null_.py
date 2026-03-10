"""add missing foreign keys and not null constraints

Revision ID: 4e4dc5144eb4
Revises: d53941401e58
Create Date: 2026-03-10 21:19:19.237666

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e4dc5144eb4"
down_revision: Union[str, None] = "d53941401e58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. forecast_cache.generated_at NOT NULL
    if insp.has_table("forecast_cache"):
        for c in insp.get_columns("forecast_cache"):
            if c["name"] == "generated_at" and c["nullable"]:
                with op.batch_alter_table("forecast_cache", schema=None) as batch_op:
                    batch_op.alter_column("generated_at", existing_type=sa.TIMESTAMP(), nullable=False)

    # 2. loyalty_programs.is_active NOT NULL
    if insp.has_table("loyalty_programs"):
        for c in insp.get_columns("loyalty_programs"):
            if c["name"] == "is_active" and c["nullable"]:
                with op.batch_alter_table("loyalty_programs", schema=None) as batch_op:
                    batch_op.alter_column(
                        "is_active",
                        existing_type=sa.BOOLEAN(),
                        nullable=False,
                        existing_server_default=sa.text("'true'"),
                    )

    # 3. Foreign Keys
    def has_fk(table_name, referred_table, constrained_column):
        if not insp.has_table(table_name):
            return True  # skip if no table
        for fk in insp.get_foreign_keys(table_name):
            if fk["referred_table"] == referred_table and constrained_column in fk["constrained_columns"]:
                return True
        return False

    if not has_fk("product_price_history", "stores", "store_id"):
        with op.batch_alter_table("product_price_history", schema=None) as batch_op:
            batch_op.create_foreign_key(None, "stores", ["store_id"], ["store_id"])

    if not has_fk("products", "hsn_master", "hsn_code"):
        with op.batch_alter_table("products", schema=None) as batch_op:
            batch_op.create_foreign_key(None, "hsn_master", ["hsn_code"], ["hsn_code"])

    if not has_fk("transactions", "staff_sessions", "session_id"):
        with op.batch_alter_table("transactions", schema=None) as batch_op:
            batch_op.create_foreign_key(None, "staff_sessions", ["session_id"], ["id"])

    if not has_fk("users", "stores", "store_id"):
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.create_foreign_key("fk_users_store_id", "stores", ["store_id"], ["store_id"], use_alter=True)


def downgrade() -> None:
    # We do not strictly need downgrades for safety reconciliations
    pass
