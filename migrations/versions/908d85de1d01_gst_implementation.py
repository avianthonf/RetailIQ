"""gst_implementation

Revision ID: 908d85de1d01
Revises: a5f8e91c7b3d
Create Date: 2026-02-28 08:36:06.674151

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '908d85de1d01'
down_revision: Union[str, None] = 'a5f8e91c7b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 50 common retail HSN codes for seeding
HSN_SEED_DATA = [
    ('0401', 'Fresh milk', 0),
    ('0402', 'Milk powder / condensed milk', 5),
    ('0901', 'Coffee (roasted, ground)', 5),
    ('0902', 'Tea', 5),
    ('1001', 'Wheat', 0),
    ('1006', 'Rice', 5),
    ('1101', 'Wheat or meslin flour', 5),
    ('1507', 'Soyabean oil', 5),
    ('1508', 'Groundnut oil', 5),
    ('1511', 'Palm oil', 5),
    ('1701', 'Cane/beet sugar', 5),
    ('1704', 'Sugar confectionery', 18),
    ('1905', 'Biscuits, cakes, pastry', 12),
    ('2009', 'Fruit juices', 12),
    ('2101', 'Instant coffee & tea extracts', 18),
    ('2106', 'Food preparations n.e.s.', 18),
    ('2201', 'Mineral/aerated water (packaged)', 18),
    ('2202', 'Flavoured/sweetened beverages', 28),
    ('2501', 'Salt', 0),
    ('3004', 'Pharmaceutical medicaments', 12),
    ('3304', 'Cosmetics & beauty preparations', 18),
    ('3305', 'Hair care preparations', 18),
    ('3306', 'Oral hygiene preparations (toothpaste)', 18),
    ('3401', 'Soap, organic surface-active products', 18),
    ('3402', 'Detergents', 18),
    ('3808', 'Insecticides, disinfectants', 18),
    ('3923', 'Plastic articles for packing', 18),
    ('3924', 'Plastic household articles', 18),
    ('4011', 'New rubber tyres', 28),
    ('4202', 'Trunks, suitcases, handbags', 18),
    ('4818', 'Toilet paper, tissues, napkins', 18),
    ('4820', 'Registers, notebooks, stationery', 12),
    ('4901', 'Printed books, newspapers', 0),
    ('4911', 'Printed matter, commercial catalogues', 12),
    ('6109', 'T-shirts, singlets, vests (knitted)', 5),
    ('6110', 'Jerseys, pullovers (knitted)', 12),
    ('6203', 'Mens suits, trousers, shorts (woven)', 12),
    ('6204', 'Womens suits, trousers, skirts (woven)', 12),
    ('6205', 'Mens shirts (woven)', 12),
    ('6302', 'Bed linen, table linen, towels', 12),
    ('6403', 'Footwear with rubber/plastic sole', 12),
    ('6404', 'Footwear with textile upper', 12),
    ('6506', 'Headgear', 12),
    ('7013', 'Glassware for table, kitchen', 18),
    ('7323', 'Steel wool, pot scourers, utensils', 18),
    ('8414', 'Fans, ventilating equipment', 18),
    ('8418', 'Refrigerators, freezers', 18),
    ('8471', 'Computers, laptops', 18),
    ('8517', 'Telephones, smartphones', 18),
    ('8528', 'Monitors, projectors, TVs', 18),
]


def upgrade() -> None:
    # 1. Create hsn_master table
    op.create_table('hsn_master',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('hsn_code', sa.String(length=8), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('default_gst_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hsn_code')
    )

    # 2. Seed HSN master with 50 codes
    hsn_table = sa.table('hsn_master',
        sa.column('id', sa.UUID()),
        sa.column('hsn_code', sa.String),
        sa.column('description', sa.Text),
        sa.column('default_gst_rate', sa.Numeric)
    )
    op.bulk_insert(hsn_table, [
        {'id': str(uuid.uuid4()), 'hsn_code': code, 'description': desc, 'default_gst_rate': rate}
        for code, desc, rate in HSN_SEED_DATA
    ])

    # 3. Add hsn_code and gst_category to products
    op.add_column('products', sa.Column('hsn_code', sa.String(length=8), nullable=True))
    op.add_column('products', sa.Column('gst_category', sa.String(length=16), server_default='REGULAR', nullable=True))
    op.create_foreign_key('fk_products_hsn_code', 'products', 'hsn_master', ['hsn_code'], ['hsn_code'])

    # 4. Create store_gst_config
    op.create_table('store_gst_config',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('gstin', sa.String(length=15), nullable=True),
        sa.Column('registration_type', sa.String(length=16), server_default='REGULAR', nullable=True),
        sa.Column('state_code', sa.String(length=2), nullable=True),
        sa.Column('is_gst_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id')
    )

    # 5. Create gst_transactions
    op.create_table('gst_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('transaction_id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('taxable_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('cgst_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('sgst_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('igst_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_gst', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('hsn_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.transaction_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id')
    )

    # 6. Create gst_filing_periods
    op.create_table('gst_filing_periods',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('total_taxable', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_cgst', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_sgst', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('total_igst', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('invoice_count', sa.Integer(), nullable=True),
        sa.Column('gstr1_json_path', sa.String(length=512), nullable=True),
        sa.Column('compiled_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='DRAFT', nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'period', name='uq_store_period')
    )


def downgrade() -> None:
    op.drop_table('gst_filing_periods')
    op.drop_table('gst_transactions')
    op.drop_table('store_gst_config')
    op.drop_constraint('fk_products_hsn_code', 'products', type_='foreignkey')
    op.drop_column('products', 'gst_category')
    op.drop_column('products', 'hsn_code')
    op.drop_table('hsn_master')
