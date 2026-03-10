"""reconcile_schema_drift

Revision ID: 121021f2b187
Revises: 7f8e9a0b1c2d
Create Date: 2026-03-10 20:25:27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "121021f2b187"
down_revision: Union[str, Sequence[str], None] = ("7f8e9a0b1c2d", "c3d91f2a7b44")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Add AuditMixin columns ---
    try:
        op.add_column("users", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
        op.add_column("users", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
    except Exception:
        pass
    try:
        op.add_column("stores", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
        op.add_column("stores", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
    except Exception:
        pass
    try:
        op.add_column(
            "categories", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "categories", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "products", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "products", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "customers", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "customers", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "transactions", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "transactions", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "transaction_items", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "transaction_items", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "stock_adjustments", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "stock_adjustments", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "stock_audits", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "stock_audits", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "stock_audit_items", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "stock_audit_items", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column("alerts", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
        op.add_column("alerts", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))
    except Exception:
        pass
    try:
        op.add_column(
            "forecast_cache", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "forecast_cache", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "daily_store_summary",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "daily_store_summary",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "daily_category_summary",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "daily_category_summary",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "daily_sku_summary", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "daily_sku_summary", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "suppliers", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "suppliers", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "supplier_products", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "supplier_products", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "purchase_orders", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "purchase_orders", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "purchase_order_items",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "purchase_order_items",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "goods_receipt_notes",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "goods_receipt_notes",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "barcodes", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "barcodes", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "receipt_templates", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "receipt_templates", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "print_jobs", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "print_jobs", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "staff_sessions", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "staff_sessions", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "staff_daily_targets",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "staff_daily_targets",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "analytics_snapshots",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "analytics_snapshots",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "loyalty_programs", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "loyalty_programs", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "customer_loyalty_accounts",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "customer_loyalty_accounts",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "loyalty_transactions",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "loyalty_transactions",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "credit_ledger", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "credit_ledger", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "credit_transactions",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "credit_transactions",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "hsn_master", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "hsn_master", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "store_gst_config", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "store_gst_config", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "gst_transactions", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "gst_transactions", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "gst_filing_periods",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "gst_filing_periods",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "whatsapp_config", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "whatsapp_config", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "whatsapp_templates",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "whatsapp_templates",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "whatsapp_message_log",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "whatsapp_message_log",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "store_groups", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "store_groups", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "store_group_memberships",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "store_group_memberships",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "chain_daily_aggregates",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "chain_daily_aggregates",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "inter_store_transfer_suggestions",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "inter_store_transfer_suggestions",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "business_events", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "business_events", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "demand_sensing_log",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "demand_sensing_log",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "event_impact_actuals",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "event_impact_actuals",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "ocr_jobs", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "ocr_jobs", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "ocr_job_items", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "ocr_job_items", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "vision_category_tags",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "vision_category_tags",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "rbac_permissions", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "rbac_permissions", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass
    try:
        op.add_column(
            "pricing_suggestions",
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
        op.add_column(
            "pricing_suggestions",
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True),
        )
    except Exception:
        pass
    try:
        op.add_column(
            "pricing_rules", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
        op.add_column(
            "pricing_rules", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True)
        )
    except Exception:
        pass

    # --- 1.5. Add other missing columns ---
    try:
        op.add_column("alerts", sa.Column("product_name", sa.String(), nullable=True))
    except Exception:
        pass

    # --- 2. Create missing tables ---
    op.create_table(
        "countries",
        sa.Column("code", sa.String(length=2), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("default_locale", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("tax_system", sa.String(length=32), nullable=False),
        sa.Column("data_residency_required", sa.Boolean(), nullable=False),
        sa.Column(
            "data_residency_region",
            sa.String(length=32),
        ),
        sa.Column(
            "regulatory_body",
            sa.String(length=128),
        ),
        sa.Column(
            "phone_code",
            sa.String(length=5),
        ),
        sa.Column("date_format", sa.String(length=16), nullable=False),
        sa.Column("number_format", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "go_live_date",
            sa.Date(),
        ),
        sa.Column(
            "config",
            postgresql.JSONB(),
        ),
    )

    op.create_table(
        "supported_currencies",
        sa.Column("code", sa.String(length=3), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("decimal_places", sa.Integer(), nullable=False),
        sa.Column("symbol_position", sa.String(length=8), nullable=False),
        sa.Column("thousands_sep", sa.String(length=1), nullable=False),
        sa.Column("decimal_sep", sa.String(length=1), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "currency_rates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("from_currency", sa.String(length=3), nullable=False),
        sa.Column("to_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(),
        ),
        sa.UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_currency_rate_pair_date"),
    )
    op.create_index("idx_currency_rates_date", "currency_rates", ["rate_date"], unique=False)

    op.create_table(
        "translation_keys",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("key", sa.String(length=256), nullable=False, unique=True),
        sa.Column(
            "module",
            sa.String(length=64),
        ),
        sa.Column(
            "description",
            sa.String(length=None),
        ),
        sa.UniqueConstraint("key", name=None),
    )

    op.create_table(
        "translations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("key_id", sa.Integer(), sa.ForeignKey("translation_keys.id"), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("value", sa.String(length=None), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
        ),
        sa.UniqueConstraint("key_id", "locale", name="uq_translation_key_locale"),
    )
    op.create_index("idx_translation_locale", "translations", ["locale"], unique=False)

    op.create_table(
        "loan_products",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("product_type", sa.String(length=15), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("max_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("interest_rate_bps", sa.Integer(), nullable=False),
        sa.Column("max_term_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "insurance_products",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=12), nullable=False),
        sa.Column(
            "description",
            sa.String(length=None),
        ),
        sa.Column("premium_monthly", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("max_coverage", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "payment_providers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column(
            "supported_methods",
            postgresql.JSONB(),
        ),
        sa.Column("settlement_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "api_version",
            sa.String(length=16),
        ),
        sa.Column(
            "webhook_url",
            sa.String(length=512),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(),
        ),
        sa.UniqueConstraint("code", name=None),
    )

    op.create_table(
        "kyc_providers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column("verification_type", sa.String(length=32), nullable=False),
        sa.Column(
            "id_format_regex",
            sa.String(length=256),
        ),
        sa.Column("id_label", sa.String(length=64), nullable=False),
        sa.Column(
            "required_fields",
            postgresql.JSONB(),
        ),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column(
            "api_endpoint",
            sa.String(length=512),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code", name=None),
    )

    op.create_table(
        "country_tax_configs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column("tax_type", sa.String(length=32), nullable=False),
        sa.Column("standard_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column(
            "reduced_rates",
            postgresql.JSONB(),
        ),
        sa.Column(
            "zero_rated_categories",
            postgresql.JSONB(),
        ),
        sa.Column(
            "exempt_categories",
            postgresql.JSONB(),
        ),
        sa.Column("filing_frequency", sa.String(length=16), nullable=False),
        sa.Column(
            "filing_format",
            sa.String(length=64),
        ),
        sa.Column("tax_id_label", sa.String(length=32), nullable=False),
        sa.Column(
            "tax_id_regex",
            sa.String(length=256),
        ),
        sa.Column("has_subnational_tax", sa.Boolean(), nullable=False),
        sa.Column(
            "subnational_config",
            postgresql.JSONB(),
        ),
        sa.Column("e_invoice_required", sa.Boolean(), nullable=False),
        sa.Column(
            "e_invoice_format",
            sa.String(length=32),
        ),
        sa.Column(
            "compliance_notes",
            sa.String(length=None),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("country_code", "tax_type", name="uq_country_tax_type"),
    )

    op.create_table(
        "store_tax_registrations",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column(
            "tax_id",
            sa.String(length=64),
        ),
        sa.Column("registration_type", sa.String(length=32), nullable=False),
        sa.Column("is_tax_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "state_province",
            sa.String(length=64),
        ),
        sa.Column(
            "additional_config",
            postgresql.JSONB(),
        ),
        sa.Column(
            "registered_at",
            sa.TIMESTAMP(),
        ),
        sa.UniqueConstraint("store_id", "country_code", name="uq_store_country_tax"),
    )
    op.create_index("idx_store_tax_reg_country", "store_tax_registrations", ["country_code"], unique=False)

    op.create_table(
        "tax_transactions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.transaction_id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column("tax_type", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "taxable_amount",
            sa.Numeric(precision=14, scale=2),
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(precision=14, scale=2),
        ),
        sa.Column(
            "tax_breakdown",
            postgresql.JSONB(),
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "exchange_rate_to_usd",
            sa.Numeric(precision=18, scale=8),
        ),
        sa.Column(
            "e_invoice_id",
            sa.String(length=128),
        ),
        sa.Column(
            "e_invoice_status",
            sa.String(length=16),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
        ),
    )
    op.create_index("idx_tax_txn_country", "tax_transactions", ["country_code", "period"], unique=False)
    op.create_index("idx_tax_txn_store_period", "tax_transactions", ["store_id", "period"], unique=False)

    op.create_table(
        "financial_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("account_name", sa.String(length=64), nullable=False),
        sa.Column("account_type", sa.String(length=9), nullable=False),
        sa.Column("balance", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("store_id", "account_type", name="uq_store_account_type"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("entry_type", sa.String(length=6), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "description",
            sa.String(length=512),
        ),
        sa.Column(
            "meta_data",
            postgresql.JSONB(),
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"], unique=False)
    op.create_index("ix_ledger_entries_created_at", "ledger_entries", ["created_at"], unique=False)

    op.create_table(
        "merchant_kyc",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False, unique=True),
        sa.Column(
            "business_type",
            sa.String(length=64),
        ),
        sa.Column(
            "tax_id",
            sa.String(length=64),
        ),
        sa.Column("verification_status", sa.String(length=8), nullable=False),
        sa.Column(
            "verification_date",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "document_urls",
            postgresql.JSONB(),
        ),
        sa.Column(
            "notes",
            sa.String(length=None),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("store_id", name=None),
    )

    op.create_table(
        "merchant_credit_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False, unique=True),
        sa.Column("credit_score", sa.Integer(), nullable=False),
        sa.Column(
            "risk_tier",
            sa.String(length=16),
        ),
        sa.Column(
            "scoring_version",
            sa.String(length=16),
        ),
        sa.Column(
            "factors",
            postgresql.JSONB(),
        ),
        sa.Column("last_recalculated", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("store_id", name=None),
    )

    op.create_table(
        "loan_applications",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("loan_products.id"), nullable=False),
        sa.Column("requested_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "approved_amount",
            sa.Numeric(precision=14, scale=2),
        ),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column(
            "interest_rate_at_origination",
            sa.Integer(),
        ),
        sa.Column(
            "term_days",
            sa.Integer(),
        ),
        sa.Column("applied_at", sa.TIMESTAMP(), nullable=False),
        sa.Column(
            "decision_at",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "disbursement_date",
            sa.Date(),
        ),
        sa.Column(
            "maturity_date",
            sa.Date(),
        ),
        sa.Column("outstanding_principal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_interest_paid", sa.Numeric(precision=14, scale=2), nullable=False),
    )

    op.create_table(
        "loan_repayments",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("loan_id", sa.BigInteger(), sa.ForeignKey("loan_applications.id"), nullable=False),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("principal_component", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("interest_component", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("repaid_at", sa.TIMESTAMP(), nullable=False),
    )

    op.create_table(
        "insurance_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("insurance_products.id"), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("enrolled_at", sa.TIMESTAMP(), nullable=False),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(),
        ),
    )

    op.create_table(
        "insurance_claims",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("policy_id", sa.BigInteger(), sa.ForeignKey("insurance_policies.id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("payout_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column(
            "paid_at",
            sa.TIMESTAMP(),
        ),
    )

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.transaction_id")),
        sa.Column(
            "external_id",
            sa.String(length=128),
        ),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("fees", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column(
            "payment_method",
            sa.String(length=32),
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )

    op.create_table(
        "treasury_configs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False, unique=True),
        sa.Column("sweep_strategy", sa.String(length=12), nullable=False),
        sa.Column("min_balance_threshold", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("store_id", name=None),
    )

    op.create_table(
        "treasury_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("type", sa.String(length=13), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "current_yield_bps",
            sa.Integer(),
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )

    op.create_table(
        "payment_records",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.transaction_id")),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("payment_providers.id"), nullable=False),
        sa.Column("payment_method", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "provider_ref_id",
            sa.String(length=128),
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "error_code",
            sa.String(length=64),
        ),
        sa.Column(
            "error_message",
            sa.String(length=None),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "completed_at",
            sa.TIMESTAMP(),
        ),
    )
    op.create_index("idx_payment_records_provider_ref", "payment_records", ["provider_ref_id"], unique=False)
    op.create_index("idx_payment_records_store_status", "payment_records", ["store_id", "status"], unique=False)

    op.create_table(
        "store_payment_methods",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("payment_providers.id"), nullable=False),
        sa.Column(
            "merchant_account_id",
            sa.String(length=128),
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("onboarding_status", sa.String(length=16), nullable=False),
        sa.Column(
            "credentials_encrypted",
            postgresql.JSONB(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
        ),
        sa.UniqueConstraint("store_id", "provider_id", name="uq_store_payment_provider"),
    )

    op.create_table(
        "kyc_records",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("kyc_providers.id"), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column(
            "id_number_hash",
            sa.String(length=128),
        ),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column(
            "verification_data",
            postgresql.JSONB(),
        ),
        sa.Column(
            "rejection_reason",
            sa.String(length=None),
        ),
        sa.Column(
            "verified_at",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
        ),
    )
    op.create_index("idx_kyc_records_status", "kyc_records", ["verification_status"], unique=False)
    op.create_index("idx_kyc_records_store_country", "kyc_records", ["store_id", "country_code"], unique=False)

    op.create_table(
        "e_invoices",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("transaction_id", sa.UUID(), sa.ForeignKey("transactions.transaction_id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("country_code", sa.String(length=2), sa.ForeignKey("countries.code"), nullable=False),
        sa.Column("invoice_format", sa.String(length=32), nullable=False),
        sa.Column(
            "invoice_number",
            sa.String(length=128),
        ),
        sa.Column(
            "authority_ref",
            sa.String(length=256),
        ),
        sa.Column(
            "xml_payload",
            sa.String(length=None),
        ),
        sa.Column(
            "qr_code_data",
            sa.String(length=None),
        ),
        sa.Column(
            "digital_signature",
            sa.String(length=None),
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "submission_response",
            postgresql.JSONB(),
        ),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
        ),
    )
    op.create_index("idx_einvoice_status", "e_invoices", ["status"], unique=False)
    op.create_index("idx_einvoice_store_country", "e_invoices", ["store_id", "country_code"], unique=False)

    op.create_table(
        "supplier_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("supplier_id", sa.UUID(), sa.ForeignKey("suppliers.id"), nullable=False, unique=True),
        sa.Column("business_name", sa.String(length=256), nullable=False),
        sa.Column("business_type", sa.String(length=12), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column(
            "verification_date",
            sa.TIMESTAMP(),
        ),
        sa.Column(
            "rating",
            sa.Numeric(precision=3, scale=2),
        ),
        sa.Column("total_orders_fulfilled", sa.Integer(), nullable=False),
        sa.Column(
            "fulfillment_rate",
            sa.Numeric(precision=5, scale=2),
        ),
        sa.Column(
            "avg_ship_days",
            sa.Numeric(precision=4, scale=1),
        ),
        sa.Column(
            "return_rate",
            sa.Numeric(precision=5, scale=2),
        ),
        sa.Column(
            "categories",
            postgresql.JSONB(),
        ),
        sa.Column(
            "regions_served",
            postgresql.JSONB(),
        ),
        sa.Column(
            "min_order_value",
            sa.Numeric(precision=12, scale=2),
        ),
        sa.Column(
            "payment_terms",
            postgresql.JSONB(),
        ),
        sa.Column(
            "logo_url",
            sa.String(length=512),
        ),
        sa.Column("catalog_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("supplier_id", name=None),
    )

    op.create_table(
        "marketplace_catalog_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("supplier_profile_id", sa.BigInteger(), sa.ForeignKey("supplier_profiles.id"), nullable=False),
        sa.Column(
            "sku",
            sa.String(length=64),
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "description",
            sa.String(length=None),
        ),
        sa.Column(
            "category",
            sa.String(length=128),
        ),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("moq", sa.Integer(), nullable=False),
        sa.Column("case_pack", sa.Integer(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column(
            "images",
            postgresql.JSONB(),
        ),
        sa.Column(
            "specifications",
            postgresql.JSONB(),
        ),
        sa.Column(
            "bulk_pricing",
            postgresql.JSONB(),
        ),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )
    op.create_index(
        "idx_catalog_items_supplier_active",
        "marketplace_catalog_items",
        ["supplier_profile_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "marketplace_purchase_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("order_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("supplier_profile_id", sa.BigInteger(), sa.ForeignKey("supplier_profiles.id"), nullable=False),
        sa.Column("status", sa.String(length=19), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "payment_terms",
            sa.String(length=32),
        ),
        sa.Column("payment_status", sa.String(length=14), nullable=False),
        sa.Column("financed_by_retailiq", sa.Boolean(), nullable=False),
        sa.Column("loan_id", sa.BigInteger(), sa.ForeignKey("loan_applications.id")),
        sa.Column(
            "shipping_tracking",
            postgresql.JSONB(),
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column(
            "expected_delivery",
            sa.Date(),
        ),
        sa.Column(
            "actual_delivery",
            sa.Date(),
        ),
        sa.UniqueConstraint("order_number", name=None),
    )
    op.create_index(
        "idx_marketplace_po_supplier_status",
        "marketplace_purchase_orders",
        ["supplier_profile_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_marketplace_po_merchant_status", "marketplace_purchase_orders", ["merchant_id", "status"], unique=False
    )

    op.create_table(
        "marketplace_po_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("marketplace_purchase_orders.id"), nullable=False),
        sa.Column("catalog_item_id", sa.BigInteger(), sa.ForeignKey("marketplace_catalog_items.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
    )

    op.create_table(
        "marketplace_rfqs",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("matched_suppliers_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )

    op.create_table(
        "marketplace_rfq_responses",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("rfq_id", sa.BigInteger(), sa.ForeignKey("marketplace_rfqs.id"), nullable=False),
        sa.Column("supplier_profile_id", sa.BigInteger(), sa.ForeignKey("supplier_profiles.id"), nullable=False),
        sa.Column("quoted_items", postgresql.JSONB(), nullable=False),
        sa.Column("total_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "delivery_days",
            sa.Integer(),
        ),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("rfq_id", "supplier_profile_id", name="uq_rfq_supplier"),
    )

    op.create_table(
        "marketplace_procurement_recommendations",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column(
            "product_category",
            sa.String(length=128),
        ),
        sa.Column("recommended_items", postgresql.JSONB(), nullable=False),
        sa.Column(
            "recommended_supplier_ids",
            postgresql.JSONB(),
        ),
        sa.Column(
            "estimated_savings",
            sa.Numeric(precision=12, scale=2),
        ),
        sa.Column("urgency", sa.String(length=8), nullable=False),
        sa.Column(
            "trigger_event",
            sa.String(length=64),
        ),
        sa.Column(
            "confidence",
            sa.Numeric(precision=3, scale=2),
        ),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(),
        ),
        sa.Column("acted_upon", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
    )
    op.create_index(
        "idx_proc_rec_merchant_urgency",
        "marketplace_procurement_recommendations",
        ["merchant_id", "urgency"],
        unique=False,
    )

    op.create_table(
        "marketplace_supplier_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("supplier_profile_id", sa.BigInteger(), sa.ForeignKey("supplier_profiles.id"), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("marketplace_purchase_orders.id")),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "review_text",
            sa.String(length=None),
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.UniqueConstraint("merchant_id", "order_id", name="uq_merchant_order_review"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="chk_supplier_review_rating"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column(
            "resource_id",
            sa.String(length=128),
        ),
        sa.Column(
            "ip_address",
            sa.String(length=45),
        ),
        sa.Column(
            "user_agent",
            sa.String(length=None),
        ),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column(
            "meta_data",
            postgresql.JSONB(),
        ),
        sa.Column("timestamp", sa.TIMESTAMP(), nullable=False),
    )


def downgrade() -> None:
    # --- Drop missing tables ---
    op.drop_table("audit_logs")
    op.drop_table("marketplace_supplier_reviews")
    op.drop_table("marketplace_procurement_recommendations")
    op.drop_table("marketplace_rfq_responses")
    op.drop_table("marketplace_rfqs")
    op.drop_table("marketplace_po_items")
    op.drop_table("marketplace_purchase_orders")
    op.drop_table("marketplace_catalog_items")
    op.drop_table("supplier_profiles")
    op.drop_table("e_invoices")
    op.drop_table("kyc_records")
    op.drop_table("store_payment_methods")
    op.drop_table("payment_records")
    op.drop_table("treasury_transactions")
    op.drop_table("treasury_configs")
    op.drop_table("payment_transactions")
    op.drop_table("insurance_claims")
    op.drop_table("insurance_policies")
    op.drop_table("loan_repayments")
    op.drop_table("loan_applications")
    op.drop_table("merchant_credit_profiles")
    op.drop_table("merchant_kyc")
    op.drop_table("ledger_entries")
    op.drop_table("financial_accounts")
    op.drop_table("tax_transactions")
    op.drop_table("store_tax_registrations")
    op.drop_table("country_tax_configs")
    op.drop_table("kyc_providers")
    op.drop_table("payment_providers")
    op.drop_table("insurance_products")
    op.drop_table("loan_products")
    op.drop_table("translations")
    op.drop_table("translation_keys")
    op.drop_table("currency_rates")
    op.drop_table("supported_currencies")
    op.drop_table("countries")

    # --- Remove AuditMixin columns ---
    try:
        op.drop_column("alerts", "product_name")
    except Exception:
        pass
    try:
        op.drop_column("users", "updated_at")
        op.drop_column("users", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("stores", "updated_at")
        op.drop_column("stores", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("categories", "updated_at")
        op.drop_column("categories", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("products", "updated_at")
        op.drop_column("products", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("customers", "updated_at")
        op.drop_column("customers", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("transactions", "updated_at")
        op.drop_column("transactions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("transaction_items", "updated_at")
        op.drop_column("transaction_items", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("stock_adjustments", "updated_at")
        op.drop_column("stock_adjustments", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("stock_audits", "updated_at")
        op.drop_column("stock_audits", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("stock_audit_items", "updated_at")
        op.drop_column("stock_audit_items", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("alerts", "updated_at")
        op.drop_column("alerts", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("forecast_cache", "updated_at")
        op.drop_column("forecast_cache", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("daily_store_summary", "updated_at")
        op.drop_column("daily_store_summary", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("daily_category_summary", "updated_at")
        op.drop_column("daily_category_summary", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("daily_sku_summary", "updated_at")
        op.drop_column("daily_sku_summary", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("suppliers", "updated_at")
        op.drop_column("suppliers", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("supplier_products", "updated_at")
        op.drop_column("supplier_products", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("purchase_orders", "updated_at")
        op.drop_column("purchase_orders", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("purchase_order_items", "updated_at")
        op.drop_column("purchase_order_items", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("goods_receipt_notes", "updated_at")
        op.drop_column("goods_receipt_notes", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("barcodes", "updated_at")
        op.drop_column("barcodes", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("receipt_templates", "updated_at")
        op.drop_column("receipt_templates", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("print_jobs", "updated_at")
        op.drop_column("print_jobs", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("staff_sessions", "updated_at")
        op.drop_column("staff_sessions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("staff_daily_targets", "updated_at")
        op.drop_column("staff_daily_targets", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("analytics_snapshots", "updated_at")
        op.drop_column("analytics_snapshots", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("loyalty_programs", "updated_at")
        op.drop_column("loyalty_programs", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("customer_loyalty_accounts", "updated_at")
        op.drop_column("customer_loyalty_accounts", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("loyalty_transactions", "updated_at")
        op.drop_column("loyalty_transactions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("credit_ledger", "updated_at")
        op.drop_column("credit_ledger", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("credit_transactions", "updated_at")
        op.drop_column("credit_transactions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("hsn_master", "updated_at")
        op.drop_column("hsn_master", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("store_gst_config", "updated_at")
        op.drop_column("store_gst_config", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("gst_transactions", "updated_at")
        op.drop_column("gst_transactions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("gst_filing_periods", "updated_at")
        op.drop_column("gst_filing_periods", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("whatsapp_config", "updated_at")
        op.drop_column("whatsapp_config", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("whatsapp_templates", "updated_at")
        op.drop_column("whatsapp_templates", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("whatsapp_message_log", "updated_at")
        op.drop_column("whatsapp_message_log", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("store_groups", "updated_at")
        op.drop_column("store_groups", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("store_group_memberships", "updated_at")
        op.drop_column("store_group_memberships", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("chain_daily_aggregates", "updated_at")
        op.drop_column("chain_daily_aggregates", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("inter_store_transfer_suggestions", "updated_at")
        op.drop_column("inter_store_transfer_suggestions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("business_events", "updated_at")
        op.drop_column("business_events", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("demand_sensing_log", "updated_at")
        op.drop_column("demand_sensing_log", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("event_impact_actuals", "updated_at")
        op.drop_column("event_impact_actuals", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("ocr_jobs", "updated_at")
        op.drop_column("ocr_jobs", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("ocr_job_items", "updated_at")
        op.drop_column("ocr_job_items", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("vision_category_tags", "updated_at")
        op.drop_column("vision_category_tags", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("rbac_permissions", "updated_at")
        op.drop_column("rbac_permissions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("pricing_suggestions", "updated_at")
        op.drop_column("pricing_suggestions", "created_at")
    except Exception:
        pass
    try:
        op.drop_column("pricing_rules", "updated_at")
        op.drop_column("pricing_rules", "created_at")
    except Exception:
        pass
