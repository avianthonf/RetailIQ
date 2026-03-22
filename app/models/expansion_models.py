"""
Multi-Country Expansion Models (Team 9)

Provides database models for:
- Country configuration and data residency
- Multi-currency exchange rates
- Country-specific tax configuration
- Local payment method tracking
- KYC verification records
- E-invoicing audit trail
"""

import uuid
from datetime import date, datetime, timezone

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
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

# ---------------------------------------------------------------------------
# Country & Locale Configuration
# ---------------------------------------------------------------------------


class Country(Base):
    """Master list of supported countries with locale defaults."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)  # ISO 3166-1 alpha-2
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217
    default_locale: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. en-IN, pt-BR
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. Asia/Kolkata
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1/2/3 launch tier
    tax_system: Mapped[str] = mapped_column(String(32), nullable=False)  # GST, VAT, SALES_TAX, IVA
    data_residency_required: Mapped[bool] = mapped_column(Boolean, default=False)
    data_residency_region: Mapped[str | None] = mapped_column(String(32))  # AWS region / CockroachDB locality
    regulatory_body: Mapped[str | None] = mapped_column(String(128))
    phone_code: Mapped[str | None] = mapped_column(String(5))
    date_format: Mapped[str] = mapped_column(String(16), default="YYYY-MM-DD")
    number_format: Mapped[str] = mapped_column(String(16), default="1,234.56")  # 1.234,56 for DE/BR
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    go_live_date: Mapped[date | None] = mapped_column(Date)
    config: Mapped[dict | None] = mapped_column(JSONB)  # country-specific extras


class CurrencyRate(Base):
    """Daily exchange rates relative to USD base."""

    __tablename__ = "currency_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="ECB")  # ECB, FIXER, OPENEX
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_currency_rate_pair_date"),
        Index("idx_currency_rates_date", "rate_date"),
    )


class SupportedCurrency(Base):
    """List of actively supported currencies with display metadata."""

    __tablename__ = "supported_currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # ISO 4217
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, default=2)
    symbol_position: Mapped[str] = mapped_column(String(8), default="before")  # before / after
    thousands_sep: Mapped[str] = mapped_column(String(1), default=",")
    decimal_sep: Mapped[str] = mapped_column(String(1), default=".")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Multi-Country Tax Configuration
# ---------------------------------------------------------------------------


class CountryTaxConfig(Base):
    """Per-country tax system configuration — extends existing GST module."""

    __tablename__ = "country_tax_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(32), nullable=False)  # GST, VAT, SALES_TAX, IVA
    standard_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    reduced_rates: Mapped[dict | None] = mapped_column(JSONB)  # [5, 12, 18, 28] for IN; [7, 19] for DE
    zero_rated_categories: Mapped[dict | None] = mapped_column(JSONB)
    exempt_categories: Mapped[dict | None] = mapped_column(JSONB)
    filing_frequency: Mapped[str] = mapped_column(String(16), default="MONTHLY")  # MONTHLY, QUARTERLY
    filing_format: Mapped[str | None] = mapped_column(String(64))  # GSTR-1, HMRC MTD, GoBD
    tax_id_label: Mapped[str] = mapped_column(String(32), default="TAX_ID")  # GSTIN, VAT_NUMBER, EIN, CNPJ
    tax_id_regex: Mapped[str | None] = mapped_column(String(256))  # validation regex
    has_subnational_tax: Mapped[bool] = mapped_column(Boolean, default=False)  # US state sales tax
    subnational_config: Mapped[dict | None] = mapped_column(JSONB)  # state/province-level overrides
    e_invoice_required: Mapped[bool] = mapped_column(Boolean, default=False)
    e_invoice_format: Mapped[str | None] = mapped_column(String(32))  # NF-e, CFDI, e-Faktur
    compliance_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("country_code", "tax_type", name="uq_country_tax_type"),)


class StoreTaxRegistration(Base):
    """Per-store tax registration for each country (extends StoreGSTConfig)."""

    __tablename__ = "store_tax_registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(64))  # GSTIN, VAT number, EIN, CNPJ
    registration_type: Mapped[str] = mapped_column(String(32), default="STANDARD")
    is_tax_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    state_province: Mapped[str | None] = mapped_column(String(64))  # for subnational taxes
    additional_config: Mapped[dict | None] = mapped_column(JSONB)
    registered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("store_id", "country_code", name="uq_store_country_tax"),
        Index("idx_store_tax_reg_country", "country_code"),
    )


class TaxTransaction(Base):
    """Universal tax transaction record — replaces single-country GSTTransaction for new countries."""

    __tablename__ = "tax_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    taxable_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    tax_breakdown: Mapped[dict | None] = mapped_column(JSONB)  # {rate: amount} or multi-component
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    exchange_rate_to_usd: Mapped[float | None] = mapped_column(Numeric(18, 8))
    e_invoice_id: Mapped[str | None] = mapped_column(String(128))
    e_invoice_status: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_tax_txn_store_period", "store_id", "period"),
        Index("idx_tax_txn_country", "country_code", "period"),
    )


# ---------------------------------------------------------------------------
# KYC Verification
# ---------------------------------------------------------------------------


class KYCProvider(Base):
    """Configuration for country-specific KYC verification providers."""

    __tablename__ = "kyc_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # aadhaar, bvn, uae_pass
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    verification_type: Mapped[str] = mapped_column(String(32), nullable=False)  # IDENTITY, BUSINESS, ADDRESS
    id_format_regex: Mapped[str | None] = mapped_column(String(256))  # regex for ID validation
    id_label: Mapped[str] = mapped_column(String(64), default="ID Number")  # Aadhaar Number, BVN, etc.
    required_fields: Mapped[dict | None] = mapped_column(JSONB)  # ["full_name", "dob", "id_number"]
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    api_endpoint: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class KYCRecord(Base):
    """Individual KYC verification attempt/result for a merchant."""

    __tablename__ = "kyc_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False)
    provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("kyc_providers.id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    id_number_hash: Mapped[str | None] = mapped_column(String(128))  # hashed, never store raw
    verification_status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("verification_status IN ('PENDING','VERIFIED','REJECTED','EXPIRED')"),
        default="PENDING",
    )
    verification_data: Mapped[dict | None] = mapped_column(JSONB)  # masked response from provider
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_kyc_records_store_country", "store_id", "country_code"),
        Index("idx_kyc_records_status", "verification_status"),
    )


# ---------------------------------------------------------------------------
# E-Invoicing
# ---------------------------------------------------------------------------


class EInvoice(Base):
    """E-invoice records for countries requiring electronic invoicing."""

    __tablename__ = "e_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), ForeignKey("countries.code"), nullable=False)
    invoice_format: Mapped[str] = mapped_column(String(32), nullable=False)  # NF_E, CFDI, E_FAKTUR, MTD
    invoice_number: Mapped[str | None] = mapped_column(String(128))
    authority_ref: Mapped[str | None] = mapped_column(String(256))  # govt-issued reference code
    xml_payload: Mapped[str | None] = mapped_column(Text)  # serialized XML
    qr_code_data: Mapped[str | None] = mapped_column(Text)
    digital_signature: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','ACCEPTED','REJECTED','CANCELLED')"),
        default="DRAFT",
    )
    submission_response: Mapped[dict | None] = mapped_column(JSONB)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_einvoice_store_country", "store_id", "country_code"),
        Index("idx_einvoice_status", "status"),
    )


# ---------------------------------------------------------------------------
# Translation / i18n
# ---------------------------------------------------------------------------


class TranslationKey(Base):
    """Master list of translatable string keys."""

    __tablename__ = "translation_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)  # e.g. "receipt.header"
    module: Mapped[str | None] = mapped_column(String(64))  # receipts, auth, tax, etc.
    description: Mapped[str | None] = mapped_column(Text)


class Translation(Base):
    """Translated strings for each key and locale."""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("translation_keys.id"), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)  # en, hi, pt-BR, de, etc.
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("key_id", "locale", name="uq_translation_key_locale"),
        Index("idx_translation_locale", "locale"),
    )
