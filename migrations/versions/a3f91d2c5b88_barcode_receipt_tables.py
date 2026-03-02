"""barcode and receipt printing tables

Revision ID: a3f91d2c5b88
Revises: 1b03ef9c8006
Create Date: 2026-02-27 16:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3f91d2c5b88'
down_revision: Union[str, None] = '1b03ef9c8006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. barcodes — product barcode registry
    op.create_table('barcodes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('barcode_value', sa.String(length=64), nullable=False),
    sa.Column('barcode_type', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('barcode_value')
    )
    op.create_index('idx_barcodes_store_product', 'barcodes', ['store_id', 'product_id'], unique=False)

    # 2. receipt_templates — per-store receipt configuration
    op.create_table('receipt_templates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('header_text', sa.Text(), nullable=True),
    sa.Column('footer_text', sa.Text(), nullable=True),
    sa.Column('show_gstin', sa.Boolean(), nullable=False),
    sa.Column('paper_width_mm', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('store_id')
    )

    # 3. print_jobs — async print job tracking
    op.create_table('print_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.UUID(), nullable=True),
    sa.Column('job_type', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.transaction_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_print_jobs_store_status', 'print_jobs', ['store_id', 'status'], unique=False)


def downgrade() -> None:
    # Drop in reverse order
    op.drop_index('idx_print_jobs_store_status', table_name='print_jobs')
    op.drop_table('print_jobs')
    op.drop_table('receipt_templates')
    op.drop_index('idx_barcodes_store_product', table_name='barcodes')
    op.drop_table('barcodes')
