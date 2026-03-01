"""pricing tables

Revision ID: c3d91f2a7b44
Revises: b966c53b0061
Create Date: 2026-02-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d91f2a7b44'
down_revision: Union[str, None] = '64289450c79b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Alter product_price_history to add new columns ────────────────────
    # Add store_id FK
    op.add_column('product_price_history',
        sa.Column('store_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_pph_store_id', 'product_price_history', 'stores',
        ['store_id'], ['store_id']
    )

    # Add old_price / new_price columns
    op.add_column('product_price_history',
        sa.Column('old_price', sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column('product_price_history',
        sa.Column('new_price', sa.Numeric(precision=12, scale=2), nullable=True)
    )

    # Add reason column
    op.add_column('product_price_history',
        sa.Column('reason', sa.String(length=64), nullable=True)
    )

    # ── 2. Create pricing_suggestions ────────────────────────────────────────
    op.create_table(
        'pricing_suggestions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('suggested_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('current_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('price_change_pct', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('reason', sa.String(length=256), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='PENDING', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('actioned_at', sa.TIMESTAMP(), nullable=True),
        sa.CheckConstraint("status IN ('PENDING','APPLIED','DISMISSED')",
                           name='chk_pricing_suggestion_status'),
        sa.ForeignKeyConstraint(['product_id'], ['products.product_id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_pricing_suggestions_store_status',
                    'pricing_suggestions', ['store_id', 'status'])
    op.create_index('idx_pricing_suggestions_product_created',
                    'pricing_suggestions', ['product_id', 'created_at'])

    # ── 3. Create pricing_rules ───────────────────────────────────────────────
    op.create_table(
        'pricing_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('rule_type', sa.String(length=32), nullable=True),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_pricing_rules_store_active',
                    'pricing_rules', ['store_id', 'is_active'])


def downgrade() -> None:
    op.drop_index('idx_pricing_rules_store_active', table_name='pricing_rules')
    op.drop_table('pricing_rules')
    op.drop_index('idx_pricing_suggestions_product_created',
                  table_name='pricing_suggestions')
    op.drop_index('idx_pricing_suggestions_store_status',
                  table_name='pricing_suggestions')
    op.drop_table('pricing_suggestions')

    try:
        op.drop_constraint('fk_pph_store_id', 'product_price_history', type_='foreignkey')
    except Exception:
        pass
    op.drop_column('product_price_history', 'reason')
    op.drop_column('product_price_history', 'new_price')
    op.drop_column('product_price_history', 'old_price')
    op.drop_column('product_price_history', 'store_id')
