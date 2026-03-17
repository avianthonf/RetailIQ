from datetime import date, datetime, timedelta, timezone

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import func

from .. import db
from ..auth.decorators import require_auth, require_role
from ..models import Product, Transaction, TransactionItem
from ..utils.responses import standard_json
from ..utils.webhooks import broadcast_event
from . import transactions_bp
from .schemas import BatchTransactionCreateSchema, TransactionCreateSchema, TransactionReturnSchema
from .services import (
    get_daily_summary_data,
    process_batch_transactions,
    process_return_transaction,
    process_single_transaction,
)


@transactions_bp.route("/", methods=["POST"])
@transactions_bp.route("", methods=["POST"])
@require_auth
def create_transaction():
    try:
        data = TransactionCreateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]
    role = g.current_user["role"]

    session_id = None
    if role == "staff":
        from ..models import StaffSession

        open_session = (
            db.session.query(StaffSession)
            .filter(StaffSession.store_id == store_id, StaffSession.user_id == user_id, StaffSession.status == "OPEN")
            .first()
        )
        if open_session:
            session_id = open_session.id

    try:
        txn = process_single_transaction(data, store_id, session_id=session_id)
        db.session.commit()

        # Broadcast Webhook Event
        broadcast_event(
            "transaction.created",
            {
                "transaction_id": str(txn.transaction_id),
                "store_id": store_id,
                "total": float(txn.total_amount),
                "payment_mode": txn.payment_mode,
            },
            required_scope="read:sales",
        )

        return standard_json(data={"transaction_id": str(txn.transaction_id)}, status_code=201)
    except ValueError as e:
        db.session.rollback()
        if "Credit limit" in str(e):
            return standard_json(success=False, message=str(e), status_code=422, error={"code": "UNPROCESSABLE_ENTITY"})
        return standard_json(success=False, message=str(e), status_code=422, error={"code": "BAD_REQUEST"})
    except Exception as e:
        db.session.rollback()
        return standard_json(success=False, message=str(e), status_code=500, error={"code": "SERVER_ERROR"})


@transactions_bp.route("/batch", methods=["POST"])
@transactions_bp.route("/batch/", methods=["POST"])
@require_auth
def create_batch_transactions():
    try:
        data = BatchTransactionCreateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]
    user_id = g.current_user["user_id"]
    role = g.current_user["role"]

    session_id = None
    if role == "staff":
        from ..models import StaffSession

        open_session = (
            db.session.query(StaffSession)
            .filter(StaffSession.store_id == store_id, StaffSession.user_id == user_id, StaffSession.status == "OPEN")
            .first()
        )
        if open_session:
            session_id = open_session.id

    result = process_batch_transactions(data["transactions"], store_id, session_id=session_id)
    db.session.commit()
    return standard_json(data=result)


@transactions_bp.route("/", methods=["GET"])
@transactions_bp.route("", methods=["GET"])
@require_auth
def get_transactions():
    store_id = g.current_user["store_id"]
    role = g.current_user["role"]

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    payment_mode = request.args.get("payment_mode")
    customer_id = request.args.get("customer_id")

    query = db.session.query(Transaction).filter(Transaction.store_id == store_id)

    if role == "staff":
        # Enforce today only
        from datetime import datetime, timezone

        today_date = datetime.now(timezone.utc).date()
        query = query.filter(func.date(Transaction.created_at) == today_date)
    else:
        if start_date:
            query = query.filter(func.date(Transaction.created_at) >= start_date)
        if end_date:
            query = query.filter(func.date(Transaction.created_at) <= end_date)

    if payment_mode:
        query = query.filter(Transaction.payment_mode == payment_mode)
    if customer_id:
        query = query.filter(Transaction.customer_id == customer_id)

    min_amount = request.args.get("min_amount")
    max_amount = request.args.get("max_amount")

    if min_amount or max_amount:
        amount_subq = (
            db.session.query(
                TransactionItem.transaction_id,
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount
                ).label("total"),
            )
            .group_by(TransactionItem.transaction_id)
            .subquery()
        )

        query = query.join(amount_subq, Transaction.transaction_id == amount_subq.c.transaction_id)

        if min_amount:
            query = query.filter(amount_subq.c.total >= float(min_amount))
        if max_amount:
            query = query.filter(amount_subq.c.total <= float(max_amount))

    total = query.count()
    transactions = query.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for t in transactions:
        result.append(
            {
                "transaction_id": str(t.transaction_id),
                "created_at": t.created_at.isoformat(),
                "payment_mode": t.payment_mode,
                "customer_id": t.customer_id,
                "is_return": t.is_return,
            }
        )

    return standard_json(data=result, meta={"page": page, "page_size": page_size, "total": total})


@transactions_bp.route("/<uuid:id>", methods=["GET"])
@require_auth
def get_transaction(id):
    store_id = g.current_user["store_id"]
    txn = db.session.query(Transaction).filter_by(transaction_id=id, store_id=store_id).first()

    if not txn:
        return standard_json(success=False, message="Transaction not found", status_code=404)

    items = db.session.query(TransactionItem).filter_by(transaction_id=txn.transaction_id).all()

    items_data = []
    for item in items:
        product = db.session.query(Product).filter_by(product_id=item.product_id).first()
        items_data.append(
            {
                "product_id": item.product_id,
                "product_name": product.name if product else None,
                "quantity": float(item.quantity) if item.quantity else 0,
                "selling_price": float(item.selling_price) if item.selling_price else 0,
                "discount_amount": float(item.discount_amount) if item.discount_amount else 0,
            }
        )

    data = {
        "transaction_id": str(txn.transaction_id),
        "created_at": txn.created_at.isoformat(),
        "payment_mode": txn.payment_mode,
        "customer_id": txn.customer_id,
        "notes": txn.notes,
        "is_return": txn.is_return,
        "original_transaction_id": str(txn.original_transaction_id) if txn.original_transaction_id else None,
        "line_items": items_data,
    }

    return standard_json(data=data)


@transactions_bp.route("/<uuid:id>/return", methods=["POST"])
@require_auth
@require_role("owner")
def return_transaction(id):
    try:
        data = TransactionReturnSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    store_id = g.current_user["store_id"]

    try:
        ret_txn = process_return_transaction(id, data, store_id)
        db.session.commit()
        return standard_json(data={"return_transaction_id": str(ret_txn.transaction_id)}, status_code=201)
    except ValueError as e:
        db.session.rollback()
        return standard_json(success=False, message=str(e), status_code=422, error={"code": "BAD_REQUEST"})
    except Exception as e:
        db.session.rollback()
        return standard_json(success=False, message=str(e), status_code=500, error={"code": "SERVER_ERROR"})


@transactions_bp.route("/summary/daily", methods=["GET"])
@require_auth
def get_daily_summary():
    store_id = g.current_user["store_id"]
    date_str = request.args.get("date", datetime.now(timezone.utc).date().isoformat())

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return standard_json(
            success=False, message="Date must be YYYY-MM-DD", status_code=422, error={"code": "INVALID_DATE"}
        )

    summary = get_daily_summary_data(store_id, target_date)
    return standard_json(data=summary)
