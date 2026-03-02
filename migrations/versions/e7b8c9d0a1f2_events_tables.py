"""events variables

Revision ID: e7b8c9d0a1f2
Revises: c3d91f2a7b44
Create Date: 2026-03-01 08:35:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e7b8c9d0a1f2'
down_revision = 'c3d91f2a7b44'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. business_events
    op.create_table(
        'business_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.store_id'), nullable=True),
        sa.Column('event_name', sa.String(length=128), nullable=True),
        sa.Column('event_type', sa.String(length=32), sa.CheckConstraint("event_type IN ('HOLIDAY', 'FESTIVAL', 'PROMOTION', 'SALE_DAY', 'CLOSURE')"), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('expected_impact_pct', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('recurrence_rule', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True)
    )

    # 2. demand_sensing_log
    op.create_table(
        'demand_sensing_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.store_id'), nullable=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.product_id'), nullable=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('actual_demand', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('base_forecast', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('event_adjusted_forecast', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('active_events', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True)
    )

    # 3. event_impact_actuals
    op.create_table(
        'event_impact_actuals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_events.id'), nullable=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.product_id'), nullable=True),
        sa.Column('actual_impact_pct', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('measured_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True)
    )

def downgrade() -> None:
    op.drop_table('event_impact_actuals')
    op.drop_table('demand_sensing_log')
    op.drop_table('business_events')
