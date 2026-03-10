from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, Float, Text, DateTime, JSON, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    organization: Mapped[Optional[str]] = mapped_column(String(255))
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255))

class DeveloperApplication(Base):
    __tablename__ = "developer_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    developer_id: Mapped[int] = mapped_column(Integer, ForeignKey("developers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    app_type: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uris: Mapped[Optional[dict]] = mapped_column(JSON)
    scopes: Mapped[Optional[dict]] = mapped_column(JSON)
    rate_limit_rpm: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    tier: Mapped[Optional[str]] = mapped_column(String(50))
    webhook_url: Mapped[Optional[str]] = mapped_column(String(255))
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255))

class MarketplaceApp(Base):
    __tablename__ = "marketplace_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tagline: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[Optional[float]] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(50), default="PENDING")

class APIUsageRecord(Base):
    __tablename__ = "api_usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, ForeignKey("developer_applications.id"))
    endpoint: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    bytes_transferred: Mapped[int] = mapped_column(Integer, default=0)
    minute_bucket: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, ForeignKey("developer_applications.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50))
    delivery_url: Mapped[str] = mapped_column(String(255))
    last_response_code: Mapped[Optional[int]] = mapped_column(Integer)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))

class MarketSignal(Base):
    __tablename__ = "market_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer)
    category_id: Mapped[Optional[int]] = mapped_column(Integer)
    region_code: Mapped[Optional[str]] = mapped_column(String(10))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class PriceIndex(Base):
    __tablename__ = "price_indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer)
    region_code: Mapped[Optional[str]] = mapped_column(String(10))
    index_value: Mapped[Optional[float]] = mapped_column(Float)
    computation_method: Mapped[Optional[str]] = mapped_column(String(100))
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    base_period: Mapped[Optional[str]] = mapped_column(String(20))

class MarketAlert(Base):
    __tablename__ = "market_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer)
    alert_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


