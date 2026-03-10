from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, case, distinct, func
from .. import db
from ..models import Category, Customer, Product, Transaction, TransactionItem

def get_top_customers(store_id, metric, limit):
    # Aggregate over non-return transactions that have a customer
    base = db.session.query(Transaction.customer_id).filter(
        Transaction.store_id == store_id,
        Transaction.is_return == False,
        Transaction.customer_id.isnot(None),
    )

    if metric == "visits":
        agg = (
            base.with_entities(
                Transaction.customer_id,
                func.count(distinct(Transaction.transaction_id)).label("metric_value"),
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
                    TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount
                ).label("metric_value"),
            )
            .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
            .filter(
                Transaction.store_id == store_id,
                Transaction.is_return == False,
                Transaction.customer_id.isnot(None),
            )
            .group_by(Transaction.customer_id)
            .order_by(
                func.sum(
                    TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount
                ).desc()
            )
            .limit(limit)
            .all()
        )

    if not agg:
        return []

    cids = [row.customer_id for row in agg]
    customers = {c.customer_id: c for c in db.session.query(Customer).filter(Customer.customer_id.in_(cids)).all()}

    data = []
    for row in agg:
        c = customers.get(row.customer_id)
        data.append(
            {
                "customer_id": row.customer_id,
                "name": c.name if c else None,
                "mobile_number": c.mobile_number if c else None,
                "metric": metric,
                "metric_value": float(row.metric_value) if row.metric_value is not None else 0.0,
            }
        )
    return data

def get_customer_analytics(store_id):
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1)

    # buyers this month
    month_buyers_sq = (
        db.session.query(Transaction.customer_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return == False,
            Transaction.customer_id.isnot(None),
            Transaction.created_at >= month_start,
        )
        .distinct()
        .subquery()
    )
    unique_customers_month = db.session.query(func.count()).select_from(month_buyers_sq).scalar() or 0

    # new customers
    first_txn_sq = (
        db.session.query(
            Transaction.customer_id,
            func.min(Transaction.created_at).label("first_at"),
        )
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return == False,
            Transaction.customer_id.isnot(None),
        )
        .group_by(Transaction.customer_id)
        .subquery()
    )
    new_customers = db.session.query(func.count()).filter(first_txn_sq.c.first_at >= month_start).scalar() or 0

    # repeat customers
    repeat_customers = (
        db.session.query(func.count(distinct(Transaction.customer_id)))
        .filter(
            Transaction.store_id == store_id,
            Transaction.is_return == False,
            Transaction.customer_id.isnot(None),
            Transaction.created_at >= month_start,
            Transaction.customer_id.in_(
                db.session.query(Transaction.customer_id)
                .filter(
                    Transaction.store_id == store_id,
                    Transaction.is_return == False,
                    Transaction.customer_id.isnot(None),
                    Transaction.created_at < month_start,
                )
                .group_by(Transaction.customer_id)
                .having(func.count(Transaction.transaction_id) >= 1)
            ),
        )
        .scalar()
        or 0
    )

    repeat_rate_pct = round(repeat_customers / unique_customers_month * 100, 2) if unique_customers_month > 0 else 0.0

    # revenue split
    new_cids = db.session.query(first_txn_sq.c.customer_id).filter(first_txn_sq.c.first_at >= month_start).subquery()

    def _month_revenue(cid_filter):
        q = (
            db.session.query(
                func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount)
            )
            .join(Transaction, Transaction.transaction_id == TransactionItem.transaction_id)
            .filter(
                Transaction.store_id == store_id,
                Transaction.is_return == False,
                Transaction.customer_id.isnot(None),
                Transaction.created_at >= month_start,
            )
        )
        if cid_filter == "new":
            q = q.filter(Transaction.customer_id.in_(db.session.query(new_cids.c.customer_id)))
        else:
            q = q.filter(~Transaction.customer_id.in_(db.session.query(new_cids.c.customer_id)))
        return float(q.scalar() or 0)

    return {
        "unique_customers_month": unique_customers_month,
        "new_customers": new_customers,
        "repeat_customers": repeat_customers,
        "repeat_rate_pct": repeat_rate_pct,
        "new_revenue": _month_revenue("new"),
        "repeat_revenue": _month_revenue("repeat"),
    }

def get_customer_summary_data(store_id, customer_id):
    spend_row = (
        db.session.query(
            func.count(distinct(Transaction.transaction_id)).label("visit_count"),
            func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).label(
                "total_spend"
            ),
            func.max(Transaction.created_at).label("last_visit"),
        )
        .select_from(Transaction)
        .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return == False,
        )
        .one()
    )

    visit_count = spend_row.visit_count or 0
    total_lifetime_spend = float(spend_row.total_spend or 0)
    last_visit_date = spend_row.last_visit.date().isoformat() if spend_row.last_visit else None
    avg_basket_size = round(total_lifetime_spend / visit_count, 2) if visit_count else 0.0

    top_cat_row = (
        db.session.query(
            Product.category_id,
            Category.name.label("category_name"),
            func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).label(
                "cat_spend"
            ),
        )
        .select_from(Transaction)
        .join(TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id)
        .join(Product, TransactionItem.product_id == Product.product_id)
        .outerjoin(Category, Product.category_id == Category.category_id)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return == False,
        )
        .group_by(Product.category_id, Category.name)
        .order_by(
            func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).desc()
        )
        .first()
    )

    top_category = {"category_id": top_cat_row.category_id, "name": top_cat_row.category_name} if top_cat_row else None

    # Repeat check (90 day window)
    txn_dates = [
        row.created_at
        for row in db.session.query(Transaction.created_at)
        .filter(
            Transaction.store_id == store_id,
            Transaction.customer_id == customer_id,
            Transaction.is_return == False,
        )
        .order_by(Transaction.created_at)
        .all()
    ]

    is_repeat_customer = False
    window = timedelta(days=90)
    for i, anchor in enumerate(txn_dates):
        count_in_window = sum(1 for t in txn_dates[i:] if t - anchor <= window)
        if count_in_window >= 3:
            is_repeat_customer = True
            break

    return {
        "customer_id": customer_id,
        "total_lifetime_spend": total_lifetime_spend,
        "visit_count": visit_count,
        "avg_basket_size": avg_basket_size,
        "last_visit_date": last_visit_date,
        "top_category": top_category,
        "is_repeat_customer": is_repeat_customer,
    }
