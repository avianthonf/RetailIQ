"""initial schema

Revision ID: 1b03ef9c8006
Revises: 
Create Date: 2026-02-20 16:44:38.376367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1b03ef9c8006'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # 1. Create users WITHOUT the store_id FK first
    op.create_table('users',
    sa.Column('user_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('mobile_number', sa.String(length=15), nullable=False),
    sa.Column('full_name', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('password_hash', sa.String(), nullable=True),
    sa.Column('role', sa.Enum('owner', 'staff', name='user_role_enum'), nullable=True),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('mobile_number')
    )

    # 2. Create stores (can now reference users.user_id)
    op.create_table('stores',
    sa.Column('store_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner_user_id', sa.Integer(), nullable=True),
    sa.Column('store_name', sa.String(), nullable=True),
    sa.Column('store_type', sa.Enum('grocery', 'pharmacy', 'general', 'electronics', 'clothing', 'other', name='store_type_enum'), nullable=True),
    sa.Column('city', sa.String(), nullable=True),
    sa.Column('state', sa.String(), nullable=True),
    sa.Column('gst_number', sa.String(), nullable=True),
    sa.Column('currency_symbol', sa.String(), nullable=True),
    sa.Column('working_days', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('opening_time', sa.Time(), nullable=True),
    sa.Column('closing_time', sa.Time(), nullable=True),
    sa.Column('timezone', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('store_id')
    )

    # 3. Now add the store_id FK to users (circular dependency resolved)
    op.create_foreign_key('fk_users_store_id', 'users', 'stores', ['store_id'], ['store_id'])

    # 4. categories (needs stores)
    op.create_table('categories',
    sa.Column('category_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('color_tag', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('gst_rate', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('category_id')
    )

    # 5. customers (needs stores)
    op.create_table('customers',
    sa.Column('customer_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('mobile_number', sa.String(length=15), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('customer_id')
    )

    # 6. products (needs stores + categories)
    op.create_table('products',
    sa.Column('product_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('sku_code', sa.String(length=50), nullable=True),
    sa.Column('uom', sa.Enum('pieces', 'kg', 'litre', 'pack', name='product_uom_enum'), nullable=True),
    sa.Column('cost_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('selling_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('current_stock', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('reorder_level', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('supplier_name', sa.String(), nullable=True),
    sa.Column('barcode', sa.String(), nullable=True),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('lead_time_days', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.category_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('product_id')
    )
    op.create_index('idx_products_store_active_stock', 'products', ['store_id', 'is_active', 'current_stock'], unique=False)
    op.create_index('idx_products_store_sku', 'products', ['store_id', 'sku_code'], unique=True)

    # 7. transactions (needs stores + customers)
    op.create_table('transactions',
    sa.Column('transaction_id', sa.UUID(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('payment_mode', sa.Enum('CASH', 'UPI', 'CARD', 'CREDIT', name='payment_mode_enum'), nullable=True),
    sa.Column('notes', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('is_return', sa.Boolean(), nullable=False),
    sa.Column('original_transaction_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.customer_id'], ),
    sa.ForeignKeyConstraint(['original_transaction_id'], ['transactions.transaction_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('transaction_id')
    )
    op.create_index('idx_transactions_store_created', 'transactions', ['store_id', sa.text('created_at DESC')], unique=False)

    # 8. transaction_items (needs transactions + products)
    op.create_table('transaction_items',
    sa.Column('item_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('transaction_id', sa.UUID(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('selling_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('original_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('cost_price_at_time', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.transaction_id'], ),
    sa.PrimaryKeyConstraint('item_id')
    )
    op.create_index('idx_transaction_items_product_id', 'transaction_items', ['product_id'], unique=False)
    op.create_index('idx_transaction_items_transaction_id', 'transaction_items', ['transaction_id'], unique=False)

    # 9. product_price_history (needs products + users)
    op.create_table('product_price_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('cost_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('selling_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('changed_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('changed_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['changed_by'], ['users.user_id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # 10. stock_audits (needs stores + users)
    op.create_table('stock_audits',
    sa.Column('audit_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('audit_date', sa.TIMESTAMP(), nullable=True),
    sa.Column('conducted_by', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['conducted_by'], ['users.user_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('audit_id')
    )

    # 11. stock_audit_items (needs stock_audits + products)
    op.create_table('stock_audit_items',
    sa.Column('item_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('audit_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('expected_stock', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('actual_stock', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('discrepancy', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.ForeignKeyConstraint(['audit_id'], ['stock_audits.audit_id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.PrimaryKeyConstraint('item_id')
    )

    # 12. stock_adjustments (needs products + users)
    op.create_table('stock_adjustments',
    sa.Column('adj_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('quantity_added', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('purchase_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('adjusted_by', sa.Integer(), nullable=True),
    sa.Column('adjusted_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('reason', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['adjusted_by'], ['users.user_id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.PrimaryKeyConstraint('adj_id')
    )

    # 13. alerts (needs stores + products)
    op.create_table('alerts',
    sa.Column('alert_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('alert_type', sa.String(length=50), nullable=True),
    sa.Column('priority', sa.Enum('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', name='alert_priority_enum'), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('resolved_at', sa.TIMESTAMP(), nullable=True),
    sa.Column('snoozed_until', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('alert_id')
    )
    op.create_index('idx_alerts_store_resolved_priority', 'alerts', ['store_id', 'resolved_at', 'priority'], unique=False)

    # 14. forecast_cache (needs stores + products)
    op.create_table('forecast_cache',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=True),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('forecast_date', sa.Date(), nullable=True),
    sa.Column('forecast_value', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('lower_bound', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('upper_bound', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('regime', sa.String(length=20), nullable=True),
    sa.Column('generated_at', sa.TIMESTAMP(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], ),
    sa.ForeignKeyConstraint(['store_id'], ['stores.store_id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # 15. Aggregation tables (no FK constraints)
    op.create_table('daily_store_summary',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('revenue', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('profit', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('transaction_count', sa.Integer(), nullable=True),
    sa.Column('avg_basket', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('units_sold', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.PrimaryKeyConstraint('date', 'store_id')
    )
    op.create_index('idx_daily_store_summary_store_date', 'daily_store_summary', ['store_id', sa.text('date DESC')], unique=False)

    op.create_table('daily_category_summary',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('revenue', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('profit', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('units_sold', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.PrimaryKeyConstraint('date', 'store_id', 'category_id')
    )

    op.create_table('daily_sku_summary',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('revenue', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('profit', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('units_sold', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('avg_selling_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.PrimaryKeyConstraint('date', 'store_id', 'product_id')
    )
    op.create_index('idx_daily_sku_summary_store_product_date', 'daily_sku_summary', ['store_id', 'product_id', sa.text('date DESC')], unique=False)


def downgrade() -> None:
    # Drop in reverse order of creation
    op.drop_index('idx_daily_sku_summary_store_product_date', table_name='daily_sku_summary')
    op.drop_table('daily_sku_summary')
    op.drop_table('daily_category_summary')
    op.drop_index('idx_daily_store_summary_store_date', table_name='daily_store_summary')
    op.drop_table('daily_store_summary')
    op.drop_table('forecast_cache')
    op.drop_index('idx_alerts_store_resolved_priority', table_name='alerts')
    op.drop_table('alerts')
    op.drop_table('stock_adjustments')
    op.drop_table('stock_audit_items')
    op.drop_table('stock_audits')
    op.drop_table('product_price_history')
    op.drop_index('idx_transaction_items_transaction_id', table_name='transaction_items')
    op.drop_index('idx_transaction_items_product_id', table_name='transaction_items')
    op.drop_table('transaction_items')
    op.drop_index('idx_transactions_store_created', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index('idx_products_store_sku', table_name='products')
    op.drop_index('idx_products_store_active_stock', table_name='products')
    op.drop_table('products')
    op.drop_table('customers')
    op.drop_table('categories')
    op.drop_constraint('fk_users_store_id', 'users', type_='foreignkey')
    op.drop_table('stores')
    op.drop_table('users')