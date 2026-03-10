import uuid
from datetime import date, datetime, time, timezone
from typing import Optional

from flask import Blueprint
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

models_bp = Blueprint("models", __name__)


class Base(DeclarativeBase):
    pass


class AuditMixin:
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="USER")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class User(Base, AuditMixin):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mobile_number: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(SQLEnum("owner", "staff", name="user_role_enum"))
    store_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stores.store_id", use_alter=True, name="fk_users_store_id"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Security & MFA
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)


class Store(Base, AuditMixin):
    __tablename__ = "stores"

    store_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"))
    store_name: Mapped[str | None] = mapped_column(String)
    store_type: Mapped[str | None] = mapped_column(
        SQLEnum("grocery", "pharmacy", "general", "electronics", "clothing", "other", name="store_type_enum")
    )
    city: Mapped[str | None] = mapped_column(String)
    state: Mapped[str | None] = mapped_column(String)
    gst_number: Mapped[str | None] = mapped_column(String)
    currency_symbol: Mapped[str | None] = mapped_column(String, default="INR")
    working_days: Mapped[dict | None] = mapped_column(JSONB)
    opening_time: Mapped[time | None] = mapped_column(Time)
    closing_time: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str | None] = mapped_column(String)


class Category(Base, AuditMixin):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    name: Mapped[str | None] = mapped_column(String)
    color_tag: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    gst_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), default=18)


class Product(Base, AuditMixin):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.category_id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    sku_code: Mapped[str | None] = mapped_column(String(50))
    uom: Mapped[str | None] = mapped_column(SQLEnum("pieces", "kg", "litre", "pack", name="product_uom_enum"))
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    current_stock: Mapped[float | None] = mapped_column(Numeric(12, 3), default=0)
    reorder_level: Mapped[float | None] = mapped_column(Numeric(12, 3), default=0)
    supplier_name: Mapped[str | None] = mapped_column(String)
    barcode: Mapped[str | None] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, default=3)

    # GST Fields
    hsn_code: Mapped[str | None] = mapped_column(String(8), ForeignKey("hsn_master.hsn_code"), nullable=True)
    gst_category: Mapped[str | None] = mapped_column(
        String(16),
        CheckConstraint("gst_category IN ('EXEMPT', 'ZERO', 'REGULAR')"),
        server_default="REGULAR",
        default="REGULAR",
    )

    __table_args__ = (
        Index("idx_products_store_sku", "store_id", "sku_code", unique=True),
        Index("idx_products_store_active_stock", "store_id", "is_active", "current_stock"),
    )


class ProductPriceHistory(Base):
    __tablename__ = "product_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=True)
    old_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    new_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # Legacy fields kept for backward compat
    cost_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    selling_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    changed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)


class PricingSuggestion(Base, AuditMixin):
    __tablename__ = "pricing_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.product_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    suggested_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    current_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_change_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))
    reason: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("status IN ('PENDING','APPLIED','DISMISSED')", name="chk_pricing_suggestion_status"),
        server_default="PENDING",
        default="PENDING",
    )
    actioned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("idx_pricing_suggestions_store_status", "store_id", "status"),
        Index("idx_pricing_suggestions_product_created", "product_id", "created_at"),
    )


class PricingRule(Base, AuditMixin):
    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    rule_type: Mapped[str | None] = mapped_column(String(32))
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    __table_args__ = (Index("idx_pricing_rules_store_active", "store_id", "is_active"),)


class Customer(Base, AuditMixin):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    gender: Mapped[str | None] = mapped_column(SQLEnum("male", "female", "other", name="customer_gender_enum"))
    birth_date: Mapped[date | None] = mapped_column(Date)
    address: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)


class Transaction(Base, AuditMixin):
    __tablename__ = "transactions"

    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.customer_id"), nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(SQLEnum("CASH", "UPI", "CARD", "CREDIT", name="payment_mode_enum"))
    notes: Mapped[str | None] = mapped_column(String(200))
    is_return: Mapped[bool] = mapped_column(Boolean, default=False)
    original_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_sessions.id"), nullable=True
    )
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    __table_args__ = (
        Index("idx_transactions_store_created", "store_id", text("created_at DESC")),
        Index("idx_transactions_session_id", "session_id"),
    )


class TransactionItem(Base, AuditMixin):
    __tablename__ = "transaction_items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id")
    )
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 3))
    selling_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    original_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0)
    cost_price_at_time: Mapped[float | None] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        Index("idx_transaction_items_transaction_id", "transaction_id"),
        Index("idx_transaction_items_product_id", "product_id"),
    )


class StockAdjustment(Base, AuditMixin):
    __tablename__ = "stock_adjustments"

    adj_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    quantity_added: Mapped[float | None] = mapped_column(Numeric(12, 3))
    purchase_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    adjusted_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"))
    adjusted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    reason: Mapped[str | None] = mapped_column(String)


class StockAudit(Base, AuditMixin):
    __tablename__ = "stock_audits"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    audit_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    conducted_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"))
    status: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(String)


class StockAuditItem(Base, AuditMixin):
    __tablename__ = "stock_audit_items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stock_audits.audit_id"))
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    expected_stock: Mapped[float | None] = mapped_column(Numeric(12, 3))
    actual_stock: Mapped[float | None] = mapped_column(Numeric(12, 3))
    discrepancy: Mapped[float | None] = mapped_column(Numeric(12, 3))


class Alert(Base, AuditMixin):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    alert_type: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[str | None] = mapped_column(
        SQLEnum("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", name="alert_priority_enum")
    )
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    __table_args__ = (Index("idx_alerts_store_resolved_priority", "store_id", "resolved_at", "priority"),)


class ForecastCache(Base, AuditMixin):
    __tablename__ = "forecast_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"), nullable=True)
    forecast_date: Mapped[date | None] = mapped_column(Date)
    forecast_value: Mapped[float | None] = mapped_column(Numeric(12, 2))
    lower_bound: Mapped[float | None] = mapped_column(Numeric(12, 2))
    upper_bound: Mapped[float | None] = mapped_column(Numeric(12, 2))
    regime: Mapped[str | None] = mapped_column(String(20))
    model_type: Mapped[str | None] = mapped_column(String(30))
    training_window_days: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("store_id", "product_id", "forecast_date", name="uq_forecast_cache_store_product_date"),
    )


class DailyStoreSummary(Base, AuditMixin):
    __tablename__ = "daily_store_summary"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    transaction_count: Mapped[int | None] = mapped_column(Integer)
    avg_basket: Mapped[float | None] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[float | None] = mapped_column(Numeric(12, 3))

    __table_args__ = (Index("idx_daily_store_summary_store_date", "store_id", text("date DESC")),)


class DailyCategorySummary(Base, AuditMixin):
    __tablename__ = "daily_category_summary"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[float | None] = mapped_column(Numeric(12, 3))


class DailySkuSummary(Base, AuditMixin):
    __tablename__ = "daily_sku_summary"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[float | None] = mapped_column(Numeric(12, 3))
    avg_selling_price: Mapped[float | None] = mapped_column(Numeric(12, 2))

    __table_args__ = (Index("idx_daily_sku_summary_store_product_date", "store_id", "product_id", text("date DESC")),)


class Supplier(Base, AuditMixin):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(Text)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupplierProduct(Base, AuditMixin):
    __tablename__ = "supplier_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.product_id"))
    quoted_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    is_preferred_supplier: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),)


class PurchaseOrder(Base, AuditMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    status: Mapped[str | None] = mapped_column(String(16), default="DRAFT")
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"))


class PurchaseOrderItem(Base, AuditMixin):
    __tablename__ = "purchase_order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.product_id"))
    ordered_qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    received_qty: Mapped[float | None] = mapped_column(Numeric(12, 3), default=0)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)


class GoodsReceiptNote(Base, AuditMixin):
    __tablename__ = "goods_receipt_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"))
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"))
    received_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"))
    received_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    notes: Mapped[str | None] = mapped_column(Text)


class Barcode(Base, AuditMixin):
    __tablename__ = "barcodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"), nullable=False)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    barcode_value: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    barcode_type: Mapped[str | None] = mapped_column(String(16), default="EAN13")

    __table_args__ = (Index("idx_barcodes_store_product", "store_id", "product_id"),)


class ReceiptTemplate(Base, AuditMixin):
    __tablename__ = "receipt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False, unique=True)
    header_text: Mapped[str | None] = mapped_column(Text)
    footer_text: Mapped[str | None] = mapped_column(Text)
    show_gstin: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_width_mm: Mapped[int] = mapped_column(Integer, default=80)


class PrintJob(Base, AuditMixin):
    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=True
    )
    job_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    payload: Mapped[dict | None] = mapped_column(JSONB)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)

    __table_args__ = (Index("idx_print_jobs_store_status", "store_id", "status"),)


class StaffSession(Base, AuditMixin):
    __tablename__ = "staff_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="OPEN", nullable=False)
    target_revenue: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    __table_args__ = (
        # Used for check constraints in migrations
    )


class StaffDailyTarget(Base, AuditMixin):
    __tablename__ = "staff_daily_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue_target: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    transaction_count_target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("store_id", "user_id", "target_date", name="uq_staff_daily_target_store_user_date"),
    )


class AnalyticsSnapshot(Base, AuditMixin):
    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False, unique=True)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    built_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    size_bytes: Mapped[int | None] = mapped_column(Integer)


class LoyaltyProgram(Base, AuditMixin):
    __tablename__ = "loyalty_programs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    points_per_rupee: Mapped[float | None] = mapped_column(Numeric(6, 4), default=1.0, server_default="1.0")
    redemption_rate: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.1, server_default="0.1")
    min_redemption_points: Mapped[int | None] = mapped_column(Integer, default=100, server_default="100")
    expiry_days: Mapped[int | None] = mapped_column(Integer, default=365, server_default="365")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CustomerLoyaltyAccount(Base, AuditMixin):
    __tablename__ = "customer_loyalty_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.customer_id"), unique=True, nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    total_points: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    redeemable_points: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    lifetime_earned: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    last_activity_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class LoyaltyTransaction(Base, AuditMixin):
    __tablename__ = "loyalty_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_loyalty_accounts.id"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    points: Mapped[float | None] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (CheckConstraint("type IN ('EARN', 'REDEEM', 'EXPIRE', 'ADJUST')", name="chk_loyalty_txn_type"),)


class CreditLedger(Base, AuditMixin):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    balance: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    credit_limit: Mapped[float | None] = mapped_column(Numeric(12, 2), default=0, server_default="0")

    __table_args__ = (UniqueConstraint("customer_id", "store_id", name="uq_credit_ledger_cust_store"),)


class CreditTransaction(Base, AuditMixin):
    __tablename__ = "credit_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ledger_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("credit_ledger.id"), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String)

    __table_args__ = (CheckConstraint("type IN ('CREDIT_SALE', 'REPAYMENT', 'ADJUSTMENT')", name="chk_credit_tx_type"),)


class HSNMaster(Base, AuditMixin):
    __tablename__ = "hsn_master"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hsn_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_gst_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))


class StoreGSTConfig(Base, AuditMixin):
    __tablename__ = "store_gst_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    registration_type: Mapped[str | None] = mapped_column(
        String(16),
        CheckConstraint("registration_type IN ('REGULAR', 'COMPOSITION', 'UNREGISTERED')"),
        server_default="REGULAR",
        default="REGULAR",
    )
    state_code: Mapped[str | None] = mapped_column(String(2))
    is_gst_enabled: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)


class GSTTransaction(Base, AuditMixin):
    __tablename__ = "gst_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), unique=True, nullable=False
    )
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    taxable_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    cgst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    sgst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    igst_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_gst: Mapped[float | None] = mapped_column(Numeric(12, 2))
    hsn_breakdown: Mapped[dict | None] = mapped_column(JSONB)


class GSTFilingPeriod(Base, AuditMixin):
    __tablename__ = "gst_filing_periods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    total_taxable: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_cgst: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_sgst: Mapped[float | None] = mapped_column(Numeric(12, 2))
    total_igst: Mapped[float | None] = mapped_column(Numeric(12, 2))
    invoice_count: Mapped[int | None] = mapped_column(Integer)
    gstr1_json_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    compiled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), server_default="DRAFT", default="DRAFT")

    __table_args__ = (UniqueConstraint("store_id", "period", name="uq_store_period"),)


# ---------------------------------------------------------------------------
# WHATSAPP INTEGRATION MODELS
# ---------------------------------------------------------------------------


class WhatsAppConfig(Base, AuditMixin):
    __tablename__ = "whatsapp_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False, unique=True)
    phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_verify_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    waba_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class WhatsAppTemplate(Base, AuditMixin):
    __tablename__ = "whatsapp_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    template_name: Mapped[str] = mapped_column(String(128), nullable=False)
    template_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str] = mapped_column(String(10), server_default="en", default="en")
    variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)


class WhatsAppMessageLog(Base, AuditMixin):
    __tablename__ = "whatsapp_message_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), server_default="OUT", default="OUT")
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="QUEUED", default="QUEUED")
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# CHAIN OWNERSHIP / MULTI-STORE MODELS
# ---------------------------------------------------------------------------


class StoreGroup(Base, AuditMixin):
    __tablename__ = "store_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False)


class StoreGroupMembership(Base, AuditMixin):
    __tablename__ = "store_group_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("store_groups.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    manager_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (UniqueConstraint("group_id", "store_id", name="uq_group_store"),)


class ChainDailyAggregate(Base, AuditMixin):
    __tablename__ = "chain_daily_aggregates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("store_groups.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    profit: Mapped[float | None] = mapped_column(Numeric(12, 2))
    transaction_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("group_id", "store_id", "date", name="uq_chain_agg_group_store_date"),)


class InterStoreTransferSuggestion(Base, AuditMixin):
    __tablename__ = "inter_store_transfer_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("store_groups.id"), nullable=False)
    from_store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    to_store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.product_id"), nullable=False)
    suggested_qty: Mapped[float | None] = mapped_column(Numeric(12, 3))
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING", default="PENDING")


# ── Events Models ─────────────────────────────────────────────────────────────


class BusinessEvent(Base, AuditMixin):
    __tablename__ = "business_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    event_name: Mapped[str | None] = mapped_column(String(128))
    event_type: Mapped[str | None] = mapped_column(
        String(32), CheckConstraint("event_type IN ('HOLIDAY', 'FESTIVAL', 'PROMOTION', 'SALE_DAY', 'CLOSURE')")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_impact_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(128))


class DemandSensingLog(Base, AuditMixin):
    __tablename__ = "demand_sensing_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    date: Mapped[date] = mapped_column(Date, nullable=True)
    actual_demand: Mapped[float | None] = mapped_column(Numeric(12, 3))
    base_forecast: Mapped[float | None] = mapped_column(Numeric(12, 3))
    event_adjusted_forecast: Mapped[float | None] = mapped_column(Numeric(12, 3))
    active_events: Mapped[dict | None] = mapped_column(JSONB)


class EventImpactActuals(Base, AuditMixin):
    __tablename__ = "event_impact_actuals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("business_events.id"))
    product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    actual_impact_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))
    measured_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


# ── Vision / OCR Models ───────────────────────────────────────────────────────


class OcrJob(Base, AuditMixin):
    __tablename__ = "ocr_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    image_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("status IN ('QUEUED', 'PROCESSING', 'REVIEW', 'APPLIED', 'FAILED')"),
        default="QUEUED",
    )
    raw_ocr_text: Mapped[str | None] = mapped_column(Text)
    extracted_items: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class OcrJobItem(Base, AuditMixin):
    __tablename__ = "ocr_job_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ocr_jobs.id"))
    raw_text: Mapped[str | None] = mapped_column(String(256))
    matched_product_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("products.product_id"))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class VisionCategoryTag(Base, AuditMixin):
    __tablename__ = "vision_category_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ocr_jobs.id"))
    tag: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))


# ── RBAC Permissions Model ────────────────────────────────────────────────────


class RBACPermission(Base, AuditMixin):
    __tablename__ = "rbac_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("role", "resource", "action", name="uq_rbac_role_resource_action"),
        Index("idx_rbac_permissions_role", "role"),
    )


# ── Missing Models ────────────────────────────────────────────────────────────

from .expansion_models import (
    Country,
    CountryTaxConfig,
    CurrencyRate,
    EInvoice,
    KYCProvider,
    KYCRecord,
    PaymentProvider,
    PaymentRecord,
    StorePaymentMethod,
    StoreTaxRegistration,
    SupportedCurrency,
    TaxTransaction,
    Translation,
    TranslationKey,
)
from .finance_models import (
    FinancialAccount,
    InsuranceClaim,
    InsurancePolicy,
    InsuranceProduct,
    LedgerEntry,
    LoanApplication,
    LoanProduct,
    LoanRepayment,
    MerchantCreditProfile,
    MerchantKYC,
    PaymentTransaction,
    TreasuryConfig,
    TreasuryTransaction,
)
from .marketplace_models import (
    RFQ,
    CatalogItem,
    MarketplacePOItem,
    MarketplacePurchaseOrder,
    ProcurementRecommendation,
    RFQResponse,
    SupplierProfile,
    SupplierReview,
)
from .missing_models import (
    APIUsageRecord,
    DataSource,
    Developer,
    DeveloperApplication,
    IntelligenceReport,
    MarketAlert,
    MarketplaceApp,
    MarketSignal,
    PriceIndex,
    WebhookEvent,
)
