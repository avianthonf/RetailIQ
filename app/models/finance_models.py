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

# ────────────────────────────────────────────────────────────────────────────
# MERCHANT FINANCIAL INFRASTRUCTURE
# ────────────────────────────────────────────────────────────────────────────


class FinancialAccount(Base):
    """A merchant's internal financial account for various purposes."""

    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    account_name: Mapped[str] = mapped_column(String(64), nullable=False)
    account_type: Mapped[str] = mapped_column(
        SQLEnum("OPERATING", "RESERVE", "REVENUE", "ESCROW", name="fin_account_type_enum"), nullable=False
    )
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("store_id", "account_type", name="uq_store_account_type"),)


class LedgerEntry(Base):
    """
    Immutable, append-only double-entry ledger.
    Every financial movement must have a DEBIT and a CREDIT entry sharing a transaction_id.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, default=uuid.uuid4)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("financial_accounts.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(SQLEnum("DEBIT", "CREDIT", name="ledger_entry_type_enum"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    description: Mapped[str | None] = mapped_column(String(512))
    meta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), index=True)

    # Note: No updates or deletes allowed on this table by policy.


class MerchantKYC(Base):
    """KYC and Compliance data for a merchant."""

    __tablename__ = "merchant_kyc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(64))
    tax_id: Mapped[str | None] = mapped_column(String(64))  # PAN/GSTIN
    verification_status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "VERIFIED", "REJECTED", "EXPIRED", name="kyc_status_enum"), default="PENDING"
    )
    verification_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    document_urls: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class MerchantCreditProfile(Base):
    """Data-driven credit scoring for merchants."""

    __tablename__ = "merchant_credit_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    credit_score: Mapped[int] = mapped_column(Integer, default=500)
    risk_tier: Mapped[str | None] = mapped_column(String(16))  # A, B, C, D, E
    scoring_version: Mapped[str | None] = mapped_column(String(16), default="v1.0")
    factors: Mapped[dict | None] = mapped_column(JSONB)  # Breakdown of score factors
    last_recalculated: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


# ────────────────────────────────────────────────────────────────────────────
# LENDING & LOANS
# ────────────────────────────────────────────────────────────────────────────


class LoanProduct(Base):
    """Templates for loan products."""

    __tablename__ = "loan_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_type: Mapped[str] = mapped_column(
        SQLEnum("TERM_LOAN", "LINE_OF_CREDIT", "REVENUE_ADVANCE", name="loan_product_type_enum"), nullable=False
    )
    min_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    max_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    interest_rate_bps: Mapped[int] = mapped_column(Integer)  # Basis points
    max_term_days: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoanApplication(Base):
    """Tracks a merchant's request for credit."""

    __tablename__ = "loan_applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("loan_products.id"), nullable=False)
    requested_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "APPLIED",
            "UNDERWRITING",
            "APPROVED",
            "DISBURSED",
            "REPAYING",
            "PAID_OFF",
            "REJECTED",
            name="loan_status_enum",
        ),
        default="APPLIED",
    )
    interest_rate_at_origination: Mapped[int | None] = mapped_column(Integer)
    term_days: Mapped[int | None] = mapped_column(Integer)
    applied_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    decision_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    disbursement_date: Mapped[date | None] = mapped_column(Date)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    outstanding_principal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_interest_paid: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class LoanRepayment(Base):
    """Repayments made against a loan."""

    __tablename__ = "loan_repayments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    loan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("loan_applications.id"), nullable=False)
    ledger_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    principal_component: Mapped[float] = mapped_column(Numeric(14, 2))
    interest_component: Mapped[float] = mapped_column(Numeric(14, 2))
    repaid_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


# ────────────────────────────────────────────────────────────────────────────
# PAYMENTS & TREASURY
# ────────────────────────────────────────────────────────────────────────────


class PaymentTransaction(Base):
    """Records for processed payments (merchant incoming revenue)."""

    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.transaction_id")
    )
    external_id: Mapped[str | None] = mapped_column(String(128))  # Stripe/Unit ID
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    fees: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(SQLEnum("PENDING", "SETTLED", "FAILED", "REFUNDED", name="payment_status_enum"))
    payment_method: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class TreasuryConfig(Base):
    """Yield/sweep configuration for treasury management."""

    __tablename__ = "treasury_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    sweep_strategy: Mapped[str] = mapped_column(
        SQLEnum("OFF", "CONSERVATIVE", "BALANCED", "AGGRESSIVE", name="sweep_strategy_enum"), default="OFF"
    )
    min_balance_threshold: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class TreasuryTransaction(Base):
    """Log of sweep and yield transactions."""

    __tablename__ = "treasury_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    type: Mapped[str] = mapped_column(SQLEnum("SWEEP_IN", "SWEEP_OUT", "YIELD_ACCRUAL", name="treasury_tx_type_enum"))
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    current_yield_bps: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


# ────────────────────────────────────────────────────────────────────────────
# INSURANCE
# ────────────────────────────────────────────────────────────────────────────


class InsuranceProduct(Base):
    """Catalog of parametric insurance products."""

    __tablename__ = "insurance_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(SQLEnum("WEATHER", "SUPPLY_CHAIN", "STRIKE", "OTHER", name="ins_cat_enum"))
    description: Mapped[str | None] = mapped_column(Text)
    premium_monthly: Mapped[float] = mapped_column(Numeric(12, 2))
    max_coverage: Mapped[float] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InsurancePolicy(Base):
    """Merchant enrollment in insurance."""

    __tablename__ = "insurance_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_products.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        SQLEnum("ACTIVE", "EXPIRED", "CANCELLED", name="policy_status_enum"), default="ACTIVE"
    )
    enrolled_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class InsuranceClaim(Base):
    """Claims against insurance policies."""

    __tablename__ = "insurance_claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("insurance_policies.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(64))  # e.g. "RAINFALL_EXCEEDED"
    payout_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "APPROVED", "PAID", "DENIED", name="claim_status_enum"), default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
