from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    organization: Mapped[str | None] = mapped_column(String(128))
    api_key_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DeveloperApplication(Base):
    __tablename__ = "developer_applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(Integer, ForeignKey("developers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    app_type: Mapped[str] = mapped_column(
        SQLEnum("WEB", "MOBILE", "BACKEND", "INTEGRATION", name="app_type_enum"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    client_secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uris: Mapped[dict | None] = mapped_column(JSONB)
    scopes: Mapped[dict | None] = mapped_column(JSONB)
    tier: Mapped[str] = mapped_column(
        SQLEnum("FREE", "GROWTH", "BUSINESS", "ENTERPRISE", name="app_tier_enum"),
        server_default="FREE",
        nullable=False,
    )
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    monthly_quota: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        SQLEnum("ACTIVE", "SUSPENDED", "REVOKED", name="app_status_enum"), server_default="ACTIVE", nullable=False
    )
    webhook_url: Mapped[str | None] = mapped_column(String(512))
    webhook_secret: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("idx_dev_app_client_id", "client_id", unique=True),)


class MarketplaceApp(Base):
    __tablename__ = "marketplace_apps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    developer_app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("developer_applications.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    icon_url: Mapped[str | None] = mapped_column(String(512))
    screenshots: Mapped[dict | None] = mapped_column(JSONB)
    pricing_model: Mapped[str] = mapped_column(
        SQLEnum("FREE", "FREEMIUM", "PAID", "SUBSCRIPTION", name="pricing_model_enum"), nullable=False
    )
    price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    security_scan_status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "PASSED", "FAILED", name="security_scan_status_enum"),
        server_default="PENDING",
        nullable=False,
    )
    review_status: Mapped[str] = mapped_column(
        SQLEnum("SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", name="review_status_enum"),
        server_default="SUBMITTED",
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class APIUsageRecord(Base):
    __tablename__ = "api_usage_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("developer_applications.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    minute_bucket: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2))
    p99_latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2))
    bytes_transferred: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (Index("idx_usage_app_minute", "app_id", "minute_bucket"),)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("developer_applications.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "DELIVERED", "FAILED", "DEAD_LETTERED", name="webhook_status_enum"),
        server_default="PENDING",
        nullable=False,
    )
    delivery_url: Mapped[str] = mapped_column(String(512), nullable=False)
    last_response_code: Mapped[int | None] = mapped_column(Integer)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))


class MarketSignal(Base):
    __tablename__ = "market_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    category_id: Mapped[int | None] = mapped_column(Integer)
    region_code: Mapped[str | None] = mapped_column(String(10))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PriceIndex(Base):
    __tablename__ = "price_indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer)
    region_code: Mapped[str | None] = mapped_column(String(10))
    index_value: Mapped[float | None] = mapped_column(Float)
    computation_method: Mapped[str | None] = mapped_column(String(100))
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    base_period: Mapped[str | None] = mapped_column(String(20))


class MarketAlert(Base):
    __tablename__ = "market_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer)
    alert_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
