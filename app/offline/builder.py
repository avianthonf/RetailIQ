import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models import Alert, Product


def build_snapshot(store_id, db):
    """
    Builds a compact analytics snapshot for offline use, enforcing a 50KB size limit.
    """
    snapshot = {
        "kpis": {
            "today_revenue": 0.0,
            "today_profit": 0.0,
            "today_transactions": 0,
            "yesterday_revenue": 0.0,
            "this_week_revenue": 0.0,
            "this_month_revenue": 0.0
        },
        "revenue_30d": [],
        "top_products_7d": [],
        "alerts_open": [],
        "low_stock_products": [],
        "built_at": datetime.now(timezone.utc).isoformat()
    }

    # Attempt to see if db is a raw session or Flask-SQLAlchemy db object
    session = getattr(db, 'session', db)

    # 1. Gather KPIs (using simple store aggregates)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    try:
        # fetch today's summary (aggregate)
        today_row = session.execute(
            text("SELECT revenue, profit, transaction_count FROM daily_store_summary WHERE store_id = :sid AND date = :d"),
            {"sid": store_id, "d": str(today)}
        ).fetchone()
        if today_row:
            snapshot["kpis"]["today_revenue"] = float(today_row.revenue or 0)
            snapshot["kpis"]["today_profit"] = float(today_row.profit or 0)
            snapshot["kpis"]["today_transactions"] = int(today_row.transaction_count or 0)

        # fetch yesterday
        yesterday_row = session.execute(
            text("SELECT revenue FROM daily_store_summary WHERE store_id = :sid AND date = :d"),
            {"sid": store_id, "d": str(yesterday)}
        ).fetchone()
        if yesterday_row:
            snapshot["kpis"]["yesterday_revenue"] = float(yesterday_row.revenue or 0)

        # fetch this week
        week_start = today - timedelta(days=today.weekday())
        week_row = session.execute(
            text("SELECT COALESCE(SUM(revenue), 0) FROM daily_store_summary WHERE store_id = :sid AND date >= :ws"),
            {"sid": store_id, "ws": str(week_start)}
        ).scalar()
        if week_row is not None:
            snapshot["kpis"]["this_week_revenue"] = float(week_row)

        # fetch this month
        month_start = today.replace(day=1)
        month_row = session.execute(
            text("SELECT COALESCE(SUM(revenue), 0) FROM daily_store_summary WHERE store_id = :sid AND date >= :ms"),
            {"sid": store_id, "ms": str(month_start)}
        ).scalar()
        if month_row is not None:
            snapshot["kpis"]["this_month_revenue"] = float(month_row)

    except Exception:
        pass # Handle gracefully, defaulting to 0s

    # 2. Daily revenue summary (30d)
    try:
        thirty_days_ago = today - timedelta(days=30)
        rev_history = session.execute(
            text("SELECT date as summary_date, revenue, profit FROM daily_store_summary WHERE store_id = :sid AND date >= :start ORDER BY date DESC"),
            {"sid": store_id, "start": str(thirty_days_ago)}
        ).fetchall()

        for row in rev_history:
            snapshot["revenue_30d"].append({
                "date": str(row.summary_date),
                "revenue": float(row.revenue or 0),
                "profit": float(row.profit or 0)
            })
    except Exception:
        pass

    # 3. Top Products 7d
    try:
        seven_days_ago = today - timedelta(days=7)
        top_products = session.execute(
            text("""
                SELECT p.product_id, p.name, COALESCE(SUM(dss.revenue), 0) as rev, COALESCE(SUM(dss.units_sold), 0) as units
                FROM daily_sku_summary dss
                JOIN products p ON dss.product_id = p.product_id
                WHERE dss.store_id = :sid AND dss.date >= :start
                GROUP BY p.product_id, p.name
                ORDER BY rev DESC LIMIT 5
            """),
            {"sid": store_id, "start": str(seven_days_ago)}
        ).fetchall()

        for p in top_products:
            snapshot["top_products_7d"].append({
                "product_id": str(p.product_id),
                "name": p.name,
                "revenue": float(p.rev or 0),
                "units_sold": int(p.units or 0)
            })
    except Exception:
        pass

    # 4. Open Alerts (up to 10)
    try:
        alerts = session.query(Alert).filter(
            Alert.store_id == store_id,
            Alert.status == 'OPEN'
        ).order_by(Alert.created_at.desc()).limit(10).all()

        for a in alerts:
            snapshot["alerts_open"].append({
                "id": str(a.alert_id),
                "priority": a.priority,
                "message": a.message,
                "created_at": a.created_at.isoformat() if a.created_at else None
            })
    except Exception:
        pass

    # 5. Low Stock Products
    try:
        low_stock = session.query(Product).filter(
            Product.store_id == store_id,
            Product.current_stock <= Product.reorder_level,
            Product.is_active is True
        ).limit(100).all() # hard limit to keep size sane

        for p in low_stock:
            snapshot["low_stock_products"].append({
                "product_id": str(p.product_id),
                "name": p.name,
                "current_stock": float(p.current_stock) if p.current_stock else 0,
                "reorder_point": float(p.reorder_level) if p.reorder_level else 0
            })
    except Exception:
        pass

    # ENFORCE SIZE LIMIT (50KB)
    serialized = json.dumps(snapshot)
    if len(serialized.encode('utf-8')) > 50 * 1024:
        # Truncate revenue to 14 days and top products to 3
        snapshot["revenue_30d"] = snapshot["revenue_30d"][:14]
        snapshot["top_products_7d"] = snapshot["top_products_7d"][:3]

        # Optionally, truncate low stock if still too large, but 50KB is around 50,000 characters
        # which easily fits 14 days history, 3 products, 10 alerts, and maybe 100 low stock items.
        # Just to be extremely safe, we clamp low_stock too if needed
        serialized_fallback = json.dumps(snapshot)
        if len(serialized_fallback.encode('utf-8')) > 50 * 1024:
            snapshot["low_stock_products"] = snapshot["low_stock_products"][:20]

    return snapshot
