"""frontend parity entities

Revision ID: 4b8d10f3c2a1
Revises: ef7d1bae1e6e
Create Date: 2026-03-21 18:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b8d10f3c2a1"
down_revision: Union[str, None] = "ef7d1bae1e6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loyalty_tiers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("program_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("min_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_points", sa.Integer(), nullable=True),
        sa.Column("benefits", sa.JSON(), nullable=True),
        sa.Column("multiplier", sa.Numeric(precision=6, scale=2), nullable=True, server_default="1.0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["loyalty_programs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "name", name="uq_loyalty_tier_program_name"),
    )

    with op.batch_alter_table("customer_loyalty_accounts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tier_id", sa.UUID(), nullable=True))
        batch_op.create_foreign_key("fk_customer_loyalty_accounts_tier_id", "loyalty_tiers", ["tier_id"], ["id"])

    op.create_table(
        "gst_hsn_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("hsn_code", sa.String(length=8), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"]),
        sa.ForeignKeyConstraint(["hsn_code"], ["hsn_master.hsn_code"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "category_id", name="uq_gst_hsn_mapping_store_category"),
        sa.UniqueConstraint("store_id", "hsn_code", name="uq_gst_hsn_mapping_store_hsn"),
    )

    op.create_table(
        "whatsapp_campaigns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("template_name", sa.String(length=128), nullable=True),
        sa.Column("recipients", sa.JSON(), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("scheduled_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("sent_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
        sa.ForeignKeyConstraint(["template_id"], ["whatsapp_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "whatsapp_contact_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPTED_IN"),
        sa.Column("opted_in_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("opted_out_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.store_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "phone", name="uq_whatsapp_contact_pref_store_phone"),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_contact_preferences")
    op.drop_table("whatsapp_campaigns")
    op.drop_table("gst_hsn_mappings")

    with op.batch_alter_table("customer_loyalty_accounts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_customer_loyalty_accounts_tier_id", type_="foreignkey")
        batch_op.drop_column("tier_id")

    op.drop_table("loyalty_tiers")
