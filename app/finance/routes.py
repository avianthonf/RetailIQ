import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import g, jsonify, request

from app import db, limiter
from app.models.finance_models import (
    FinancialAccount,
    InsuranceClaim,
    InsurancePolicy,
    InsuranceProduct,
    LedgerEntry,
    LoanApplication,
    LoanProduct,
    MerchantCreditProfile,
    MerchantKYC,
    TreasuryConfig,
    TreasuryTransaction,
)

from ..auth.decorators import require_auth, require_role
from . import finance_bp
from .credit_scoring import calculate_merchant_score
from .insurance_engine import enroll_merchant, trigger_parametric_claim
from .ledger import get_account_balance, record_transaction
from .loan_engine import apply_for_loan, approve_loan, disburse_loan
from .treasury_manager import accrue_yield, perform_sweep, set_sweep_config

# ────────────────────────────────────────────────────────────────────────────
# KYC & COMPLIANCE
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/kyc/submit", methods=["POST"])
@require_auth
@require_role("owner")
def submit_kyc():
    """Submit KYC identity data for verification."""
    data = request.get_json()
    store_id = g.current_user["store_id"]

    kyc = db.session.query(MerchantKYC).filter_by(store_id=store_id).first()
    if not kyc:
        kyc = MerchantKYC(store_id=store_id)
        db.session.add(kyc)

    kyc.business_type = data.get("business_type")
    kyc.tax_id = data.get("tax_id")
    kyc.document_urls = data.get("document_urls", {})
    kyc.kyc_status = "PENDING"

    db.session.commit()
    return jsonify({"message": "KYC submitted successfully", "status": "PENDING"}), 201


@finance_bp.route("/kyc/status", methods=["GET"])
@require_auth
def get_kyc_status():
    """Check KYC verification status."""
    kyc = db.session.query(MerchantKYC).filter_by(store_id=g.current_user["store_id"]).first()
    if not kyc:
        return jsonify({"status": "NOT_STARTED"}), 200

    return jsonify(
        {
            "status": kyc.kyc_status,
            "tax_id": kyc.tax_id,
            "updated_at": kyc.updated_at.isoformat() if kyc.updated_at else None,
        }
    ), 200


# ────────────────────────────────────────────────────────────────────────────
# CREDIT SCORING
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/credit-score", methods=["GET"])
@require_auth
def get_credit_score():
    """Get merchant credit score + SHAP factors."""
    store_id = g.current_user["store_id"]
    profile = db.session.query(MerchantCreditProfile).filter_by(store_id=store_id).first()
    if not profile:
        # Initial calculation if not exists
        calculate_merchant_score(store_id)
        profile = db.session.query(MerchantCreditProfile).filter_by(store_id=store_id).first()
        db.session.commit()

    return jsonify(
        {
            "score": profile.credit_score,
            "tier": profile.risk_tier,
            "factors": profile.factors,
            "last_updated": (profile.last_evaluated_at or profile.created_at).isoformat(),
        }
    ), 200


@finance_bp.route("/credit-score/refresh", methods=["POST"])
@require_auth
def refresh_credit_score():
    """Trigger credit score recomputation."""
    score = calculate_merchant_score(g.current_user["store_id"])
    db.session.commit()
    return jsonify({"message": "Score recalculated", "score": score}), 200


# ────────────────────────────────────────────────────────────────────────────
# LEDGER & ACCOUNTS
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/accounts", methods=["GET"])
@require_auth
def get_accounts():
    """List merchant financial accounts."""
    accounts = db.session.query(FinancialAccount).filter_by(store_id=g.current_user["store_id"]).all()
    return jsonify(
        [
            {
                "id": a.id,
                "type": a.account_type,
                "balance": float(a.balance),
            }
            for a in accounts
        ]
    ), 200


@finance_bp.route("/ledger", methods=["GET"])
@require_auth
def get_ledger():
    """Query ledger entries with filters."""
    account_id = request.args.get("account_id", type=int)
    store_id = g.current_user["store_id"]
    query = db.session.query(LedgerEntry).join(FinancialAccount).filter(FinancialAccount.store_id == store_id)

    if account_id:
        query = query.filter(LedgerEntry.account_id == account_id)

    entries = query.order_by(LedgerEntry.created_at.desc()).limit(50).all()

    return jsonify(
        [
            {
                "id": e.id,
                "txn_id": str(e.transaction_id),
                "account_id": e.account_id,
                "type": e.entry_type,
                "amount": float(e.amount),
                "description": e.description,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]
    ), 200


# ────────────────────────────────────────────────────────────────────────────
# LENDING
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/loans/apply", methods=["POST"])
@require_auth
@require_role("owner")
def apply_loan():
    """Submit loan application."""
    data = request.get_json()
    app = apply_for_loan(
        store_id=g.current_user["store_id"],
        product_id=data["product_id"],
        amount=Decimal(str(data["amount"])),
        term_days=data["term_days"],
    )
    db.session.commit()
    return jsonify({"message": "Application submitted", "application_id": app.id, "status": app.status}), 201


@finance_bp.route("/loans", methods=["GET"])
@require_auth
def list_loans():
    """List merchant loans."""
    loans = db.session.query(LoanApplication).filter_by(store_id=g.current_user["store_id"]).all()
    return jsonify(
        [
            {
                "id": l.id,
                "amount": float(l.approved_amount or l.requested_amount),
                "status": l.status,
                "applied_at": l.created_at.isoformat(),
                "outstanding": float(l.outstanding_principal),
            }
            for l in loans
        ]
    ), 200


@finance_bp.route("/loans/<int:loan_id>/disburse", methods=["POST"])
@require_auth
@require_role("owner")
def disburse_loan_route(loan_id):
    """Disburse approved loan."""
    store_id = g.current_user["store_id"]
    loan = db.session.query(LoanApplication).filter_by(id=loan_id, store_id=store_id).first()
    if not loan:
        return jsonify({"message": "Loan not found"}), 404

    txn_id = disburse_loan(loan_id)
    db.session.commit()
    return jsonify({"message": "Loan disbursed", "ledger_txn_id": str(txn_id)}), 200


# ────────────────────────────────────────────────────────────────────────────
# PAYMENTS
# ────────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────────
# TREASURY
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/treasury/balance", methods=["GET"])
@require_auth
def treasury_balance():
    """Treasury balance + yield info."""
    account = (
        db.session.query(FinancialAccount)
        .filter_by(store_id=g.current_user["store_id"], account_type="RESERVE")
        .first()
    )
    # Pull latest yield from the most recent treasury transaction for this store
    latest_yield_tx = (
        db.session.query(TreasuryTransaction)
        .filter_by(store_id=g.current_user["store_id"], type="YIELD_ACCRUAL")
        .order_by(TreasuryTransaction.created_at.desc())
        .first()
    )
    yield_bps = latest_yield_tx.current_yield_bps if latest_yield_tx and latest_yield_tx.current_yield_bps else 450

    return jsonify(
        {
            "available": float(account.balance) if account else 0,
            "yield_bps": yield_bps,
            "currency": "INR",
        }
    ), 200


@finance_bp.route("/treasury/config", methods=["GET"])
@require_auth
def get_treasury_config():
    """Return treasury sweep configuration for the current store."""
    store_id = g.current_user["store_id"]
    config = db.session.query(TreasuryConfig).filter_by(store_id=store_id).first()

    if not config:
        return jsonify(
            {
                "auto_transfer_enabled": False,
                "reserve_percentage": 0,
                "daily_transfer_limit": 0,
                "settlement_account_id": "",
                "strategy": "OFF",
            }
        ), 200

    reserve_account = db.session.query(FinancialAccount).filter_by(store_id=store_id, account_type="RESERVE").first()
    operating_account = (
        db.session.query(FinancialAccount).filter_by(store_id=store_id, account_type="OPERATING").first()
    )
    reserve_balance = float(reserve_account.balance) if reserve_account else 0
    operating_balance = float(operating_account.balance) if operating_account else 0
    total_balance = reserve_balance + operating_balance
    reserve_percentage = (reserve_balance / total_balance * 100) if total_balance > 0 else 0

    return jsonify(
        {
            "auto_transfer_enabled": bool(config.sweep_enabled and config.is_active),
            "reserve_percentage": round(reserve_percentage, 2),
            "daily_transfer_limit": float(config.min_balance_threshold or 0),
            "settlement_account_id": str(config.sweep_target_account_id or ""),
            "strategy": config.sweep_strategy or "OFF",
            "sweep_threshold": float(config.sweep_threshold or 0),
            "created_at": config.created_at.isoformat() if config.created_at else None,
        }
    ), 200


@finance_bp.route("/treasury/sweep-config", methods=["PUT"])
@require_auth
@require_role("owner")
def update_sweep_config():
    """Set sweep strategy."""
    data = request.get_json()
    config = set_sweep_config(
        store_id=g.current_user["store_id"],
        strategy=data["strategy"],
        min_balance=Decimal(str(data.get("min_balance", 0))),
    )
    db.session.commit()
    return jsonify({"message": "Sweep config updated", "active": config.is_active}), 200


@finance_bp.route("/treasury/transactions", methods=["GET"])
@require_auth
def get_treasury_transactions():
    """List treasury transactions with a frontend-friendly history shape."""
    store_id = g.current_user["store_id"]
    limit = min(request.args.get("limit", 50, type=int), 200)

    transactions = (
        db.session.query(TreasuryTransaction)
        .filter_by(store_id=store_id)
        .order_by(TreasuryTransaction.created_at.desc())
        .limit(limit)
        .all()
    )

    if transactions:
        data = [
            {
                "id": txn.id,
                "type": txn.type or txn.transaction_type or "TRANSFER_IN",
                "amount": float(txn.amount),
                "description": txn.transaction_type or txn.type or "Treasury transaction",
                "status": txn.status or "COMPLETED",
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "completed_at": txn.created_at.isoformat() if txn.created_at else None,
            }
            for txn in transactions
        ]
        return jsonify(data), 200

    reserve_account = db.session.query(FinancialAccount).filter_by(store_id=store_id, account_type="RESERVE").first()
    if not reserve_account:
        return jsonify([]), 200

    ledger_entries = (
        db.session.query(LedgerEntry)
        .filter_by(account_id=reserve_account.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    data = [
        {
            "id": entry.id,
            "type": "TRANSFER_OUT" if entry.entry_type == "DEBIT" else "TRANSFER_IN",
            "amount": float(entry.amount),
            "description": entry.description or "Treasury ledger entry",
            "status": "COMPLETED",
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "completed_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in ledger_entries
    ]
    return jsonify(data), 200


# ────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────────────────────────────────


@finance_bp.route("/dashboard", methods=["GET"])
@require_auth
def finance_dashboard():
    """Financial health dashboard."""
    store_id = g.current_user["store_id"]
    operating = db.session.query(FinancialAccount).filter_by(store_id=store_id, account_type="OPERATING").first()
    reserve = db.session.query(FinancialAccount).filter_by(store_id=store_id, account_type="RESERVE").first()
    loans = (
        db.session.query(LoanApplication)
        .filter(LoanApplication.store_id == store_id, LoanApplication.status.in_(["DISBURSED", "REPAYING"]))
        .all()
    )

    return jsonify(
        {
            "cash_on_hand": float(operating.balance) if operating else 0,
            "treasury_balance": float(reserve.balance) if reserve else 0,
            "total_debt": float(sum(l.outstanding_principal for l in loans)),
            "credit_score": calculate_merchant_score(store_id),
        }
    ), 200
