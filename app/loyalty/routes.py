import uuid
from datetime import datetime, timezone
from decimal import Decimal

from flask import g, request
from marshmallow import ValidationError

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import CreditLedger, CreditTransaction, CustomerLoyaltyAccount, LoyaltyProgram, LoyaltyTransaction
from . import loyalty_bp
from .schemas import LoyaltyProgramUpsertSchema, RedeemPointsSchema, RepayCreditSchema


@loyalty_bp.route("/loyalty/program", methods=["GET"])
@require_auth
def get_loyalty_program():
    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()
    if not program:
        return format_response(False, error={"code": "NOT_FOUND", "message": "No loyalty program configured"}), 404

    data = {
        "points_per_rupee": float(program.points_per_rupee),
        "redemption_rate": float(program.redemption_rate),
        "min_redemption_points": program.min_redemption_points,
        "expiry_days": program.expiry_days,
        "is_active": program.is_active,
    }
    return format_response(True, data=data), 200


@loyalty_bp.route("/loyalty/program", methods=["PUT"])
@require_auth
@require_role("owner")
def upsert_loyalty_program():
    try:
        data = LoyaltyProgramUpsertSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

    store_id = g.current_user["store_id"]
    program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id).first()

    if not program:
        program = LoyaltyProgram(store_id=store_id)
        db.session.add(program)

    for key, value in data.items():
        setattr(program, key, value)

    db.session.commit()
    return format_response(True, data={"message": "Loyalty program updated"}), 200


@loyalty_bp.route("/loyalty/customers/<int:customer_id>", methods=["GET"])
@loyalty_bp.route("/loyalty/customers/<int:customer_id>/account", methods=["GET"])
@require_auth
def get_customer_loyalty(customer_id):
    store_id = g.current_user["store_id"]
    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not account:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"}), 404

    txns = (
        db.session.query(LoyaltyTransaction)
        .filter_by(account_id=account.id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .limit(10)
        .all()
    )
    recent_transactions = []
    for t in txns:
        recent_transactions.append(
            {
                "type": t.type,
                "points": float(t.points) if t.points else 0,
                "balance_after": float(t.balance_after) if t.balance_after else 0,
                "created_at": t.created_at.isoformat(),
                "notes": t.notes,
            }
        )

    data = {
        "total_points": float(account.total_points),
        "redeemable_points": float(account.redeemable_points),
        "lifetime_earned": float(account.lifetime_earned),
        "last_activity_at": account.last_activity_at.isoformat() if account.last_activity_at else None,
        "recent_transactions": recent_transactions,
    }
    return format_response(True, data=data), 200


@loyalty_bp.route("/loyalty/customers/<int:customer_id>/transactions", methods=["GET"])
@require_auth
def get_loyalty_transactions(customer_id):
    store_id = g.current_user["store_id"]
    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not account:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Loyalty account not found"}), 404

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
    for t in txns:
        data.append(
            {
                "id": str(t.id),
                "type": t.type,
                "points": float(t.points) if t.points else 0,
                "balance_after": float(t.balance_after) if t.balance_after else 0,
                "created_at": t.created_at.isoformat(),
                "notes": t.notes,
            }
        )

    return format_response(True, data=data), 200


@loyalty_bp.route("/loyalty/customers/<int:customer_id>/redeem", methods=["POST"])
@require_auth
def redeem_loyalty_points(customer_id):
    try:
        data = RedeemPointsSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

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

            tx = LoyaltyTransaction(
                account_id=account.id,
                transaction_id=data.get("transaction_id"),
                type="REDEEM",
                points=-points_to_redeem,
                balance_after=account.total_points,
                notes="Redeemed points",
            )
            db.session.add(tx)

        db.session.commit()
        return format_response(
            True, data={"message": "Points redeemed successfully", "remaining_points": float(account.total_points)}
        ), 200
    except ValueError as e:
        db.session.rollback()
        return format_response(False, error={"code": "UNPROCESSABLE_ENTITY", "message": str(e)}), 422
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500


@loyalty_bp.route("/credit/customers/<int:customer_id>", methods=["GET"])
@loyalty_bp.route("/credit/customers/<int:customer_id>/account", methods=["GET"])
@require_auth
def get_customer_credit(customer_id):
    store_id = g.current_user["store_id"]
    ledger = db.session.query(CreditLedger).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not ledger:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Credit ledger not found"}), 404

    txns = (
        db.session.query(CreditTransaction)
        .filter_by(ledger_id=ledger.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
        .all()
    )
    recent_transactions = []
    for t in txns:
        recent_transactions.append(
            {
                "type": t.type,
                "amount": float(t.amount) if t.amount else 0,
                "balance_after": float(t.balance_after) if t.balance_after else 0,
                "created_at": t.created_at.isoformat(),
                "notes": t.notes,
            }
        )

    data = {
        "balance": float(ledger.balance),
        "credit_limit": float(ledger.credit_limit),
        "updated_at": ledger.updated_at.isoformat() if ledger.updated_at else None,
        "recent_transactions": recent_transactions,
    }
    return format_response(True, data=data), 200


@loyalty_bp.route("/credit/customers/<int:customer_id>/transactions", methods=["GET"])
@require_auth
def get_credit_transactions(customer_id):
    store_id = g.current_user["store_id"]
    ledger = db.session.query(CreditLedger).filter_by(customer_id=customer_id, store_id=store_id).first()

    if not ledger:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Credit ledger not found"}), 404

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
    for t in txns:
        data.append(
            {
                "id": str(t.id),
                "type": t.type,
                "amount": float(t.amount) if t.amount else 0,
                "balance_after": float(t.balance_after) if t.balance_after else 0,
                "created_at": t.created_at.isoformat(),
                "notes": t.notes,
            }
        )

    return format_response(True, data=data), 200


@loyalty_bp.route("/credit/customers/<int:customer_id>/repay", methods=["POST"])
@require_auth
def repay_credit(customer_id):
    try:
        data = RepayCreditSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400

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

            tx = CreditTransaction(
                ledger_id=ledger.id,
                type="REPAYMENT",
                amount=-amount,
                balance_after=ledger.balance,
                notes=notes or "Repayment received",
            )
            db.session.add(tx)

        db.session.commit()
        return format_response(
            True, data={"message": "Repayment successful", "remaining_balance": float(ledger.balance)}
        ), 200
    except ValueError as e:
        db.session.rollback()
        return format_response(False, error={"code": "UNPROCESSABLE_ENTITY", "message": str(e)}), 422
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500


@loyalty_bp.route("/loyalty/analytics", methods=["GET"])
@require_auth
def loyalty_analytics():
    store_id = g.current_user["store_id"]

    enrolled_customers = db.session.query(CustomerLoyaltyAccount).filter_by(store_id=store_id).count()

    today = datetime.now(timezone.utc)
    start_of_month = datetime(today.year, today.month, 1, tzinfo=timezone.utc)

    accounts = db.session.query(CustomerLoyaltyAccount.id).filter_by(store_id=store_id).subquery()

    from sqlalchemy import func

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

    # Needs to be absolute for redemption rate
    redeemed_abs = abs(float(redeemed_this_month))
    earned = float(earned_this_month)

    redemption_rate = (redeemed_abs / (earned + redeemed_abs)) if (earned + redeemed_abs) > 0 else 0

    data = {
        "enrolled_customers": enrolled_customers,
        "points_issued_this_month": earned,
        "points_redeemed_this_month": redeemed_abs,
        "redemption_rate_this_month": redemption_rate,
    }
    return format_response(True, data=data), 200
