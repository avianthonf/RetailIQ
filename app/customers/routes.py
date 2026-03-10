from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import and_, case, distinct, func

from .. import db
from ..auth.decorators import require_auth
from ..models import Category, Customer, Product, Transaction, TransactionItem
from ..utils.responses import standard_json
from . import customers_bp
from .schemas import CustomerCreateSchema, CustomerUpdateSchema
from .services import (
    get_customer_analytics,
    get_customer_summary_data,
    get_top_customers,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _customer_to_dict(c):
    return {
        "customer_id": c.customer_id,
        "store_id": c.store_id,
        "name": c.name,
        "mobile_number": c.mobile_number,
        "email": c.email,
        "gender": c.gender,
        "birth_date": c.birth_date.isoformat() if c.birth_date else None,
        "address": c.address,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ──────────────────────────────────────────────────────────────
# Static routes MUST come before /<int:customer_id>
# ──────────────────────────────────────────────────────────────


@customers_bp.route("/top", methods=["GET"])
@require_auth
def top_customers():
    """GET /customers/top?metric=revenue|visits&limit=10"""
    store_id = g.current_user["store_id"]
    metric = request.args.get("metric", "revenue")
    limit = min(int(request.args.get("limit", 10)), 100)

    data = get_top_customers(store_id, metric, limit)
    return standard_json(data=data)


@customers_bp.route("/analytics", methods=["GET"])
@require_auth
def analytics():
    """
    GET /customers/analytics
    Monthly stats (current calendar month, UTC).
    """
    store_id = g.current_user["store_id"]
    data = get_customer_analytics(store_id)
    return standard_json(data=data)


# ──────────────────────────────────────────────────────────────
# Collection endpoints
# ──────────────────────────────────────────────────────────────


@customers_bp.route("", methods=["GET"])
@require_auth
def list_customers():
    store_id = g.current_user["store_id"]
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    name_q = request.args.get("name")
    mobile_q = request.args.get("mobile")
    created_after = request.args.get("created_after")  # YYYY-MM-DD
    created_before = request.args.get("created_before")  # YYYY-MM-DD

    query = db.session.query(Customer).filter(Customer.store_id == store_id)

    if name_q:
        query = query.filter(Customer.name.ilike(f"%{name_q}%"))
    if mobile_q:
        query = query.filter(Customer.mobile_number.contains(mobile_q))
    if created_after:
        query = query.filter(Customer.created_at >= created_after)
    if created_before:
        query = query.filter(Customer.created_at <= created_before + " 23:59:59")

    total = query.count()
    customers = query.order_by(Customer.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return standard_json(
        data=[_customer_to_dict(c) for c in customers],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@customers_bp.route("", methods=["POST"])
@require_auth
def create_customer():
    store_id = g.current_user["store_id"]

    try:
        data = CustomerCreateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    # Duplicate mobile within same store
    existing = db.session.query(Customer).filter_by(store_id=store_id, mobile_number=data["mobile_number"]).first()
    if existing:
        return standard_json(
            success=False,
            message=f"A customer with mobile {data['mobile_number']} already exists in this store.",
            status_code=422,
            error={"code": "DUPLICATE_MOBILE"},
        )

    customer = Customer(
        store_id=store_id,
        name=data["name"],
        mobile_number=data["mobile_number"],
        email=data.get("email"),
        gender=data.get("gender"),
        birth_date=data.get("birth_date"),
        address=data.get("address"),
        notes=data.get("notes"),
        created_at=datetime.now(timezone.utc),
    )

    try:
        db.session.add(customer)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return standard_json(success=False, message=str(e), status_code=500, error={"code": "SERVER_ERROR"})

    return standard_json(data=_customer_to_dict(customer), status_code=201)


# ──────────────────────────────────────────────────────────────
# Single-resource endpoints
# ──────────────────────────────────────────────────────────────


@customers_bp.route("/<int:customer_id>", methods=["GET"])
@require_auth
def get_customer(customer_id):
    store_id = g.current_user["store_id"]
    customer = db.session.query(Customer).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not customer:
        return standard_json(success=False, message="Customer not found", status_code=404, error={"code": "NOT_FOUND"})
    return standard_json(data=_customer_to_dict(customer))


@customers_bp.route("/<int:customer_id>", methods=["PUT"])
@require_auth
def update_customer(customer_id):
    store_id = g.current_user["store_id"]
    customer = db.session.query(Customer).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not customer:
        return standard_json(success=False, message="Customer not found", status_code=404, error={"code": "NOT_FOUND"})

    try:
        data = CustomerUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return standard_json(success=False, message="Validation error", status_code=422, error=err.messages)

    # Duplicate mobile check (only if changing mobile)
    if "mobile_number" in data and data["mobile_number"] != customer.mobile_number:
        clash = db.session.query(Customer).filter_by(store_id=store_id, mobile_number=data["mobile_number"]).first()
        if clash:
            return standard_json(
                success=False,
                message=f"Mobile {data['mobile_number']} already belongs to another customer.",
                status_code=422,
                error={"code": "DUPLICATE_MOBILE"},
            )

    for field in ["name", "mobile_number", "email", "gender", "birth_date", "address", "notes"]:
        if field in data:
            setattr(customer, field, data[field])

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return standard_json(success=False, message=str(e), status_code=500, error={"code": "SERVER_ERROR"})

    return standard_json(data=_customer_to_dict(customer))


@customers_bp.route("/<int:customer_id>/transactions", methods=["GET"])
@require_auth
def customer_transactions(customer_id):
    store_id = g.current_user["store_id"]
    customer = db.session.query(Customer).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not customer:
        return standard_json(success=False, message="Customer not found", status_code=404, error={"code": "NOT_FOUND"})

    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    category_id = request.args.get("category_id", type=int)
    min_amount = request.args.get("min_amount", type=float)
    max_amount = request.args.get("max_amount", type=float)

    query = db.session.query(Transaction).filter(
        Transaction.store_id == store_id,
        Transaction.customer_id == customer_id,
        Transaction.is_return == False,
    )

    if date_from:
        query = query.filter(Transaction.created_at >= date_from)
    if date_to:
        query = query.filter(Transaction.created_at <= date_to + " 23:59:59")

    # category_id filter — join transaction_items → products
    if category_id is not None:
        query = (
            query.join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
            .join(Product, TransactionItem.product_id == Product.product_id)
            .filter(Product.category_id == category_id)
            .distinct()
        )

    # amount filter via subquery
    if min_amount is not None or max_amount is not None:
        amount_sq = (
            db.session.query(
                TransactionItem.transaction_id,
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount
                ).label("total"),
            )
            .group_by(TransactionItem.transaction_id)
            .subquery()
        )
        query = query.join(amount_sq, Transaction.transaction_id == amount_sq.c.transaction_id)
        if min_amount is not None:
            query = query.filter(amount_sq.c.total >= min_amount)
        if max_amount is not None:
            query = query.filter(amount_sq.c.total <= max_amount)

    total = query.count()
    txns = query.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    data = [
        {
            "transaction_id": str(t.transaction_id),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "payment_mode": t.payment_mode,
            "notes": t.notes,
        }
        for t in txns
    ]

    return standard_json(data=data, meta={"page": page, "page_size": page_size, "total": total})


@customers_bp.route("/<int:customer_id>/summary", methods=["GET"])
@require_auth
def customer_summary(customer_id):
    store_id = g.current_user["store_id"]
    customer = db.session.query(Customer).filter_by(customer_id=customer_id, store_id=store_id).first()
    if not customer:
        return standard_json(success=False, message="Customer not found", status_code=404, error={"code": "NOT_FOUND"})

    data = get_customer_summary_data(store_id, customer_id)
    return standard_json(data=data)

