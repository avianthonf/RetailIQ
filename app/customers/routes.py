from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import and_, case, distinct, func

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import Category, Customer, Product, Transaction, TransactionItem
from . import customers_bp
from .schemas import CustomerCreateSchema, CustomerUpdateSchema

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _customer_to_dict(c):
    return {
        "customer_id":   c.customer_id,
        "store_id":      c.store_id,
        "name":          c.name,
        "mobile_number": c.mobile_number,
        "email":         c.email,
        "gender":        c.gender,
        "birth_date":    c.birth_date.isoformat() if c.birth_date else None,
        "address":       c.address,
        "notes":         c.notes,
        "created_at":    c.created_at.isoformat() if c.created_at else None,
    }


def _txn_total(txn_id_col):
    """SQL expression: sum of line-item revenue for a transaction."""
    return func.sum(
        TransactionItem.quantity * TransactionItem.selling_price
        - TransactionItem.discount_amount
    )


# ──────────────────────────────────────────────────────────────
# Static routes MUST come before /<int:customer_id>
# ──────────────────────────────────────────────────────────────

@customers_bp.route('/top', methods=['GET'])
@require_auth
def top_customers():
    """GET /customers/top?metric=revenue|visits&limit=10"""
    store_id = g.current_user['store_id']
    metric   = request.args.get('metric', 'revenue')
    limit    = min(int(request.args.get('limit', 10)), 100)

    # Aggregate over non-return transactions that have a customer
    base = (
        db.session.query(Transaction.customer_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return is False,
            Transaction.customer_id.isnot(None),
        )
    )

    if metric == 'visits':
        agg = (
            base.with_entities(
                Transaction.customer_id,
                func.count(distinct(Transaction.transaction_id)).label('metric_value'),
            )
            .group_by(Transaction.customer_id)
            .order_by(func.count(distinct(Transaction.transaction_id)).desc())
            .limit(limit)
            .all()
        )
    else:  # revenue (default)
        agg = (
            db.session.query(
                Transaction.customer_id,
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price
                    - TransactionItem.discount_amount
                ).label('metric_value'),
            )
            .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
            .filter(
                Transaction.store_id == store_id,
                Transaction.is_return is False,
                Transaction.customer_id.isnot(None),
            )
            .group_by(Transaction.customer_id)
            .order_by(
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price
                    - TransactionItem.discount_amount
                ).desc()
            )
            .limit(limit)
            .all()
        )

    if not agg:
        return format_response(True, data=[]), 200

    cids = [row.customer_id for row in agg]
    customers = {
        c.customer_id: c
        for c in db.session.query(Customer).filter(Customer.customer_id.in_(cids)).all()
    }

    data = []
    for row in agg:
        c = customers.get(row.customer_id)
        data.append({
            "customer_id":   row.customer_id,
            "name":          c.name if c else None,
            "mobile_number": c.mobile_number if c else None,
            "metric":        metric,
            "metric_value":  float(row.metric_value) if row.metric_value is not None else 0.0,
        })

    return format_response(True, data=data), 200


@customers_bp.route('/analytics', methods=['GET'])
@require_auth
def analytics():
    """
    GET /customers/analytics
    Monthly stats (current calendar month, UTC).
    """
    store_id = g.current_user['store_id']
    now      = datetime.now(timezone.utc)
    # Use naive UTC month_start so datetime comparisons work for both
    # SQLite (tests, stores naive datetimes) and PostgreSQL (production).
    month_start = datetime(now.year, now.month, 1)  # naive UTC

    # ── customers who made at least one purchase this month ──────────────────
    month_buyers_sq = (
        db.session.query(Transaction.customer_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return is False,
            Transaction.customer_id.isnot(None),
            Transaction.created_at >= month_start,
        )
        .distinct()
        .subquery()
    )

    unique_customers_month = db.session.query(
        func.count()
    ).select_from(month_buyers_sq).scalar() or 0

    # ── new customers: first transaction ever is this month ──────────────────
    first_txn_sq = (
        db.session.query(
            Transaction.customer_id,
            func.min(Transaction.created_at).label('first_at'),
        )
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return is False,
            Transaction.customer_id.isnot(None),
        )
        .group_by(Transaction.customer_id)
        .subquery()
    )

    new_customers = db.session.query(func.count()).filter(
        first_txn_sq.c.first_at >= month_start
    ).scalar() or 0

    # Must have purchased this month AND have 2+ prior transactions
    repeat_customers = db.session.query(
        func.count(distinct(Transaction.customer_id))
    ).filter(
        Transaction.store_id == store_id,
        Transaction.is_return is False,
        Transaction.customer_id.isnot(None),
        Transaction.created_at >= month_start,
        Transaction.customer_id.in_(
            db.session.query(Transaction.customer_id)
            .filter(
                Transaction.store_id == store_id,
                Transaction.is_return is False,
                Transaction.customer_id.isnot(None),
                Transaction.created_at < month_start,
            )
            .group_by(Transaction.customer_id)
            .having(func.count(Transaction.transaction_id) >= 1)
        ),
    ).scalar() or 0

    repeat_rate_pct = (
        round(repeat_customers / unique_customers_month * 100, 2)
        if unique_customers_month > 0 else 0.0
    )

    # ── revenue split: new vs repeat ─────────────────────────────────────────
    new_cids = (
        db.session.query(first_txn_sq.c.customer_id)
        .filter(first_txn_sq.c.first_at >= month_start)
        .subquery()
    )

    def _month_revenue(cid_filter):
        q = (
            db.session.query(
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price
                    - TransactionItem.discount_amount
                )
            )
            .join(Transaction, Transaction.transaction_id == TransactionItem.transaction_id)
            .filter(
                Transaction.store_id == store_id,
                Transaction.is_return is False,
                Transaction.customer_id.isnot(None),
                Transaction.created_at >= month_start,
            )
        )
        if cid_filter == 'new':
            q = q.filter(Transaction.customer_id.in_(
                db.session.query(new_cids.c.customer_id)
            ))
        else:
            q = q.filter(~Transaction.customer_id.in_(
                db.session.query(new_cids.c.customer_id)
            ))
        return float(q.scalar() or 0)

    new_revenue    = _month_revenue('new')
    repeat_revenue = _month_revenue('repeat')

    return format_response(True, data={
        "unique_customers_month": unique_customers_month,
        "new_customers":          new_customers,
        "repeat_customers":       repeat_customers,
        "repeat_rate_pct":        repeat_rate_pct,
        "new_revenue":            new_revenue,
        "repeat_revenue":         repeat_revenue,
    }), 200


# ──────────────────────────────────────────────────────────────
# Collection endpoints
# ──────────────────────────────────────────────────────────────

@customers_bp.route('', methods=['GET'])
@require_auth
def list_customers():
    store_id  = g.current_user['store_id']
    page      = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    name_q    = request.args.get('name')
    mobile_q  = request.args.get('mobile')
    created_after  = request.args.get('created_after')    # YYYY-MM-DD
    created_before = request.args.get('created_before')   # YYYY-MM-DD

    query = db.session.query(Customer).filter(Customer.store_id == store_id)

    if name_q:
        query = query.filter(Customer.name.ilike(f'%{name_q}%'))
    if mobile_q:
        query = query.filter(Customer.mobile_number.contains(mobile_q))
    if created_after:
        query = query.filter(Customer.created_at >= created_after)
    if created_before:
        query = query.filter(Customer.created_at <= created_before + ' 23:59:59')

    total    = query.count()
    customers = (
        query
        .order_by(Customer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return format_response(
        True,
        data=[_customer_to_dict(c) for c in customers],
        meta={"page": page, "page_size": page_size, "total": total},
    ), 200


@customers_bp.route('', methods=['POST'])
@require_auth
def create_customer():
    store_id = g.current_user['store_id']

    try:
        data = CustomerCreateSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 422

    # Duplicate mobile within same store
    existing = db.session.query(Customer).filter_by(
        store_id=store_id, mobile_number=data['mobile_number']
    ).first()
    if existing:
        return format_response(
            False,
            error={"code": "DUPLICATE_MOBILE",
                   "message": f"A customer with mobile {data['mobile_number']} already exists in this store."}
        ), 422

    customer = Customer(
        store_id=store_id,
        name=data['name'],
        mobile_number=data['mobile_number'],
        email=data.get('email'),
        gender=data.get('gender'),
        birth_date=data.get('birth_date'),
        address=data.get('address'),
        notes=data.get('notes'),
        created_at=datetime.now(timezone.utc),
    )

    try:
        db.session.add(customer)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500

    return format_response(True, data=_customer_to_dict(customer)), 201


# ──────────────────────────────────────────────────────────────
# Single-resource endpoints
# ──────────────────────────────────────────────────────────────

@customers_bp.route('/<int:customer_id>', methods=['GET'])
@require_auth
def get_customer(customer_id):
    store_id = g.current_user['store_id']
    customer = db.session.query(Customer).filter_by(
        customer_id=customer_id, store_id=store_id
    ).first()
    if not customer:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Customer not found"}), 404
    return format_response(True, data=_customer_to_dict(customer)), 200


@customers_bp.route('/<int:customer_id>', methods=['PUT'])
@require_auth
def update_customer(customer_id):
    store_id = g.current_user['store_id']
    customer = db.session.query(Customer).filter_by(
        customer_id=customer_id, store_id=store_id
    ).first()
    if not customer:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Customer not found"}), 404

    try:
        data = CustomerUpdateSchema().load(request.json or {})
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 422

    # Duplicate mobile check (only if changing mobile)
    if 'mobile_number' in data and data['mobile_number'] != customer.mobile_number:
        clash = db.session.query(Customer).filter_by(
            store_id=store_id, mobile_number=data['mobile_number']
        ).first()
        if clash:
            return format_response(
                False,
                error={"code": "DUPLICATE_MOBILE",
                       "message": f"Mobile {data['mobile_number']} already belongs to another customer."}
            ), 422

    for field in ['name', 'mobile_number', 'email', 'gender', 'birth_date', 'address', 'notes']:
        if field in data:
            setattr(customer, field, data[field])

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500

    return format_response(True, data=_customer_to_dict(customer)), 200


@customers_bp.route('/<int:customer_id>/transactions', methods=['GET'])
@require_auth
def customer_transactions(customer_id):
    store_id  = g.current_user['store_id']
    customer  = db.session.query(Customer).filter_by(
        customer_id=customer_id, store_id=store_id
    ).first()
    if not customer:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Customer not found"}), 404

    page      = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    date_from = request.args.get('date_from')
    date_to   = request.args.get('date_to')
    category_id  = request.args.get('category_id', type=int)
    min_amount   = request.args.get('min_amount',   type=float)
    max_amount   = request.args.get('max_amount',   type=float)

    query = (
        db.session.query(Transaction)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return is False,
        )
    )

    if date_from:
        query = query.filter(Transaction.created_at >= date_from)
    if date_to:
        query = query.filter(Transaction.created_at <= date_to + ' 23:59:59')

    # category_id filter — join transaction_items → products
    if category_id is not None:
        query = query.join(
            TransactionItem,
            Transaction.transaction_id == TransactionItem.transaction_id
        ).join(
            Product,
            TransactionItem.product_id == Product.product_id
        ).filter(Product.category_id == category_id).distinct()

    # amount filter via subquery
    if min_amount is not None or max_amount is not None:
        amount_sq = (
            db.session.query(
                TransactionItem.transaction_id,
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price
                    - TransactionItem.discount_amount
                ).label('total'),
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
    txns  = (
        query
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    data = [
        {
            "transaction_id": str(t.transaction_id),
            "created_at":     t.created_at.isoformat() if t.created_at else None,
            "payment_mode":   t.payment_mode,
            "notes":          t.notes,
        }
        for t in txns
    ]

    return format_response(True, data=data,
                           meta={"page": page, "page_size": page_size, "total": total}), 200


@customers_bp.route('/<int:customer_id>/summary', methods=['GET'])
@require_auth
def customer_summary(customer_id):
    store_id = g.current_user['store_id']
    customer = db.session.query(Customer).filter_by(
        customer_id=customer_id, store_id=store_id
    ).first()
    if not customer:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Customer not found"}), 404

    # ── Lifetime spend + visit count ─────────────────────────────────────────
    spend_row = (
        db.session.query(
            func.count(distinct(Transaction.transaction_id)).label('visit_count'),
            func.sum(
                TransactionItem.quantity * TransactionItem.selling_price
                - TransactionItem.discount_amount
            ).label('total_spend'),
            func.max(Transaction.created_at).label('last_visit'),
        )
        .select_from(Transaction)
        .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return is False,
        )
        .one()
    )

    visit_count          = spend_row.visit_count or 0
    total_lifetime_spend = float(spend_row.total_spend or 0)
    last_visit_date      = spend_row.last_visit.date().isoformat() if spend_row.last_visit else None
    avg_basket_size      = round(total_lifetime_spend / visit_count, 2) if visit_count else 0.0

    # ── Top category by spend ────────────────────────────────────────────────
    top_cat_row = (
        db.session.query(
            Product.category_id,
            Category.name.label('category_name'),
            func.sum(
                TransactionItem.quantity * TransactionItem.selling_price
                - TransactionItem.discount_amount
            ).label('cat_spend'),
        )
        .select_from(Transaction)
        .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
        .join(Product, TransactionItem.product_id == Product.product_id)
        .outerjoin(Category, Product.category_id == Category.category_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return is False,
        )
        .group_by(Product.category_id, Category.name)
        .order_by(func.sum(
            TransactionItem.quantity * TransactionItem.selling_price
            - TransactionItem.discount_amount
        ).desc())
        .first()
    )

    top_category = (
        {"category_id": top_cat_row.category_id, "name": top_cat_row.category_name}
        if top_cat_row else None
    )

    # ── Repeat customer: 3+ transactions within ANY rolling 90-day window ────
    # We fetch all transaction timestamps then do a sliding-window check in Python.
    # This is acceptable because the list per-customer is small.
    txn_dates = [
        row.created_at
        for row in db.session.query(Transaction.created_at)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return is False,
        )
        .order_by(Transaction.created_at)
        .all()
    ]

    is_repeat_customer = False
    window = timedelta(days=90)
    for i, anchor in enumerate(txn_dates):
        count_in_window = sum(
            1 for t in txn_dates[i:]
            if t - anchor <= window
        )
        if count_in_window >= 3:
            is_repeat_customer = True
            break

    return format_response(True, data={
        "customer_id":          customer_id,
        "total_lifetime_spend": total_lifetime_spend,
        "visit_count":          visit_count,
        "avg_basket_size":      avg_basket_size,
        "last_visit_date":      last_visit_date,
        "top_category":         top_category,
        "is_repeat_customer":   is_repeat_customer,
    }), 200
