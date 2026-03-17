"""RetailIQ Customer Services."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_top_customers(store_id: int, metric: str = "revenue", limit: int = 10) -> list[dict]:
    from sqlalchemy import func, text

    from app import db

    if metric == "visits":
        order_col = "visit_count"
    else:
        order_col = "total_revenue"

    rows = db.session.execute(
        text(f"""
        SELECT
            c.customer_id,
            c.name,
            c.mobile_number,
            COUNT(t.transaction_id)             AS visit_count,
            COALESCE(SUM(
                (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                 FROM transaction_items ti WHERE ti.transaction_id = t.transaction_id)
            ), 0)                                AS total_revenue
        FROM customers c
        JOIN transactions t ON t.customer_id = c.customer_id
            AND t.store_id = :sid AND t.is_return = FALSE
        WHERE c.store_id = :sid
        GROUP BY c.customer_id, c.name, c.mobile_number
        ORDER BY {order_col} DESC
        LIMIT :limit
        """),
        {"sid": store_id, "limit": limit},
    ).fetchall()

    return [
        {
            "customer_id": r.customer_id,
            "name": r.name,
            "mobile_number": r.mobile_number,
            "visit_count": r.visit_count,
            "total_revenue": round(float(r.total_revenue), 2),
        }
        for r in rows
    ]


def get_customer_analytics(store_id: int) -> dict:
    from sqlalchemy import text

    from app import db

    today = datetime.now(timezone.utc).date()
    month_start = str(today.replace(day=1))

    # Detailed CTE for accurate categorization and revenue calculation
    result = db.session.execute(
        text("""
        WITH txn_amounts AS (
            SELECT
                t.transaction_id,
                t.customer_id,
                t.created_at,
                (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                 FROM transaction_items ti WHERE ti.transaction_id = t.transaction_id) as amount
            FROM transactions t
            WHERE t.store_id = :sid AND t.is_return = FALSE
        ),
        customer_stats AS (
            SELECT
                customer_id,
                MIN(created_at) as first_txn_at,
                MAX(created_at) as last_txn_at,
                SUM(CASE WHEN created_at >= :month_start THEN amount ELSE 0 END) as month_revenue,
                SUM(amount) as total_revenue
            FROM txn_amounts
            GROUP BY customer_id
        )
        SELECT
            COUNT(DISTINCT CASE WHEN last_txn_at >= :month_start THEN customer_id END) as unique_customers_month,
            COUNT(DISTINCT CASE WHEN first_txn_at >= :month_start THEN customer_id END) as new_customers,
            SUM(CASE WHEN first_txn_at >= :month_start THEN month_revenue ELSE 0 END) as new_revenue,
            SUM(CASE WHEN first_txn_at < :month_start AND last_txn_at >= :month_start THEN month_revenue ELSE 0 END) as repeat_revenue,
            COALESCE(AVG(total_revenue), 0) as avg_lifetime_value
        FROM customer_stats
        """),
        {"sid": store_id, "month_start": month_start},
    ).fetchone()

    new_customers = result.new_customers or 0
    total_active = result.unique_customers_month or 0
    repeat_customers = max(0, total_active - new_customers)

    return {
        "new_customers": new_customers,
        "unique_customers_month": total_active,
        "new_revenue": round(float(result.new_revenue or 0), 2),
        "repeat_customers": repeat_customers,
        "repeat_revenue": round(float(result.repeat_revenue or 0), 2),
        "repeat_rate_pct": (repeat_customers / total_active * 100) if total_active > 0 else 0.0,
        "avg_lifetime_value": round(float(result.avg_lifetime_value or 0), 2),
    }


def get_customer_summary_data(store_id: int, customer_id: int) -> dict:
    from sqlalchemy import text

    from app import db

    row = db.session.execute(
        text("""
        SELECT
            COUNT(t.transaction_id)                              AS total_visits,
            COALESCE(MAX(t.created_at), NULL)                    AS last_visit,
            COALESCE(SUM(
                (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                 FROM transaction_items ti WHERE ti.transaction_id = t.transaction_id)
            ), 0)                                                AS total_spent,
            COALESCE(AVG(
                (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                 FROM transaction_items ti WHERE ti.transaction_id = t.transaction_id)
            ), 0)                                                AS avg_basket
        FROM transactions t
        WHERE t.store_id = :sid AND t.customer_id = :cid AND t.is_return = FALSE
        """),
        {"sid": store_id, "cid": customer_id},
    ).fetchone()

    repeat_check = db.session.execute(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM transactions t1
            WHERE t1.customer_id = :cid AND t1.store_id = :sid AND t1.is_return = FALSE
            AND (
                SELECT COUNT(*) FROM transactions t2
                WHERE t2.customer_id = t1.customer_id AND t2.store_id = t1.store_id AND t2.is_return = FALSE
                AND t2.created_at BETWEEN datetime(t1.created_at, '-90 days') AND t1.created_at
            ) >= 3
        )
        """),
        {"sid": store_id, "cid": customer_id},
    ).scalar()

    return {
        "visit_count": row.total_visits or 0,
        "last_visit_date": row.last_visit.isoformat() if hasattr(row.last_visit, "isoformat") else row.last_visit,
        "total_lifetime_spend": round(float(row.total_spent or 0), 2),
        "avg_basket_size": round(float(row.avg_basket or 0), 2),
        "is_repeat_customer": bool(repeat_check),
    }
