"""add missing FK indexes

Revision ID: f4a5b6c7d8e9
Revises: 31f7ac7d8d9a
Create Date: 2026-03-01 10:35:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = '31f7ac7d8d9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # supplier_products
    op.create_index('idx_supplier_products_supplier_id', 'supplier_products', ['supplier_id'])
    op.create_index('idx_supplier_products_product_id', 'supplier_products', ['product_id'])

    # purchase_orders
    op.create_index('idx_purchase_orders_supplier_id', 'purchase_orders', ['supplier_id'])
    op.create_index('idx_purchase_orders_created_by', 'purchase_orders', ['created_by'])

    # purchase_order_items
    op.create_index('idx_purchase_order_items_po_id', 'purchase_order_items', ['po_id'])
    op.create_index('idx_purchase_order_items_product_id', 'purchase_order_items', ['product_id'])

    # goods_receipt_notes
    op.create_index('idx_goods_receipt_notes_po_id', 'goods_receipt_notes', ['po_id'])
    op.create_index('idx_goods_receipt_notes_store_id', 'goods_receipt_notes', ['store_id'])
    op.create_index('idx_goods_receipt_notes_received_by', 'goods_receipt_notes', ['received_by'])

    # gst_transactions
    op.create_index('idx_gst_transactions_store_period', 'gst_transactions', ['store_id', 'period'])

    # loyalty_transactions
    op.create_index('idx_loyalty_transactions_account_id', 'loyalty_transactions', ['account_id'])
    op.create_index('idx_loyalty_transactions_transaction_id', 'loyalty_transactions', ['transaction_id'])

    # credit_transactions
    op.create_index('idx_credit_transactions_ledger_id', 'credit_transactions', ['ledger_id'])
    op.create_index('idx_credit_transactions_transaction_id', 'credit_transactions', ['transaction_id'])

    # ocr_job_items
    op.create_index('idx_ocr_job_items_job_id', 'ocr_job_items', ['job_id'])
    op.create_index('idx_ocr_job_items_matched_product_id', 'ocr_job_items', ['matched_product_id'])

    # vision_category_tags
    op.create_index('idx_vision_category_tags_job_id', 'vision_category_tags', ['job_id'])

    # ocr_jobs
    op.create_index('idx_ocr_jobs_store_id', 'ocr_jobs', ['store_id'])

    # whatsapp_templates
    op.create_index('idx_whatsapp_templates_store_id', 'whatsapp_templates', ['store_id'])

    # whatsapp_message_log
    op.create_index('idx_whatsapp_message_log_store_id', 'whatsapp_message_log', ['store_id'])

    # store_group_memberships
    op.create_index('idx_store_group_memberships_group_id', 'store_group_memberships', ['group_id'])
    op.create_index('idx_store_group_memberships_store_id', 'store_group_memberships', ['store_id'])

    # chain_daily_aggregates
    op.create_index('idx_chain_daily_aggregates_group_id', 'chain_daily_aggregates', ['group_id'])
    op.create_index('idx_chain_daily_aggregates_store_id', 'chain_daily_aggregates', ['store_id'])

    # inter_store_transfer_suggestions
    op.create_index('idx_inter_store_transfer_group_id', 'inter_store_transfer_suggestions', ['group_id'])
    op.create_index('idx_inter_store_transfer_from_store', 'inter_store_transfer_suggestions', ['from_store_id'])
    op.create_index('idx_inter_store_transfer_to_store', 'inter_store_transfer_suggestions', ['to_store_id'])
    op.create_index('idx_inter_store_transfer_product', 'inter_store_transfer_suggestions', ['product_id'])

    # business_events
    op.create_index('idx_business_events_store_id', 'business_events', ['store_id'])

    # demand_sensing_log
    op.create_index('idx_demand_sensing_log_store_id', 'demand_sensing_log', ['store_id'])
    op.create_index('idx_demand_sensing_log_product_id', 'demand_sensing_log', ['product_id'])

    # event_impact_actuals
    op.create_index('idx_event_impact_actuals_event_id', 'event_impact_actuals', ['event_id'])
    op.create_index('idx_event_impact_actuals_product_id', 'event_impact_actuals', ['product_id'])

    # stock_adjustments
    op.create_index('idx_stock_adjustments_product_id', 'stock_adjustments', ['product_id'])
    op.create_index('idx_stock_adjustments_adjusted_by', 'stock_adjustments', ['adjusted_by'])

    # stock_audit_items
    op.create_index('idx_stock_audit_items_audit_id', 'stock_audit_items', ['audit_id'])
    op.create_index('idx_stock_audit_items_product_id', 'stock_audit_items', ['product_id'])

    # product_price_history
    op.create_index('idx_product_price_history_product_id', 'product_price_history', ['product_id'])
    op.create_index('idx_product_price_history_store_id', 'product_price_history', ['store_id'])
    op.create_index('idx_product_price_history_changed_by', 'product_price_history', ['changed_by'])


def downgrade() -> None:
    op.drop_index('idx_product_price_history_changed_by', 'product_price_history')
    op.drop_index('idx_product_price_history_store_id', 'product_price_history')
    op.drop_index('idx_product_price_history_product_id', 'product_price_history')
    op.drop_index('idx_stock_audit_items_product_id', 'stock_audit_items')
    op.drop_index('idx_stock_audit_items_audit_id', 'stock_audit_items')
    op.drop_index('idx_stock_adjustments_adjusted_by', 'stock_adjustments')
    op.drop_index('idx_stock_adjustments_product_id', 'stock_adjustments')
    op.drop_index('idx_event_impact_actuals_product_id', 'event_impact_actuals')
    op.drop_index('idx_event_impact_actuals_event_id', 'event_impact_actuals')
    op.drop_index('idx_demand_sensing_log_product_id', 'demand_sensing_log')
    op.drop_index('idx_demand_sensing_log_store_id', 'demand_sensing_log')
    op.drop_index('idx_business_events_store_id', 'business_events')
    op.drop_index('idx_inter_store_transfer_product', 'inter_store_transfer_suggestions')
    op.drop_index('idx_inter_store_transfer_to_store', 'inter_store_transfer_suggestions')
    op.drop_index('idx_inter_store_transfer_from_store', 'inter_store_transfer_suggestions')
    op.drop_index('idx_inter_store_transfer_group_id', 'inter_store_transfer_suggestions')
    op.drop_index('idx_chain_daily_aggregates_store_id', 'chain_daily_aggregates')
    op.drop_index('idx_chain_daily_aggregates_group_id', 'chain_daily_aggregates')
    op.drop_index('idx_store_group_memberships_store_id', 'store_group_memberships')
    op.drop_index('idx_store_group_memberships_group_id', 'store_group_memberships')
    op.drop_index('idx_whatsapp_message_log_store_id', 'whatsapp_message_log')
    op.drop_index('idx_whatsapp_templates_store_id', 'whatsapp_templates')
    op.drop_index('idx_ocr_jobs_store_id', 'ocr_jobs')
    op.drop_index('idx_vision_category_tags_job_id', 'vision_category_tags')
    op.drop_index('idx_ocr_job_items_matched_product_id', 'ocr_job_items')
    op.drop_index('idx_ocr_job_items_job_id', 'ocr_job_items')
    op.drop_index('idx_credit_transactions_transaction_id', 'credit_transactions')
    op.drop_index('idx_credit_transactions_ledger_id', 'credit_transactions')
    op.drop_index('idx_loyalty_transactions_transaction_id', 'loyalty_transactions')
    op.drop_index('idx_loyalty_transactions_account_id', 'loyalty_transactions')
    op.drop_index('idx_gst_transactions_store_period', 'gst_transactions')
    op.drop_index('idx_goods_receipt_notes_received_by', 'goods_receipt_notes')
    op.drop_index('idx_goods_receipt_notes_store_id', 'goods_receipt_notes')
    op.drop_index('idx_goods_receipt_notes_po_id', 'goods_receipt_notes')
    op.drop_index('idx_purchase_order_items_product_id', 'purchase_order_items')
    op.drop_index('idx_purchase_order_items_po_id', 'purchase_order_items')
    op.drop_index('idx_purchase_orders_created_by', 'purchase_orders')
    op.drop_index('idx_purchase_orders_supplier_id', 'purchase_orders')
    op.drop_index('idx_supplier_products_product_id', 'supplier_products')
    op.drop_index('idx_supplier_products_supplier_id', 'supplier_products')
