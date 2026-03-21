import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import func

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import (
    CreditLedger,
    CreditTransaction,
    Customer,
    CustomerLoyaltyAccount,
    LoyaltyProgram,
    LoyaltyTier,
    LoyaltyTransaction,
)
from . import credit_bp, loyalty_bp
from .schemas import LoyaltyProgramUpsertSchema, RedeemPointsSchema, RepayCreditSchema


def _ensure_loyalty_program(store_id):
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        program = LoyaltyProgram(store_id=store_id)
        db.session.add(program)
        db.session.flush()
    return program


def _ensure_default_tier(program):
    tier = db.session.query(LoyaltyTier).filter_by(program_id=program.id, is_default=True).first()
    if tier:
        return tier

    tier = LoyaltyTier(
        program_id=program.id,
        name="Base",
        description="Default loyalty tier",
        min_points=0,
        benefits=[],
        multiplier=1,
        is_default=True,
    )
    db.session.add(tier)
    db.session.flush()
    return tier


def _serialize_tier(tier):
    return {
        "id": str(tier.id),
        "name": tier.name,
        "description": tier.description or "",
        "min_points": tier.min_points,
        "max_points": tier.max_points,
        "benefits": tier.benefits or [],
        "multiplier": float(tier.multiplier or 1),
        "created_at": tier.created_at.isoformat() if tier.created_at else None,
    }


def _serialize_account(account, customer=None, tier=None):
    customer = customer or db.session.get(Customer, account.customer_id)
    tier = tier or (db.session.get(LoyaltyTier, account.tier_id) if account.tier_id else None)
    return {
        "id": str(account.id),
        "customer_id": str(account.customer_id),
        "customer_name": customer.name if customer and customer.name else f"Customer {account.customer_id}",
        "customer_phone": customer.mobile_number if customer and customer.mobile_number else "",
        "customer_email": customer.email if customer else None,
        "program_id": str(tier.program_id) if tier else None,
        "tier_id": str(tier.id) if tier else "default",
        "tier_name": tier.name if tier else "Base",
        "current_points": float(account.total_points or 0),
        "lifetime_points": float(account.lifetime_earned or 0),
        "points_earned": float(account.lifetime_earned or 0),
        "points_redeemed": max(float(account.lifetime_earned or 0) - float(account.total_points or 0), 0),
        "last_activity_at": account.last_activity_at.isoformat() if account.last_activity_at else None,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


def _apply_loyalty_adjustment(account, points, reason):
    account.total_points = Decimal(str(account.total_points or 0)) + points
    account.redeemable_points = Decimal(str(account.redeemable_points or 0)) + points
    account.lifetime_earned = Decimal(str(account.lifetime_earned or 0)) + max(points, Decimal("0"))
    account.last_activity_at = datetime.now(timezone.utc)

    txn = LoyaltyTransaction(
        account_id=account.id,
        type="ADJUST",
        points=points,
        balance_after=account.total_points,
        notes=reason,
    )
    db.session.add(txn)
    return txn


@loyalty_bp.route("/program", methods=["GET"])
@require_auth
def get_loyalty_program():
    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "No loyalty program configured"}
        ), 404

    tiers = db.session.query(LoyaltyTier).filter_by(program_id=program.id).order_by(LoyaltyTier.min_points.asc()).all()
    data = {
        "points_per_rupee": float(program.points_per_rupee),
        "redemption_rate": float(program.redemption_rate),
        "min_redemption_points": program.min_redemption_points,
        "expiry_days": program.expiry_days,
        "is_active": program.is_active,
        "tiers": [_serialize_tier(tier) for tier in tiers],
    }
    return format_response(success=True, data=data)


@loyalty_bp.route("/program", methods=["PUT"])
@require_auth
@require_role("owner")
def upsert_loyalty_program():
    try:
        data = LoyaltyProgramUpsertSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": err.messages})

    store_id = g.current_user["store_id"]
    program = _ensure_loyalty_program(store_id)

    for key, value in data.items():
        setattr(program, key, value)

    _ensure_default_tier(program)
    db.session.commit()
    return format_response(success=True, data={"message": "Loyalty program updated"})


@loyalty_bp.route("/tiers", methods=["POST"])
@require_auth
@require_role("owner")
def create_loyalty_tier():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    if not body.get("name"):
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": "name is required"},
            status_code=400,
        )

    program = _ensure_loyalty_program(store_id)
    _ensure_default_tier(program)
    tier = LoyaltyTier(
        program_id=program.id,
        name=body["name"],
        description=body.get("description"),
        min_points=body.get("min_points", 0),
        max_points=body.get("max_points"),
        benefits=body.get("benefits", []),
        multiplier=body.get("multiplier", 1),
        is_default=False,
    )
    db.session.add(tier)
    db.session.commit()
    return format_response(True, data=_serialize_tier(tier), status_code=201)


@loyalty_bp.route("/tiers/<uuid:tier_id>", methods=["PUT", "PATCH"])
@require_auth
@require_role("owner")
def update_loyalty_tier(tier_id):
    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Loyalty program not found"}, status_code=404
        )

    tier = db.session.query(LoyaltyTier).filter_by(id=tier_id, program_id=program.id).first()
    if not tier:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Tier not found"}, status_code=404)

    body = request.get_json() or {}
    for key in ("name", "description", "min_points", "max_points", "benefits", "multiplier"):
        if key in body:
            setattr(tier, key, body[key])

    db.session.commit()
    return format_response(True, data=_serialize_tier(tier))


@loyalty_bp.route("/tiers/<uuid:tier_id>", methods=["DELETE"])
@require_auth
@require_role("owner")
def delete_loyalty_tier(tier_id):
    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Loyalty program not found"}, status_code=404
        )

    tier = db.session.query(LoyaltyTier).filter_by(id=tier_id, program_id=program.id).first()
    if not tier:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Tier not found"}, status_code=404)
    if tier.is_default:
        return format_response(
            success=False,
            error={"code": "UNPROCESSABLE_ENTITY", "message": "Default tier cannot be deleted"},
            status_code=422,
        )

    default_tier = _ensure_default_tier(program)
    db.session.query(CustomerLoyaltyAccount).filter_by(tier_id=tier.id).update({"tier_id": default_tier.id})
    db.session.delete(tier)
    db.session.commit()
    return format_response(True, data={"id": str(tier_id), "deleted": True})


@loyalty_bp.route("/customers/<int:customer_id>", methods=["GET"])
@loyalty_bp.route("/customers/<int:customer_id>/account", methods=["GET"])
@loyalty_bp.route("/credit/account/<int:customer_id>", methods=["GET"])
@require_auth
def get_customer_loyalty(customer_id):
    store_id = g.current_user["store_id"]
    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not account:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"})

    txns = (
        db.session.query(LoyaltyTransaction)
        .filter_by(account_id=account.id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .limit(10)
        .all()
    )
    recent_transactions = []
    for txn in txns:
        recent_transactions.append(
            {
                "type": txn.type,
                "points": float(txn.points) if txn.points else 0,
                "balance_after": float(txn.balance_after) if txn.balance_after else 0,
                "created_at": txn.created_at.isoformat(),
                "notes": txn.notes,
            }
        )

    customer = db.session.get(Customer, customer_id)
    tier = db.session.get(LoyaltyTier, account.tier_id) if account.tier_id else None
    data = {
        "total_points": float(account.total_points),
        "redeemable_points": float(account.redeemable_points),
        "lifetime_earned": float(account.lifetime_earned),
        "last_activity_at": account.last_activity_at.isoformat() if account.last_activity_at else None,
        "recent_transactions": recent_transactions,
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.mobile_number if customer else None,
        "tier_id": str(tier.id) if tier else None,
        "tier_name": tier.name if tier else "Base",
    }
    return format_response(success=True, data=data)


@loyalty_bp.route("/customers/<int:customer_id>/enroll", methods=["POST"])
@require_auth
@require_role("owner")
def enroll_loyalty_customer(customer_id):
    store_id = g.current_user["store_id"]
    customer = db.session.query(Customer).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not customer:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Customer not found"}, status_code=404
        )

    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not account:
        program = _ensure_loyalty_program(store_id)
        default_tier = _ensure_default_tier(program)
        account = CustomerLoyaltyAccount(
            customer_id=customer_id,
            store_id=store_id,
            tier_id=default_tier.id,
            total_points=0,
            redeemable_points=0,
            lifetime_earned=0,
            last_activity_at=datetime.now(timezone.utc),
        )
        db.session.add(account)
        db.session.commit()
    return format_response(True, data=_serialize_account(account, customer=customer))


@loyalty_bp.route("/customers/<int:customer_id>/transactions", methods=["GET"])
@require_auth
def get_loyalty_transactions(customer_id):
    store_id = g.current_user["store_id"]
    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not account:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"})

    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 20, type=int), 100)
    offset = (page - 1) * limit

    txns = (
        db.session.query(LoyaltyTransaction)
        .filter_by(account_id=account.id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for txn in txns:
        data.append(
            {
                "id": str(txn.id),
                "type": txn.type,
                "points": float(txn.points) if txn.points else 0,
                "balance_after": float(txn.balance_after) if txn.balance_after else 0,
                "created_at": txn.created_at.isoformat(),
                "notes": txn.notes,
            }
        )

    return format_response(success=True, data=data)


@loyalty_bp.route("/customers/<int:customer_id>/redeem", methods=["POST"])
@require_auth
def redeem_loyalty_points(customer_id):
    try:
        data = RedeemPointsSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": err.messages})

    store_id = g.current_user["store_id"]
    points_to_redeem = Decimal(str(data["points_to_redeem"]))

    try:
        with db.session.begin_nested():
            program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id, is_active=True).first()
            if not program:
                raise ValueError("Active loyalty program not found")

            if points_to_redeem < Decimal(str(program.min_redemption_points)):
                raise ValueError(f"Points to redeem is below minimum of {program.min_redemption_points}")

            account = (
                db.session.query(CustomerLoyaltyAccount)
                .with_for_update()
                .filter_by(customer_id=customer_id, store_id=store_id)
                .first()
            )
            if not account or Decimal(str(account.redeemable_points)) < points_to_redeem:
                raise ValueError("Insufficient points for redemption")

            account.total_points = Decimal(str(account.total_points)) - points_to_redeem
            account.redeemable_points = Decimal(str(account.redeemable_points)) - points_to_redeem
            account.last_activity_at = datetime.now(timezone.utc)

            txn = LoyaltyTransaction(
                account_id=account.id,
                transaction_id=data.get("transaction_id"),
                type="REDEEM",
                points=-points_to_redeem,
                balance_after=account.total_points,
                notes="Redeemed points",
            )
            db.session.add(txn)

        db.session.commit()
        return format_response(
            True, data={"message": "Points redeemed successfully", "remaining_points": float(account.total_points)}
        )
    except ValueError as exc:
        db.session.rollback()
        return format_response(
            success=False, error={"code": "UNPROCESSABLE_ENTITY", "message": str(exc)}, status_code=422
        )
    except Exception as exc:
        db.session.rollback()
        return format_response(success=False, error={"code": "SERVER_ERROR", "message": str(exc)})


@loyalty_bp.route("/customers/<int:customer_id>/adjust", methods=["POST"])
@require_auth
@require_role("owner")
def adjust_loyalty_points(customer_id):
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    try:
        points = Decimal(str(body["points"]))
    except Exception:
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": "points is required"},
            status_code=400,
        )

    reason = body.get("reason") or "Manual adjustment"
    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not account:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"}, status_code=404
        )

    txn = _apply_loyalty_adjustment(account, points, reason)
    db.session.commit()
    return format_response(
        True,
        data={
            "id": str(txn.id),
            "type": "ADJUST",
            "points": float(txn.points),
            "balance_after": float(txn.balance_after),
            "description": reason,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        },
    )


@loyalty_bp.route("/customers/adjustments/bulk", methods=["POST"])
@require_auth
@require_role("owner")
def bulk_adjust_loyalty_points():
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    adjustments = body if isinstance(body, list) else body.get("adjustments", [])

    successful = []
    failed = []
    for adjustment in adjustments:
        customer_id = adjustment.get("customer_id")
        try:
            points = Decimal(str(adjustment["points"]))
            reason = adjustment.get("reason") or "Manual adjustment"
            account = (
                db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()
            )
            if not account:
                raise ValueError("Loyalty account not found")
            txn = _apply_loyalty_adjustment(account, points, reason)
            successful.append(
                {
                    "customer_id": str(customer_id),
                    "transaction": {
                        "id": str(txn.id),
                        "type": "ADJUST",
                        "points": float(txn.points),
                        "balance_after": float(txn.balance_after),
                    },
                }
            )
        except Exception as exc:
            failed.append({"customer_id": str(customer_id), "error": str(exc)})

    db.session.commit()
    return format_response(True, data={"successful": successful, "failed": failed})


@loyalty_bp.route("/customers/<int:customer_id>/tier", methods=["PUT"])
@require_auth
@require_role("owner")
def update_customer_loyalty_tier(customer_id):
    store_id = g.current_user["store_id"]
    body = request.get_json() or {}
    tier_id = body.get("tier_id")
    if not tier_id:
        return format_response(
            success=False, error={"code": "VALIDATION_ERROR", "message": "tier_id is required"}, status_code=400
        )

    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not account:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"}, status_code=404
        )

    tier = db.session.get(LoyaltyTier, uuid.UUID(str(tier_id)))
    if not tier:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Tier not found"}, status_code=404)

    account.tier_id = tier.id
    db.session.commit()
    customer = db.session.get(Customer, customer_id)
    return format_response(True, data=_serialize_account(account, customer=customer, tier=tier))


@credit_bp.route("/customers/<int:customer_id>", methods=["GET"])
@credit_bp.route("/customers/<int:customer_id>/account", methods=["GET"])
@require_auth
def get_customer_credit(customer_id):
    store_id = g.current_user["store_id"]
    ledger = db.session.query(CreditLedger).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not ledger:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Credit ledger not found"})

    txns = (
        db.session.query(CreditTransaction)
        .filter_by(ledger_id=ledger.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
        .all()
    )
    recent_transactions = []
    for txn in txns:
        recent_transactions.append(
            {
                "type": txn.type,
                "amount": float(txn.amount) if txn.amount else 0,
                "balance_after": float(txn.balance_after) if txn.balance_after else 0,
                "created_at": txn.created_at.isoformat(),
                "notes": txn.notes,
            }
        )

    data = {
        "balance": float(ledger.balance),
        "credit_limit": float(ledger.credit_limit),
        "updated_at": ledger.updated_at.isoformat() if ledger.updated_at else None,
        "recent_transactions": recent_transactions,
    }
    return format_response(success=True, data=data)


@credit_bp.route("/customers/<int:customer_id>/transactions", methods=["GET"])
@require_auth
def get_credit_transactions(customer_id):
    store_id = g.current_user["store_id"]
    ledger = db.session.query(CreditLedger).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not ledger:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Credit ledger not found"})

    page = request.args.get("page", 1, type=int)
    limit = min(request.args.get("limit", 20, type=int), 100)
    offset = (page - 1) * limit

    txns = (
        db.session.query(CreditTransaction)
        .filter_by(ledger_id=ledger.id)
        .order_by(CreditTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    data = []
    for txn in txns:
        data.append(
            {
                "id": str(txn.id),
                "type": txn.type,
                "amount": float(txn.amount) if txn.amount else 0,
                "balance_after": float(txn.balance_after) if txn.balance_after else 0,
                "created_at": txn.created_at.isoformat(),
                "notes": txn.notes,
            }
        )

    return format_response(success=True, data=data)


@credit_bp.route("/customers/<int:customer_id>/repay", methods=["POST"])
@require_auth
def repay_credit(customer_id):
    try:
        data = RepayCreditSchema().load(request.json)
    except ValidationError as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": err.messages})

    store_id = g.current_user["store_id"]
    amount = Decimal(str(data["amount"]))
    notes = data.get("notes")

    try:
        with db.session.begin_nested():
            ledger = (
                db.session.query(CreditLedger)
                .with_for_update()
                .filter_by(customer_id=customer_id, store_id=store_id)
                .first()
            )
            if not ledger:
                raise ValueError("Credit ledger not found")

            ledger.balance = Decimal(str(ledger.balance)) - amount
            ledger.updated_at = datetime.now(timezone.utc)

            txn = CreditTransaction(
                ledger_id=ledger.id,
                type="REPAYMENT",
                amount=-amount,
                balance_after=ledger.balance,
                notes=notes or "Repayment received",
            )
            db.session.add(txn)

        db.session.commit()
        return format_response(
            True, data={"message": "Repayment successful", "remaining_balance": float(ledger.balance)}
        )
    except ValueError as exc:
        db.session.rollback()
        return format_response(success=False, error={"code": "UNPROCESSABLE_ENTITY", "message": str(exc)})
    except Exception as exc:
        db.session.rollback()
        return format_response(success=False, error={"code": "SERVER_ERROR", "message": str(exc)})


@loyalty_bp.route("/analytics", methods=["GET"])
@require_auth
def loyalty_analytics():
    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if program:
        _ensure_default_tier(program)
        db.session.flush()

    enrolled_customers = db.session.query(CustomerLoyaltyAccount).filter_by(store_id=store_id).count()

    today = datetime.now(timezone.utc)
    start_of_month = datetime(today.year, today.month, 1, tzinfo=timezone.utc)

    accounts = db.session.query(CustomerLoyaltyAccount.id).filter_by(store_id=store_id).subquery()

    earned_this_month = (
        db.session.query(func.sum(LoyaltyTransaction.points))
        .filter(
            LoyaltyTransaction.account_id.in_(accounts),
            LoyaltyTransaction.type == "EARN",
            LoyaltyTransaction.created_at >= start_of_month,
        )
        .scalar()
        or 0
    )

    redeemed_this_month = (
        db.session.query(func.sum(LoyaltyTransaction.points))
        .filter(
            LoyaltyTransaction.account_id.in_(accounts),
            LoyaltyTransaction.type == "REDEEM",
            LoyaltyTransaction.created_at >= start_of_month,
        )
        .scalar()
        or 0
    )

    redeemed_abs = abs(float(redeemed_this_month))
    earned = float(earned_this_month)
    redemption_rate = (redeemed_abs / (earned + redeemed_abs)) if (earned + redeemed_abs) > 0 else 0

    top_rows = (
        db.session.query(CustomerLoyaltyAccount, Customer, LoyaltyTier)
        .join(Customer, Customer.customer_id == CustomerLoyaltyAccount.customer_id)
        .outerjoin(LoyaltyTier, LoyaltyTier.id == CustomerLoyaltyAccount.tier_id)
        .filter(CustomerLoyaltyAccount.store_id == store_id)
        .order_by(CustomerLoyaltyAccount.total_points.desc())
        .limit(5)
        .all()
    )
    top_customers = [
        {
            "customer_id": str(account.customer_id),
            "customer_name": customer.name or f"Customer {account.customer_id}",
            "points": float(account.total_points or 0),
            "tier": tier.name if tier else "Base",
        }
        for account, customer, tier in top_rows
    ]

    tier_distribution = []
    if program:
        tier_rows = (
            db.session.query(LoyaltyTier.name, func.count(CustomerLoyaltyAccount.id))
            .outerjoin(CustomerLoyaltyAccount, CustomerLoyaltyAccount.tier_id == LoyaltyTier.id)
            .filter(LoyaltyTier.program_id == program.id)
            .group_by(LoyaltyTier.name)
            .all()
        )
        tier_distribution = [
            {
                "tier_name": tier_name,
                "customer_count": count,
                "percentage": round((count / enrolled_customers) * 100, 2) if enrolled_customers else 0,
            }
            for tier_name, count in tier_rows
        ]

    data = {
        "enrolled_customers": enrolled_customers,
        "points_issued_this_month": earned,
        "points_redeemed_this_month": redeemed_abs,
        "redemption_rate_this_month": redemption_rate,
        "top_customers": top_customers,
        "tier_distribution": tier_distribution,
        "monthly_trends": [],
    }
    return format_response(success=True, data=data)


@loyalty_bp.route("/expiring-points", methods=["GET"])
@require_auth
def get_expiring_points():
    store_id = g.current_user["store_id"]
    days = request.args.get("days", 30, type=int)
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        return format_response(True, data=[])

    expiry_days = int(program.expiry_days or 0)
    now = datetime.now(timezone.utc)
    accounts = (
        db.session.query(CustomerLoyaltyAccount, Customer)
        .join(Customer, Customer.customer_id == CustomerLoyaltyAccount.customer_id)
        .filter(CustomerLoyaltyAccount.store_id == store_id, CustomerLoyaltyAccount.total_points > 0)
        .all()
    )

    data = []
    for account, customer in accounts:
        if not account.last_activity_at:
            continue
        last_activity = account.last_activity_at
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        expires_at = last_activity + timedelta(days=expiry_days)
        if 0 <= (expires_at - now).days <= days:
            data.append(
                {
                    "customer_id": str(account.customer_id),
                    "customer_name": customer.name or f"Customer {account.customer_id}",
                    "points": float(account.total_points or 0),
                    "expires_at": expires_at.isoformat(),
                }
            )
    return format_response(True, data=data)
