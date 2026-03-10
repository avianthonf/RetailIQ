import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class SupplierProfile(Base):
    """Extended supplier with marketplace capabilities."""

    __tablename__ = "supplier_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), unique=True)
    business_name: Mapped[str] = mapped_column(String(256), nullable=False)
    business_type: Mapped[str] = mapped_column(
        SQLEnum("MANUFACTURER", "WHOLESALER", "DISTRIBUTOR", "ARTISAN", name="supplier_business_type_enum"),
        nullable=False,
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))  # 0.00 - 5.00
    total_orders_fulfilled: Mapped[int] = mapped_column(Integer, default=0)
    fulfillment_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))  # percentage
    avg_ship_days: Mapped[float | None] = mapped_column(Numeric(4, 1))
    return_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))
    categories: Mapped[dict | None] = mapped_column(JSONB)  # ARRAY mapped to JSON for SQLite compat
    regions_served: Mapped[dict | None] = mapped_column(JSONB)  # ARRAY mapped to JSON for SQLite compat
    min_order_value: Mapped[float | None] = mapped_column(Numeric(12, 2))
    payment_terms: Mapped[dict | None] = mapped_column(JSONB)  # net30, net60, etc.
    logo_url: Mapped[str | None] = mapped_column(String(512))
    catalog_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class CatalogItem(Base):
    """Product listed on the B2B marketplace."""

    __tablename__ = "marketplace_catalog_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    supplier_profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("supplier_profiles.id"), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(128))
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    moq: Mapped[int] = mapped_column(Integer, default=1)  # minimum order quantity
    case_pack: Mapped[int] = mapped_column(Integer, default=1)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=3)
    images: Mapped[dict | None] = mapped_column(JSONB)  # ARRAY mapped to JSON
    specifications: Mapped[dict | None] = mapped_column(JSONB)
    bulk_pricing: Mapped[dict | None] = mapped_column(JSONB)  # [{"qty": 100, "price": 9.50}, ...]
    available_quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_catalog_items_supplier_active", "supplier_profile_id", "is_active"),
    )


class MarketplacePurchaseOrder(Base):
    """B2B purchase order between merchant and supplier."""

    __tablename__ = "marketplace_purchase_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    supplier_profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("supplier_profiles.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "DRAFT",
            "SUBMITTED",
            "ACKNOWLEDGED",
            "PROCESSING",
            "SHIPPED",
            "PARTIALLY_DELIVERED",
            "DELIVERED",
            "DISPUTED",
            "CANCELLED",
            "RETURNED",
            name="marketplace_po_status_enum",
        ),
        default="DRAFT",
    )
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tax: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    shipping_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    payment_terms: Mapped[str | None] = mapped_column(String(32))  # net30, net60, prepaid
    payment_status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "PARTIALLY_PAID", "PAID", "OVERDUE", name="marketplace_po_payment_status_enum"),
        default="PENDING",
    )
    financed_by_retailiq: Mapped[bool] = mapped_column(Boolean, default=False)
    loan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("loan_applications.id"), nullable=True)
    shipping_tracking: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    expected_delivery: Mapped[date | None] = mapped_column(Date)
    actual_delivery: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        Index("idx_marketplace_po_merchant_status", "merchant_id", "status"),
        Index("idx_marketplace_po_supplier_status", "supplier_profile_id", "status"),
    )


class MarketplacePOItem(Base):
    """Line items on a marketplace PO."""

    __tablename__ = "marketplace_po_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("marketplace_purchase_orders.id"), nullable=False)
    catalog_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("marketplace_catalog_items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)


class RFQ(Base):
    """Request for Quote."""

    __tablename__ = "marketplace_rfqs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    items: Mapped[dict] = mapped_column(JSONB, nullable=False)  # [{"category": "Electronics", "description": "...", "quantity": 100}]
    status: Mapped[str] = mapped_column(
        SQLEnum("OPEN", "CLOSED", "CANCELLED", "FULFILLED", name="rfq_status_enum"), default="OPEN"
    )
    matched_suppliers_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class RFQResponse(Base):
    """Supplier response to RFQ."""

    __tablename__ = "marketplace_rfq_responses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rfq_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("marketplace_rfqs.id"), nullable=False)
    supplier_profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("supplier_profiles.id"), nullable=False)
    quoted_items: Mapped[dict] = mapped_column(JSONB, nullable=False)  # [{"rfq_item_id": 1, "unit_price": 10.50, "catalog_item_id": Optional}]
    total_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_days: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "ACCEPTED", "REJECTED", "EXPIRED", name="rfq_response_status_enum"), default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("rfq_id", "supplier_profile_id", name="uq_rfq_supplier"),
    )


class ProcurementRecommendation(Base):
    """AI procurement suggestions."""

    __tablename__ = "marketplace_procurement_recommendations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    product_category: Mapped[str | None] = mapped_column(String(128))
    recommended_items: Mapped[dict] = mapped_column(JSONB, nullable=False)  # [{"catalog_item_id": 1, "qty": 50, "reason": "Low stock"}]
    recommended_supplier_ids: Mapped[dict | None] = mapped_column(JSONB)  # ARRAY of BigInteger
    estimated_savings: Mapped[float | None] = mapped_column(Numeric(12, 2))
    urgency: Mapped[str] = mapped_column(
        SQLEnum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="procurement_urgency_enum"), default="LOW"
    )
    trigger_event: Mapped[str | None] = mapped_column(String(64))  # 'low_stock', 'price_drop', 'seasonal_prep'
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    acted_upon: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_proc_rec_merchant_urgency", "merchant_id", "urgency"),
    )


class SupplierReview(Base):
    """Merchant reviews of suppliers."""

    __tablename__ = "marketplace_supplier_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    supplier_profile_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("supplier_profiles.id"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("marketplace_purchase_orders.id"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    review_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="chk_supplier_review_rating"),
        UniqueConstraint("merchant_id", "order_id", name="uq_merchant_order_review"),
    )
