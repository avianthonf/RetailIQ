"""
RetailIQ Finance Models
========================
Embedded finance, lending, treasury, and insurance models.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Boolean,
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


class MerchantCreditProfile(Base):
    __tablename__ = "merchant_credit_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    credit_score: Mapped[int | None] = mapped_column(Integer)
    credit_limit: Mapped[float | None] = mapped_column(Numeric(14, 2))
    utilization_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    risk_tier: Mapped[str | None] = mapped_column(SQLEnum("A", "B", "C", "D", "E", name="credit_risk_tier_enum"))
    factors: Mapped[dict | None] = mapped_column(JSON)
    history: Mapped[dict | None] = mapped_column(JSON)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_recalculated: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class LoanProduct(Base):
    __tablename__ = "loan_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_type: Mapped[str] = mapped_column(
        SQLEnum("TERM_LOAN", "WORKING_CAPITAL", "INVOICE_FINANCE", "BNPL", name="loan_product_type_enum"),
        nullable=False,
    )
    min_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    max_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    min_tenure_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tenure_days: Mapped[int] = mapped_column(Integer, nullable=False)
    base_interest_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    processing_fee_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    eligibility_criteria: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    loan_product_id: Mapped[int] = mapped_column(Integer, ForeignKey("loan_products.id"), nullable=False)
    requested_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    tenure_days: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))
    outstanding_principal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_interest_paid: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(
        SQLEnum(
            "PENDING",
            "UNDER_REVIEW",
            "APPROVED",
            "DISBURSED",
            "REPAYING",
            "REJECTED",
            "CLOSED",
            name="loan_app_status_enum",
        ),
        default="PENDING",
        nullable=False,
    )
    purpose: Mapped[str | None] = mapped_column(String(256))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    disbursed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    decision_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    due_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    maturity_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    interest_recalculated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("idx_loan_app_store_status", "store_id", "status"),)


class LoanRepayment(Base):
    __tablename__ = "loan_repayments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loan_application_id: Mapped[int] = mapped_column(Integer, ForeignKey("loan_applications.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    principal_component: Mapped[float | None] = mapped_column(Numeric(14, 2))
    interest_component: Mapped[float | None] = mapped_column(Numeric(14, 2))
    payment_mode: Mapped[str | None] = mapped_column(String(32))
    reference_number: Mapped[str | None] = mapped_column(String(128))
    repaid_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    account_type: Mapped[str] = mapped_column(
        SQLEnum(
            "CURRENT",
            "SAVINGS",
            "VIRTUAL",
            "OPERATING",
            "REVENUE",
            "LIABILITY",
            "ESCROW",
            "RESERVE",
            name="fin_account_type_enum",
        ),
        nullable=False,
    )
    account_number: Mapped[str | None] = mapped_column(String(64))
    ifsc_code: Mapped[str | None] = mapped_column(String(16))
    bank_name: Mapped[str | None] = mapped_column(String(128))
    balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("financial_accounts.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(SQLEnum("DEBIT", "CREDIT", name="ledger_entry_type_enum"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(256))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    reference_type: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(String(32))
    gateway: Mapped[str | None] = mapped_column(String(64))
    gateway_txn_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "COMPLETED", "SETTLED", "FAILED", "REFUNDED", name="payment_txn_status_enum"),
        default="PENDING",
    )
    payment_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    transaction_id: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(64))
    fees: Mapped[float | None] = mapped_column(Numeric(14, 2))
    payment_method: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class TreasuryConfig(Base):
    __tablename__ = "treasury_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    sweep_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sweep_threshold: Mapped[float | None] = mapped_column(Numeric(14, 2))
    sweep_strategy: Mapped[str | None] = mapped_column(String(32), default="OFF")
    min_balance_threshold: Mapped[float | None] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    sweep_target_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("financial_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class TreasuryTransaction(Base):
    __tablename__ = "treasury_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("treasury_configs.id"))
    store_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stores.store_id"))
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    type: Mapped[str | None] = mapped_column(String(32))
    transaction_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    current_yield_bps: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class InsuranceProduct(Base):
    __tablename__ = "insurance_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    product_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128))
    premium_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    coverage_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_products.id"), nullable=False)
    policy_number: Mapped[str | None] = mapped_column(String(128), unique=True)
    premium_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    coverage_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    start_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    end_date: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    status: Mapped[str] = mapped_column(
        SQLEnum("ACTIVE", "EXPIRED", "CANCELLED", "CLAIMED", name="insurance_policy_status_enum"),
        default="ACTIVE",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class InsuranceClaim(Base):
    __tablename__ = "insurance_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(Integer, ForeignKey("insurance_policies.id"), nullable=False)
    claim_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    approved_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED", "PAID", name="insurance_claim_status_enum"),
        default="PENDING",
    )
    submitted_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)


class MerchantKYC(Base):
    __tablename__ = "merchant_kyc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.store_id"), unique=True, nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(64))
    tax_id: Mapped[str | None] = mapped_column(String(64))
    document_urls: Mapped[dict | None] = mapped_column(JSON)
    kyc_status: Mapped[str] = mapped_column(
        SQLEnum("PENDING", "VERIFIED", "REJECTED", "EXPIRED", name="merchant_kyc_status_enum"), default="PENDING"
    )
    verification_status: Mapped[str | None] = mapped_column(String(32))  # Backwards compat
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    documents: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
