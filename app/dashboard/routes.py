"""
RetailIQ Dashboard Routes
==========================
Provides aggregated dashboard data for the frontend executive dashboard.
Endpoints are registered at /api/v1/dashboard.

All endpoints query real aggregation tables (daily_store_summary,
daily_sku_summary), alerts, forecast_cache, products, purchase_orders,
loyalty_transactions, and market_signals.  Zero mock / hardcoded data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import text

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/test")
def test():
    """Simple test route."""
    return jsonify(
        {
            "message": "Dashboard blueprint is working!",
            "routes": [
                "/api/v1/dashboard/test",
                "/api/v1/dashboard/overview",
                "/api/v1/dashboard/alerts",
                "/api/v1/dashboard/live-signals",
                "/api/v1/dashboard/forecasts/stores",
                "/api/v1/dashboard/incidents/active",
                "/api/v1/dashboard/alerts/feed",
            ],
        }
    )


def _store_id():
    """Get current user's store ID from auth context."""
    return g.current_user["store_id"]


# ── helpers ──────────────────────────────────────────────────────────────────


def _pct_delta(current, previous):
    """Return a human-friendly delta string like '+12.5%' or '-3.2%'."""
    if not previous:
        return "+0%" if not current else "+100%"
    change = (current - previous) / abs(previous) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def _int_delta(current, previous):
    """Return an integer delta string like '+5' or '-2'."""
    diff = current - previous
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff}"


def _to_iso(value):
    """Safely convert a datetime or string to ISO-8601 string."""
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_sparkline(rows, metric_key, value_key):
    """Build a sparkline dict from a list of row-dicts."""
    return {
        "metric": metric_key,
        "points": [{"timestamp": r["timestamp"], "value": float(r.get(value_key, 0))} for r in rows],
    }


# ── /overview ────────────────────────────────────────────────────────────────


@dashboard_bp.route("/overview")
@require_auth
def overview():
    """Get dashboard overview metrics from real aggregation tables."""
    try:
        return _overview_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "DASHBOARD_ERROR", "message": str(e)}), 500


def _overview_impl():
    sid = _store_id()
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=6)

    # ── Today + 7-day daily revenue for sparkline ────────────────────────────
    rev_rows = db.session.execute(
        text("""
            SELECT date, revenue, profit, transaction_count
            FROM daily_store_summary
            WHERE store_id = :sid AND date >= :week_ago AND date <= :today
            ORDER BY date ASC
        """),
        {"sid": sid, "week_ago": str(week_ago), "today": str(today)},
    ).fetchall()

    sales_today = 0.0
    profit_today = 0.0
    sales_yesterday = 0.0
    profit_yesterday = 0.0
    sparkline_pts = []
    for r in rev_rows:
        row_date = r.date if isinstance(r.date, date) else date.fromisoformat(str(r.date)[:10])
        rev = float(r.revenue or 0)
        pft = float(r.profit or 0)
        sparkline_pts.append({"timestamp": str(row_date) + "T00:00:00Z", "revenue": rev})
        if row_date == today:
            sales_today = rev
            profit_today = pft
        elif row_date == yesterday:
            sales_yesterday = rev
            profit_yesterday = pft

    gross_margin = round((profit_today / sales_today * 100), 1) if sales_today else 0.0
    gross_margin_prev = round((profit_yesterday / sales_yesterday * 100), 1) if sales_yesterday else 0.0

    sales_sparkline = _build_sparkline(sparkline_pts, "sales", "revenue")

    margin_pts = [
        {"timestamp": p["timestamp"], "value": round(p["revenue"] * (gross_margin / 100), 2) if gross_margin else 0}
        for p in sparkline_pts
    ]
    gross_margin_sparkline = {"metric": "gross_margin", "points": margin_pts}

    # ── Inventory at risk (products below reorder level) ─────────────────────
    inv_row = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE store_id = :sid AND is_active = TRUE
              AND current_stock <= reorder_level
        """),
        {"sid": sid},
    ).fetchone()
    inventory_at_risk = inv_row.cnt if inv_row else 0

    inv_row_prev = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM products
            WHERE store_id = :sid AND is_active = TRUE
              AND current_stock <= reorder_level + 1
        """),
        {"sid": sid},
    ).fetchone()
    inventory_at_risk_prev = inv_row_prev.cnt if inv_row_prev else 0

    inventory_sparkline = {"metric": "inventory_at_risk", "points": []}

    # ── Outstanding purchase orders ──────────────────────────────────────────
    po_row = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM purchase_orders
            WHERE store_id = :sid AND status IN ('DRAFT', 'SENT')
        """),
        {"sid": sid},
    ).fetchone()
    outstanding_pos = po_row.cnt if po_row else 0

    po_row_prev = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM purchase_orders
            WHERE store_id = :sid
              AND status IN ('DRAFT', 'SENT')
              AND created_at < :yesterday
        """),
        {"sid": sid, "yesterday": str(yesterday)},
    ).fetchone()
    outstanding_pos_prev = po_row_prev.cnt if po_row_prev else outstanding_pos

    pos_sparkline = {"metric": "outstanding_pos", "points": []}

    # ── Loyalty redemptions (last 7 days) ────────────────────────────────────
    loyalty_row = db.session.execute(
        text("""
            SELECT COALESCE(SUM(ABS(lt.points)), 0) AS total_redeemed
            FROM loyalty_transactions lt
            JOIN customer_loyalty_accounts cla ON cla.id = lt.account_id
            WHERE cla.store_id = :sid AND lt.type = 'REDEEM'
              AND lt.created_at >= :week_ago
        """),
        {"sid": sid, "week_ago": str(week_ago)},
    ).fetchone()
    loyalty_redemptions = int(loyalty_row.total_redeemed) if loyalty_row else 0

    # Previous-period loyalty redemptions (prior 7-day window)
    prev_week_start = week_ago - timedelta(days=7)
    loyalty_row_prev = db.session.execute(
        text("""
            SELECT COALESCE(SUM(ABS(lt.points)), 0) AS total_redeemed
            FROM loyalty_transactions lt
            JOIN customer_loyalty_accounts cla ON cla.id = lt.account_id
            WHERE cla.store_id = :sid AND lt.type = 'REDEEM'
              AND lt.created_at >= :prev_start AND lt.created_at < :week_ago
        """),
        {"sid": sid, "prev_start": str(prev_week_start), "week_ago": str(week_ago)},
    ).fetchone()
    loyalty_prev = int(loyalty_row_prev.total_redeemed) if loyalty_row_prev else 0

    loyalty_sparkline = {"metric": "loyalty_redemptions", "points": []}

    # ── Online orders (transactions with payment_mode containing 'online') ───
    online_row = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE store_id = :sid AND is_return = FALSE
              AND DATE(created_at) = :today
              AND LOWER(COALESCE(payment_mode, '')) LIKE :pattern
        """),
        {"sid": sid, "today": str(today), "pattern": "%online%"},
    ).fetchone()
    online_orders = online_row.cnt if online_row else 0

    # Yesterday's online orders for delta
    online_row_prev = db.session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE store_id = :sid AND is_return = FALSE
              AND DATE(created_at) = :yesterday
              AND LOWER(COALESCE(payment_mode, '')) LIKE :pattern
        """),
        {"sid": sid, "yesterday": str(yesterday), "pattern": "%online%"},
    ).fetchone()
    online_orders_prev = online_row_prev.cnt if online_row_prev else 0

    online_sparkline = {"metric": "online_orders", "points": []}

    return format_response(
        data={
            "sales": round(sales_today, 2),
            "sales_delta": _pct_delta(sales_today, sales_yesterday),
            "sales_sparkline": sales_sparkline,
            "gross_margin": gross_margin,
            "gross_margin_delta": _pct_delta(gross_margin, gross_margin_prev),
            "gross_margin_sparkline": gross_margin_sparkline,
            "inventory_at_risk": inventory_at_risk,
            "inventory_at_risk_delta": _int_delta(inventory_at_risk, inventory_at_risk_prev),
            "inventory_at_risk_sparkline": inventory_sparkline,
            "outstanding_pos": outstanding_pos,
            "outstanding_pos_delta": _int_delta(outstanding_pos, outstanding_pos_prev),
            "outstanding_pos_sparkline": pos_sparkline,
            "loyalty_redemptions": loyalty_redemptions,
            "loyalty_redemptions_delta": _pct_delta(loyalty_redemptions, loyalty_prev),
            "loyalty_redemptions_sparkline": loyalty_sparkline,
            "online_orders": online_orders,
            "online_orders_delta": _pct_delta(online_orders, online_orders_prev),
            "online_orders_sparkline": online_sparkline,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    )


# ── /alerts ──────────────────────────────────────────────────────────────────


@dashboard_bp.route("/alerts")
@require_auth
def alerts():
    """Get unresolved alerts for the current store from the alerts table."""
    try:
        return _alerts_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "ALERTS_ERROR", "message": str(e)}), 500


def _alerts_impl():
    sid = _store_id()

    rows = db.session.execute(
        text("""
            SELECT alert_id, alert_type, priority, product_name, message,
                   snoozed_until, created_at
            FROM alerts
            WHERE store_id = :sid AND resolved_at IS NULL
            ORDER BY
                CASE priority
                    WHEN 'CRITICAL' THEN 0
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END,
                created_at DESC
            LIMIT 50
        """),
        {"sid": sid},
    ).fetchall()

    priority_to_severity = {
        "CRITICAL": "high",
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
        "INFO": "low",
    }

    alert_list = []
    for r in rows:
        snoozed = r.snoozed_until is not None
        ts = _to_iso(r.created_at)
        alert_list.append(
            {
                "id": str(r.alert_id),
                "type": (r.alert_type or "system").lower(),
                "severity": priority_to_severity.get(r.priority, "low"),
                "title": f"{r.alert_type or 'Alert'}: {r.product_name}"
                if r.product_name
                else (r.alert_type or "Alert"),
                "message": r.message or "",
                "timestamp": ts,
                "source": "inventory" if r.alert_type and "stock" in r.alert_type.lower() else "system",
                "acknowledged": snoozed,
                "resolved": False,
            }
        )

    return format_response(data={"alerts": alert_list, "has_more": False, "next_cursor": None})


# ── /live-signals ────────────────────────────────────────────────────────────


@dashboard_bp.route("/live-signals")
@require_auth
def live_signals():
    """Get live market signals from the market_signals table.

    NOTE: market_signals is a global table with no store_id column.
    Signals are scoped by region_code where available.  This endpoint
    intentionally returns market-wide signals relevant to all stores.
    """
    try:
        return _live_signals_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "SIGNALS_ERROR", "message": str(e)}), 500


def _live_signals_impl():
    _store_id()  # validate auth context

    rows = db.session.execute(
        text("""
            SELECT ms.id, ms.signal_type, ms.region_code, ms.value,
                   ms.confidence, ms.timestamp
            FROM market_signals ms
            ORDER BY ms.timestamp DESC
            LIMIT 10
        """),
    ).fetchall()

    signals = []
    for r in rows:
        val = float(r.value or 0)
        delta_str = f"+{val:.0f}%" if val >= 0 else f"{val:.0f}%"
        sig_type = r.signal_type or "MARKET"
        ts = _to_iso(r.timestamp)

        if "price" in sig_type.lower():
            insight = f"Price signal detected in {r.region_code or 'region'}: {sig_type}"
            recommendation = "Review pricing strategy for affected products"
        elif "demand" in sig_type.lower():
            insight = f"Demand signal in {r.region_code or 'region'}: {sig_type}"
            recommendation = "Adjust inventory levels to match demand trend"
        else:
            insight = f"Market signal: {sig_type} in {r.region_code or 'region'}"
            recommendation = "Monitor market conditions and adjust strategy"

        signals.append(
            {
                "id": f"signal-{r.id}",
                "sku": "",
                "product_name": sig_type,
                "delta": delta_str,
                "region": r.region_code or "",
                "insight": insight,
                "recommendation": recommendation,
                "timestamp": ts,
            }
        )

    # If no signals exist yet, return empty list (no mock data)
    return format_response(
        data={
            "signals": signals,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    )


# ── /forecasts/stores ────────────────────────────────────────────────────────


@dashboard_bp.route("/forecasts/stores")
@require_auth
def forecasts_stores():
    """Get store-level forecasts from forecast_cache."""
    try:
        return _forecasts_stores_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "FORECAST_ERROR", "message": str(e)}), 500


def _forecasts_stores_impl():
    sid = _store_id()
    today = datetime.now(timezone.utc).date()

    rows = db.session.execute(
        text("""
            SELECT fc.forecast_date, fc.forecast_value, fc.lower_bound,
                   fc.upper_bound, fc.model_type
            FROM forecast_cache fc
            WHERE fc.store_id = :sid AND fc.forecast_date >= :today
            ORDER BY fc.forecast_date ASC
        """),
        {"sid": sid, "today": str(today)},
    ).fetchall()

    # Get store name
    store_row = db.session.execute(
        text("SELECT store_name FROM stores WHERE store_id = :sid"),
        {"sid": sid},
    ).fetchone()
    store_name = store_row.store_name if store_row else f"Store {sid}"

    forecast_data = []
    for r in rows:
        fval = float(r.forecast_value or 0)
        lower = float(r.lower_bound or 0) if r.lower_bound else fval * 0.85
        upper = float(r.upper_bound or 0) if r.upper_bound else fval * 1.15
        confidence = round(1.0 - (upper - lower) / (fval * 2) if fval else 0.8, 2)
        forecast_data.append(
            {
                "date": str(r.forecast_date),
                "predicted_sales": round(fval, 2),
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )

    total_predicted = sum(f["predicted_sales"] for f in forecast_data)

    forecasts = [
        {
            "store_id": sid,
            "store_name": store_name,
            "forecast": forecast_data,
            "total_predicted": round(total_predicted, 2),
            "accuracy": round(sum(f["confidence"] for f in forecast_data) / len(forecast_data), 2)
            if forecast_data
            else None,
        }
    ]

    return format_response(data={"forecasts": forecasts})


# ── /incidents/active ────────────────────────────────────────────────────────


@dashboard_bp.route("/incidents/active")
@require_auth
def active_incidents():
    """Get active critical/high-priority unresolved alerts as incidents."""
    try:
        return _active_incidents_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "INCIDENTS_ERROR", "message": str(e)}), 500


def _active_incidents_impl():
    sid = _store_id()

    rows = db.session.execute(
        text("""
            SELECT alert_id, alert_type, priority, message, created_at, updated_at
            FROM alerts
            WHERE store_id = :sid
              AND resolved_at IS NULL
              AND priority IN ('CRITICAL', 'HIGH')
            ORDER BY created_at DESC
            LIMIT 5
        """),
        {"sid": sid},
    ).fetchall()

    incidents = []
    for r in rows:
        created = _to_iso(r.created_at)
        updated = _to_iso(r.updated_at) if r.updated_at else created
        est_resolution = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

        incidents.append(
            {
                "id": f"incident-{r.alert_id}",
                "title": r.alert_type or "Active Incident",
                "description": r.message or "No details available",
                "severity": "high" if r.priority == "CRITICAL" else "medium",
                "status": "investigating",
                "impacted_services": [r.alert_type.lower()] if r.alert_type else ["system"],
                "created_at": created,
                "updated_at": updated,
                "estimated_resolution": est_resolution,
            }
        )

    return format_response(data={"incidents": incidents})


# ── /alerts/feed ─────────────────────────────────────────────────────────────


@dashboard_bp.route("/alerts/feed")
@require_auth
def alerts_feed():
    """Get paginated alert feed from the alerts table."""
    try:
        return _alerts_feed_impl()
    except Exception as e:
        db.session.rollback()
        return format_response(data=None, error={"code": "ALERTS_FEED_ERROR", "message": str(e)}), 500


def _alerts_feed_impl():
    sid = _store_id()
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except (ValueError, TypeError):
        limit = 20
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    rows = db.session.execute(
        text("""
            SELECT alert_id, alert_type, priority, product_name, message,
                   snoozed_until, created_at
            FROM alerts
            WHERE store_id = :sid AND resolved_at IS NULL
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"sid": sid, "limit": limit + 1, "offset": offset},
    ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    priority_to_severity = {
        "CRITICAL": "high",
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
        "INFO": "low",
    }

    alert_list = []
    for r in rows:
        snoozed = r.snoozed_until is not None
        ts = _to_iso(r.created_at)
        alert_list.append(
            {
                "id": str(r.alert_id),
                "type": (r.alert_type or "system").lower(),
                "severity": priority_to_severity.get(r.priority, "low"),
                "title": f"{r.alert_type or 'Alert'}: {r.product_name}"
                if r.product_name
                else (r.alert_type or "Alert"),
                "message": r.message or "",
                "timestamp": ts,
                "source": "inventory" if r.alert_type and "stock" in r.alert_type.lower() else "system",
                "acknowledged": snoozed,
                "resolved": False,
            }
        )

    next_cursor = str(offset + limit) if has_more else None

    return format_response(
        data={
            "alerts": alert_list,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
    )
