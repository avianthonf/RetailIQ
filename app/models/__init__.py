import uuid
from datetime import datetime, time, date, timezone
from typing import Optional

from flask import Blueprint
from sqlalchemy import (
    String, Integer, Boolean, Numeric, TIMESTAMP, ForeignKey,
    Enum as SQLEnum, Text, Time, Date, Index, text, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID

models_bp = Blueprint('models', __name__)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mobile_number: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    password_hash: Mapped[Optional[str]] = mapped_column(String)
    role: Mapped[Optional[str]] = mapped_column(SQLEnum('owner', 'staff', name='user_role_enum'))
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

class Store(Base):
    __tablename__ = 'stores'

    store_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.user_id'))
    store_name: Mapped[Optional[str]] = mapped_column(String)
    store_type: Mapped[Optional[str]] = mapped_column(SQLEnum('grocery', 'pharmacy', 'general', 'electronics', 'clothing', 'other', name='store_type_enum'))
    city: Mapped[Optional[str]] = mapped_column(String)
    state: Mapped[Optional[str]] = mapped_column(String)
    gst_number: Mapped[Optional[str]] = mapped_column(String)
    currency_symbol: Mapped[Optional[str]] = mapped_column(String, default='INR')
    working_days: Mapped[Optional[dict]] = mapped_column(JSONB)
    opening_time: Mapped[Optional[time]] = mapped_column(Time)
    closing_time: Mapped[Optional[time]] = mapped_column(Time)
    timezone: Mapped[Optional[str]] = mapped_column(String)

class Category(Base):
    __tablename__ = 'categories'

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    name: Mapped[Optional[str]] = mapped_column(String)
    color_tag: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    gst_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), default=18)

class Product(Base):
    __tablename__ = 'products'

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('categories.category_id'))
    name: Mapped[str] = mapped_column(String, nullable=False)
    sku_code: Mapped[Optional[str]] = mapped_column(String(50))
    uom: Mapped[Optional[str]] = mapped_column(SQLEnum('pieces', 'kg', 'litre', 'pack', name='product_uom_enum'))
    cost_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    current_stock: Mapped[Optional[float]] = mapped_column(Numeric(12, 3), default=0)
    reorder_level: Mapped[Optional[float]] = mapped_column(Numeric(12, 3), default=0)
    supplier_name: Mapped[Optional[str]] = mapped_column(String)
    barcode: Mapped[Optional[str]] = mapped_column(String)
    image_url: Mapped[Optional[str]] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, default=3)

    __table_args__ = (
        Index('idx_products_store_sku', 'store_id', 'sku_code', unique=True),
        Index('idx_products_store_active_stock', 'store_id', 'is_active', 'current_stock'),
    )

class ProductPriceHistory(Base):
    __tablename__ = 'product_price_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'))
    cost_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    changed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    changed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.user_id'))

class Customer(Base):
    __tablename__ = 'customers'

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    mobile_number: Mapped[Optional[str]] = mapped_column(String(15))
    name: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    gender: Mapped[Optional[str]] = mapped_column(SQLEnum('male', 'female', 'other', name='customer_gender_enum'))
    birth_date: Mapped[Optional[date]] = mapped_column(Date)
    address: Mapped[Optional[str]] = mapped_column(String)
    notes: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

class Transaction(Base):
    __tablename__ = 'transactions'

    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('customers.customer_id'), nullable=True)
    payment_mode: Mapped[Optional[str]] = mapped_column(SQLEnum('CASH', 'UPI', 'CARD', 'CREDIT', name='payment_mode_enum'))
    notes: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    is_return: Mapped[bool] = mapped_column(Boolean, default=False)
    original_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'), nullable=True)

    __table_args__ = (
        Index('idx_transactions_store_created', 'store_id', text('created_at DESC')),
    )

class TransactionItem(Base):
    __tablename__ = 'transaction_items'

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'))
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    selling_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    original_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), default=0)
    cost_price_at_time: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        Index('idx_transaction_items_transaction_id', 'transaction_id'),
        Index('idx_transaction_items_product_id', 'product_id'),
    )

class StockAdjustment(Base):
    __tablename__ = 'stock_adjustments'

    adj_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'))
    quantity_added: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    purchase_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    adjusted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.user_id'))
    adjusted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    reason: Mapped[Optional[str]] = mapped_column(String)

class StockAudit(Base):
    __tablename__ = 'stock_audits'

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    audit_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    conducted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('users.user_id'))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(String)

class StockAuditItem(Base):
    __tablename__ = 'stock_audit_items'

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stock_audits.audit_id'))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'))
    expected_stock: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    actual_stock: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    discrepancy: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))

class Alert(Base):
    __tablename__ = 'alerts'

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    alert_type: Mapped[Optional[str]] = mapped_column(String(50))
    priority: Mapped[Optional[str]] = mapped_column(SQLEnum('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO', name='alert_priority_enum'))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index('idx_alerts_store_resolved_priority', 'store_id', 'resolved_at', 'priority'),
    )

class ForecastCache(Base):
    __tablename__ = 'forecast_cache'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stores.store_id'))
    product_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('products.product_id'), nullable=True)
    forecast_date: Mapped[Optional[date]] = mapped_column(Date)
    forecast_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    lower_bound: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    upper_bound: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    regime: Mapped[Optional[str]] = mapped_column(String(20))
    model_type: Mapped[Optional[str]] = mapped_column(String(30))
    training_window_days: Mapped[Optional[int]] = mapped_column(Integer)
    generated_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    __table_args__ = (
        UniqueConstraint('store_id', 'product_id', 'forecast_date',
                         name='uq_forecast_cache_store_product_date'),
    )


class DailyStoreSummary(Base):
    __tablename__ = 'daily_store_summary'

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    profit: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    transaction_count: Mapped[Optional[int]] = mapped_column(Integer)
    avg_basket: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))

    __table_args__ = (
        Index('idx_daily_store_summary_store_date', 'store_id', text('date DESC')),
    )

class DailyCategorySummary(Base):
    __tablename__ = 'daily_category_summary'

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    profit: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))

class DailySkuSummary(Base):
    __tablename__ = 'daily_sku_summary'

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revenue: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    profit: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    units_sold: Mapped[Optional[float]] = mapped_column(Numeric(12, 3))
    avg_selling_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        Index('idx_daily_sku_summary_store_product_date', 'store_id', 'product_id', text('date DESC')),
    )
