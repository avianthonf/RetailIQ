"""supplier management

Revision ID: b4g02e3d6c99
Revises: a3f91d2c5b88
Create Date: 2026-02-27 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4g02e3d6c99"
down_revision: Union[str, None] = "a3f91d2c5b88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("contact_name", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), server_default="30", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # supplier_products
    op.create_table(
        "supplier_products",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quoted_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_preferred_supplier", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_updated", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.product_id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),
    )

    # purchase_orders
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # purchase_order_items
    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("po_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("ordered_qty", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("received_qty", sa.Numeric(precision=12, scale=3), server_default="0", nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["po_id"],
            ["purchase_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.product_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # goods_receipt_notes
    op.create_table(
        "goods_receipt_notes",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("po_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("received_by", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["po_id"],
            ["purchase_orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["received_by"],
            ["users.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.store_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("goods_receipt_notes")
    op.drop_table("purchase_order_items")
    op.drop_table("purchase_orders")
    op.drop_table("supplier_products")
    op.drop_table("suppliers")
