import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.getcwd())

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Import all models to populate metadata
from app.models import (
    RFQ,
    APIUsageRecord,
    AuditLog,
    Base,
    CatalogItem,
    Category,
    Country,
    CountryTaxConfig,
    CurrencyRate,
    Customer,
    DataSource,
    Developer,
    DeveloperApplication,
    EInvoice,
    FinancialAccount,
    InsuranceClaim,
    InsurancePolicy,
    InsuranceProduct,
    IntelligenceReport,
    KYCProvider,
    KYCRecord,
    LedgerEntry,
    LoanApplication,
    LoanProduct,
    LoanRepayment,
    MarketAlert,
    MarketplaceApp,
    MarketplacePOItem,
    MarketplacePurchaseOrder,
    MarketSignal,
    MerchantCreditProfile,
    MerchantKYC,
    PaymentProvider,
    PaymentRecord,
    PaymentTransaction,
    PriceIndex,
    PricingRule,
    PricingSuggestion,
    ProcurementRecommendation,
    Product,
    ProductPriceHistory,
    RFQResponse,
    Store,
    StorePaymentMethod,
    StoreTaxRegistration,
    SupplierProfile,
    SupplierReview,
    SupportedCurrency,
    TaxTransaction,
    Translation,
    TranslationKey,
    TreasuryConfig,
    TreasuryTransaction,
    User,
    WebhookEvent,
)


def render_column(col):
    col_type = col.type
    # Handle specific types
    type_str = str(col_type)
    if isinstance(col_type, sa.Numeric):
        type_str = f"sa.Numeric(precision={col_type.precision}, scale={col_type.scale})"
    elif isinstance(col_type, sa.String):
        type_str = f"sa.String(length={col_type.length})"
    elif isinstance(col_type, sa.Enum):
        type_str = f"sa.Enum({', '.join([repr(e) for e in col_type.enums])}, name='{col_type.name}')"
    elif isinstance(col_type, JSONB):
        type_str = "postgresql.JSONB()"
    elif isinstance(col_type, UUID):
        type_str = "sa.UUID()"
    elif "TIMESTAMP" in type_str:
        type_str = "sa.TIMESTAMP()"
    else:
        # Fallback to sa.Type()
        type_str = f"sa.{type(col_type).__name__}()"
        if "()" in type_str:
            pass
        else:
            type_str += "()"

    pos_params = []
    kw_params = []

    # Handle ForeignKeys first as positional
    for fk in col.foreign_keys:
        pos_params.append(f"sa.ForeignKey('{fk.target_fullname}')")

    if col.primary_key:
        kw_params.append("primary_key=True")
    if col.nullable is False:
        kw_params.append("nullable=False")
    if col.server_default is not None:
        kw_params.append(f"server_default={repr(col.server_default.arg)}")
    if col.autoincrement is True:
        kw_params.append("autoincrement=True")
    if col.unique:
        kw_params.append("unique=True")

    all_params = pos_params + kw_params

    return f'sa.Column("{col.name}", {type_str}, {", ".join(all_params)})'


def gen_create_table(table_name):
    table = Base.metadata.tables[table_name]
    lines = [f'    op.create_table(\n        "{table_name}",']
    for col in table.columns:
        lines.append(f"        {render_column(col)},")

    # Constraints & Indexes (simplified)
    for const in table.constraints:
        if isinstance(const, sa.PrimaryKeyConstraint):
            continue
        if isinstance(const, sa.ForeignKeyConstraint):
            continue  # already in columns
        if isinstance(const, sa.UniqueConstraint):
            cols = [repr(c.name) for c in const.columns]
            lines.append(f'        sa.UniqueConstraint({", ".join(cols)}, name={repr(const.name)}),')
        if isinstance(const, sa.CheckConstraint):
            lines.append(f"        sa.CheckConstraint({repr(str(const.sqltext))}, name={repr(const.name)}),")

    lines.append("    )")

    # Indexes
    for idx in table.indexes:
        cols = [repr(c.name) for c in idx.columns]
        lines.append(f'    op.create_index("{idx.name}", "{table_name}", [{", ".join(cols)}], unique={idx.unique})')

    return "\n".join(lines)


def main():
    print('"""reconcile_schema_drift')
    print("")
    print("Revision ID: 121021f2b187")
    print("Revises: 7f8e9a0b1c2d")
    print(f'Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print("")
    print('"""')
    print("from typing import Sequence, Union")
    print("")
    print("from alembic import op")
    print("import sqlalchemy as sa")
    print("from sqlalchemy.dialects import postgresql")
    print("")
    print("")
    print("# revision identifiers, used by Alembic.")
    print("revision: str = '121021f2b187'")
    print("down_revision: Union[str, Sequence[str], None] = ('7f8e9a0b1c2d', 'c3d91f2a7b44')")
    print("branch_labels: Union[str, Sequence[str], None] = None")
    print("depends_on: Union[str, Sequence[str], None] = None")
    print("")
    print("")

    # The missing tables in CORRECT dependency order
    missing_tables = [
        "countries",
        "supported_currencies",
        "currency_rates",
        "translation_keys",
        "translations",
        "loan_products",
        "insurance_products",
        "payment_providers",
        "kyc_providers",
        "country_tax_configs",
        "store_tax_registrations",
        "tax_transactions",
        "financial_accounts",
        "ledger_entries",
        "merchant_kyc",
        "merchant_credit_profiles",
        "loan_applications",
        "loan_repayments",
        "insurance_policies",
        "insurance_claims",
        "payment_transactions",
        "treasury_configs",
        "treasury_transactions",
        "payment_records",
        "store_payment_methods",
        "kyc_records",
        "e_invoices",
        "supplier_profiles",
        "marketplace_catalog_items",
        "marketplace_purchase_orders",
        "marketplace_po_items",
        "marketplace_rfqs",
        "marketplace_rfq_responses",
        "marketplace_procurement_recommendations",
        "marketplace_supplier_reviews",
        "audit_logs",
    ]

    # AuditMixin tables
    audit_mix_tables = [
        "users",
        "stores",
        "categories",
        "products",
        "customers",
        "transactions",
        "transaction_items",
        "stock_adjustments",
        "stock_audits",
        "stock_audit_items",
        "alerts",
        "forecast_cache",
        "daily_store_summary",
        "daily_category_summary",
        "daily_sku_summary",
        "suppliers",
        "supplier_products",
        "purchase_orders",
        "purchase_order_items",
        "goods_receipt_notes",
        "barcodes",
        "receipt_templates",
        "print_jobs",
        "staff_sessions",
        "staff_daily_targets",
        "analytics_snapshots",
        "loyalty_programs",
        "customer_loyalty_accounts",
        "loyalty_transactions",
        "credit_ledger",
        "credit_transactions",
        "hsn_master",
        "store_gst_config",
        "gst_transactions",
        "gst_filing_periods",
        "whatsapp_config",
        "whatsapp_templates",
        "whatsapp_message_log",
        "store_groups",
        "store_group_memberships",
        "chain_daily_aggregates",
        "inter_store_transfer_suggestions",
        "business_events",
        "demand_sensing_log",
        "event_impact_actuals",
        "ocr_jobs",
        "ocr_job_items",
        "vision_category_tags",
        "rbac_permissions",
        "pricing_suggestions",
        "pricing_rules",
    ]

    print("def upgrade() -> None:")
    print("    bind = op.get_bind()")
    print("    insp = sa.inspect(bind)")
    print("    def has_col(table, col):")
    print("        if not insp.has_table(table): return False")
    print("        return any(c['name'] == col for c in insp.get_columns(table))")
    
    print("\n    # --- 1. Add AuditMixin columns ---")
    for t in audit_mix_tables:
        print(f'    if not has_col("{t}", "created_at"):')
        print(
            f'        op.add_column("{t}", sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))'
        )
        print(f'    if not has_col("{t}", "updated_at"):')
        print(
            f'        op.add_column("{t}", sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=True))'
        )

    print("\n    # --- 1.5. Add other missing columns ---")
    print('    if not has_col("alerts", "product_name"):')
    print('        op.add_column("alerts", sa.Column("product_name", sa.String(), nullable=True))')

    print("\n    # --- 2. Create missing tables ---")
    for t in missing_tables:
        try:
            print(f'    if not insp.has_table("{t}"):')
            table_def = gen_create_table(t)
            indented = "    " + table_def.replace("\\n", "\\n    ")
            print(indented)
            print("")
        except KeyError:
            print(f"    # Table {t} not found in metadata")

    print("\ndef downgrade() -> None:")
    print("    bind = op.get_bind()")
    print("    insp = sa.inspect(bind)")
    print("    def has_col(table, col):")
    print("        if not insp.has_table(table): return False")
    print("        return any(c['name'] == col for c in insp.get_columns(table))")

    print("\n    # --- Drop missing tables ---")
    for t in reversed(missing_tables):
        print(f'    if insp.has_table("{t}"):')
        print(f'        op.drop_table("{t}")')

    print("\n    # --- Remove AuditMixin columns ---")
    print('    if has_col("alerts", "product_name"):')
    print('        op.drop_column("alerts", "product_name")')
    for t in audit_mix_tables:
        print(f'    if has_col("{t}", "updated_at"):')
        print(f'        op.drop_column("{t}", "updated_at")')
        print(f'    if has_col("{t}", "created_at"):')
        print(f'        op.drop_column("{t}", "created_at")')


if __name__ == "__main__":
    main()
