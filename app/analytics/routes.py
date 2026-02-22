"""
RetailIQ Analytics Routes
==========================
All endpoints read ONLY from aggregation tables (daily_store_summary,
daily_category_summary, daily_sku_summary) or transactions/customers for
payment/customer summaries. Redis-cached for 60 seconds per store + path.

Blueprint is registered at /api/v1/analytics  (see app/__init__.py).
Dashboard is registered separately at /api/v1/dashboard.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from collections import defaultdict

from flask import jsonify, request, g, current_app, Blueprint
from sqlalchemy import text

from app import db
from app.auth.decorators import require_auth, require_role
from app.auth.utils import format_response
from .helpers import (
    cache_response, parse_date, aggregate_by_period,
    compute_7d_moving_avg, bucket_date,
)

analytics_bp = Blueprint('analytics', __name__)

# ── Shared query range ────────────────────────────────────────────────────────

def _date_range():
    """Parse start/end from query-string; default last 30 days."""
    today = date.today()
    end   = parse_date(request.args.get('end'),   today)
    start = parse_date(request.args.get('start'), today - timedelta(days=30))
    return str(start), str(end)


def _store_id() -> int:
    return g.current_user['store_id']


# ── 1. Revenue ────────────────────────────────────────────────────────────────

@analytics_bp.route('/revenue')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def revenue():
    start, end = _date_range()
    group_by = request.args.get('group_by', 'day')
    sid = _store_id()

    rows = db.session.execute(text("""
        SELECT date, revenue, profit, transaction_count
        FROM daily_store_summary
        WHERE store_id = :sid AND date >= :start AND date <= :end
        ORDER BY date ASC
    """), {'sid': sid, 'start': start, 'end': end}).fetchall()

    daily = [
        {'date': str(r.date), 'revenue': float(r.revenue or 0),
         'profit': float(r.profit or 0), 'transactions': r.transaction_count or 0}
        for r in rows
    ]

    if group_by in ('week', 'month'):
        daily = aggregate_by_period(daily, group_by, ['revenue', 'profit', 'transactions'])

    daily = compute_7d_moving_avg(daily, value_key='revenue')
    return jsonify(format_response(data=daily))


# ── 2. Profit ─────────────────────────────────────────────────────────────────

@analytics_bp.route('/profit')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def profit():
    start, end = _date_range()
    group_by = request.args.get('group_by', 'day')
    sid = _store_id()

    rows = db.session.execute(text("""
        SELECT date, revenue, profit
        FROM daily_store_summary
        WHERE store_id = :sid AND date >= :start AND date <= :end
        ORDER BY date ASC
    """), {'sid': sid, 'start': start, 'end': end}).fetchall()

    daily = []
    for r in rows:
        rev = float(r.revenue or 0)
        pft = float(r.profit or 0)
        margin_pct = round((pft / rev * 100), 4) if rev else 0.0
        daily.append({'date': str(r.date), 'profit': pft, 'revenue': rev, 'margin_pct': margin_pct})

    if group_by in ('week', 'month'):
        daily = aggregate_by_period(daily, group_by, ['profit', 'revenue'])
        for row in daily:
            row['margin_pct'] = round((row['profit'] / row['revenue'] * 100) if row['revenue'] else 0, 4)

    daily = compute_7d_moving_avg(daily, value_key='profit')
    return jsonify(format_response(data=daily))


# ── 3. Top Products ───────────────────────────────────────────────────────────

@analytics_bp.route('/top-products')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def top_products():
    start, end = _date_range()
    metric = request.args.get('metric', 'revenue')
    limit  = min(int(request.args.get('limit', 10)), 100)
    sid = _store_id()

    valid_metrics = {'revenue', 'quantity', 'profit'}
    if metric not in valid_metrics:
        return jsonify(format_response(False, error={'code': 'INVALID_PARAM', 'message': 'metric must be revenue|quantity|profit'}, meta=None)), 400

    col_map = {'revenue': 'revenue', 'quantity': 'units_sold', 'profit': 'profit'}
    col = col_map[metric]

    rows = db.session.execute(text(f"""
        SELECT dss.product_id, p.name,
               SUM(dss.revenue)    AS total_revenue,
               SUM(dss.units_sold) AS total_quantity,
               SUM(dss.profit)     AS total_profit
        FROM daily_sku_summary dss
        JOIN products p ON p.product_id = dss.product_id
        WHERE dss.store_id = :sid AND dss.date >= :start AND dss.date <= :end
        GROUP BY dss.product_id, p.name
        ORDER BY SUM(dss.{col}) DESC
        LIMIT :limit
    """), {'sid': sid, 'start': start, 'end': end, 'limit': limit}).fetchall()

    data = [
        {
            'rank': i + 1,
            'product_id': r.product_id,
            'name': r.name,
            'revenue': float(r.total_revenue or 0),
            'quantity': float(r.total_quantity or 0),
            'profit': float(r.total_profit or 0),
        }
        for i, r in enumerate(rows)
    ]
    return jsonify(format_response(data=data))


# ── 4. Category Breakdown ─────────────────────────────────────────────────────

@analytics_bp.route('/category-breakdown')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def category_breakdown():
    start, end = _date_range()
    sid = _store_id()

    rows = db.session.execute(text("""
        SELECT dcs.category_id, c.name,
               SUM(dcs.revenue)    AS total_revenue,
               SUM(dcs.profit)     AS total_profit,
               SUM(dcs.units_sold) AS total_units
        FROM daily_category_summary dcs
        LEFT JOIN categories c ON c.category_id = dcs.category_id
        WHERE dcs.store_id = :sid AND dcs.date >= :start AND dcs.date <= :end
        GROUP BY dcs.category_id, c.name
        ORDER BY total_revenue DESC
    """), {'sid': sid, 'start': start, 'end': end}).fetchall()

    total_revenue = sum(float(r.total_revenue or 0) for r in rows)
    data = [
        {
            'category_id': r.category_id,
            'name': r.name or 'Uncategorised',
            'revenue': float(r.total_revenue or 0),
            'profit': float(r.total_profit or 0),
            'units': float(r.total_units or 0),
            'share_pct': round(float(r.total_revenue or 0) / total_revenue * 100, 2) if total_revenue else 0.0,
        }
        for r in rows
    ]
    return jsonify(format_response(data=data))


# ── 5. SKU Contribution  ──────────────────────────────────────────────────────

@analytics_bp.route('/contribution')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def contribution():
    """
    Price-Volume-Contribution analysis for each SKU.

    compare_start / compare_end  → prior period (defaults to equivalent length
    before the main window if not supplied).

    For each SKU:
      Contribution_i = (Rev_i(t) - Rev_i(t-1)) / TotalRevChange
    Pareto flag: top 20% of SKUs by current-period revenue.
    Price-volume decomp (midpoint):
      ΔP_i = avg_price_t - avg_price_{t-1}
      ΔV_i = units_t - units_{t-1}
      P̄   = (avg_price_t + avg_price_{t-1}) / 2
      V̄   = (units_t + units_{t-1}) / 2
      price_effect  = ΔP_i * V̄
      volume_effect = ΔV_i * P̄
    """
    start, end = _date_range()
    sid = _store_id()

    # compare window
    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)
    delta   = (end_d - start_d).days + 1
    cmp_end_d   = start_d - timedelta(days=1)
    cmp_start_d = cmp_end_d - timedelta(days=delta - 1)
    cmp_start = request.args.get('compare_start', str(cmp_start_d))
    cmp_end   = request.args.get('compare_end',   str(cmp_end_d))

    def _sku_totals(s, e):
        rows = db.session.execute(text("""
            SELECT dss.product_id, p.name,
                   SUM(dss.revenue)            AS rev,
                   SUM(dss.units_sold)         AS units,
                   SUM(dss.profit)             AS profit,
                   AVG(dss.avg_selling_price)  AS avg_price
            FROM daily_sku_summary dss
            JOIN products p ON p.product_id = dss.product_id
            WHERE dss.store_id = :sid AND dss.date >= :start AND dss.date <= :end
            GROUP BY dss.product_id, p.name
        """), {'sid': sid, 'start': s, 'end': e}).fetchall()
        return {r.product_id: r for r in rows}

    current = _sku_totals(start, end)
    prior   = _sku_totals(cmp_start, cmp_end)

    all_pids = set(current) | set(prior)
    total_rev_current = sum(float(current[p].rev or 0) for p in current)
    total_rev_prior   = sum(float(prior[p].rev or 0)   for p in prior)
    total_rev_change  = total_rev_current - total_rev_prior

    # Pareto: top 20% by current-period revenue
    sorted_by_rev = sorted(current.keys(), key=lambda p: float(current[p].rev or 0), reverse=True)
    top20_count = max(1, round(len(sorted_by_rev) * 0.20))
    pareto_pids = set(sorted_by_rev[:top20_count])

    result = []
    for pid in sorted_by_rev + [p for p in prior if p not in current]:
        cur = current.get(pid)
        pri = prior.get(pid)
        rev_t   = float(cur.rev or 0)   if cur else 0.0
        rev_t1  = float(pri.rev or 0)   if pri else 0.0
        units_t = float(cur.units or 0) if cur else 0.0
        units_t1= float(pri.units or 0) if pri else 0.0
        p_t     = float(cur.avg_price or 0) if cur else 0.0
        p_t1    = float(pri.avg_price or 0) if pri else 0.0

        delta_rev = rev_t - rev_t1
        # Contribution — safe division
        if abs(total_rev_change) > 0.01:
            contrib = delta_rev / total_rev_change
        else:
            contrib = 0.0  # stable fallback

        # Midpoint price-volume decomp
        p_bar = (p_t + p_t1) / 2
        v_bar = (units_t + units_t1) / 2
        price_effect  = (p_t - p_t1) * v_bar
        volume_effect = (units_t - units_t1) * p_bar

        result.append({
            'product_id': pid,
            'name': (cur or pri).name if (cur or pri) else str(pid),
            'revenue_current': round(rev_t,  2),
            'revenue_prior':   round(rev_t1, 2),
            'delta_revenue':   round(delta_rev, 2),
            'contribution':    round(contrib, 4),
            'is_pareto':       pid in pareto_pids,
            'price_effect':    round(price_effect, 2),
            'volume_effect':   round(volume_effect, 2),
            'profit_current':  round(float(cur.profit or 0) if cur else 0, 2),
        })

    summary = {
        'total_rev_current': round(total_rev_current, 2),
        'total_rev_prior':   round(total_rev_prior, 2),
        'total_rev_change':  round(total_rev_change, 2),
        'period':   {'start': start, 'end': end},
        'compare':  {'start': cmp_start, 'end': cmp_end},
    }
    return jsonify(format_response(data={'skus': result, 'summary': summary}))


# ── 6. Payment Modes ──────────────────────────────────────────────────────────

@analytics_bp.route('/payment-modes')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def payment_modes():
    start, end = _date_range()
    sid = _store_id()

    rows = db.session.execute(text("""
        SELECT payment_mode,
               COUNT(*)        AS txn_count,
               SUM(
                 (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                  FROM transaction_items ti
                  WHERE ti.transaction_id = t.transaction_id)
               ) AS revenue
        FROM transactions t
        WHERE t.store_id = :sid
          AND DATE(t.created_at) >= :start
          AND DATE(t.created_at) <= :end
          AND t.is_return = FALSE
        GROUP BY t.payment_mode
        ORDER BY revenue DESC
    """), {'sid': sid, 'start': start, 'end': end}).fetchall()

    total_txns = sum(r.txn_count for r in rows)
    total_rev  = sum(float(r.revenue or 0) for r in rows)
    data = [
        {
            'mode': r.payment_mode or 'UNKNOWN',
            'txn_count': r.txn_count,
            'revenue': round(float(r.revenue or 0), 2),
            'txn_share_pct': round(r.txn_count / total_txns * 100, 2) if total_txns else 0.0,
            'rev_share_pct': round(float(r.revenue or 0) / total_rev * 100, 2) if total_rev else 0.0,
        }
        for r in rows
    ]
    return jsonify(format_response(data=data))


# ── 7. Customer Summary ───────────────────────────────────────────────────────

@analytics_bp.route('/customers/summary')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def customers_summary():
    start, end = _date_range()
    sid = _store_id()

    row = db.session.execute(text("""
        SELECT
            COUNT(DISTINCT t.customer_id) FILTER (WHERE t.customer_id IS NOT NULL) AS identified_customers,
            COUNT(DISTINCT t.transaction_id) AS total_txns,
            COUNT(DISTINCT t.transaction_id) FILTER (WHERE t.customer_id IS NOT NULL) AS identified_txns,
            COALESCE(SUM(
                (SELECT COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                 FROM transaction_items ti WHERE ti.transaction_id = t.transaction_id)
            ), 0) AS total_revenue
        FROM transactions t
        WHERE t.store_id = :sid
          AND DATE(t.created_at) >= :start
          AND DATE(t.created_at) <= :end
          AND t.is_return = FALSE
    """), {'sid': sid, 'start': start, 'end': end}).fetchone()

    # New vs returning (first txn in prior period)
    new_customers_row = db.session.execute(text("""
        SELECT COUNT(DISTINCT t.customer_id) AS new_count
        FROM transactions t
        WHERE t.store_id = :sid
          AND t.customer_id IS NOT NULL
          AND DATE(t.created_at) >= :start
          AND DATE(t.created_at) <= :end
          AND t.is_return = FALSE
          AND NOT EXISTS (
              SELECT 1 FROM transactions t2
              WHERE t2.customer_id = t.customer_id
                AND t2.store_id = :sid
                AND DATE(t2.created_at) < :start
          )
    """), {'sid': sid, 'start': start, 'end': end}).fetchone()

    ident  = row.identified_customers or 0
    total  = row.total_txns or 0
    new_c  = new_customers_row.new_count or 0
    data = {
        'identified_customers':     ident,
        'new_customers':            new_c,
        'returning_customers':      max(0, ident - new_c),
        'total_transactions':       total,
        'identified_transactions':  row.identified_txns or 0,
        'anonymous_transactions':   total - (row.identified_txns or 0),
        'total_revenue':            round(float(row.total_revenue or 0), 2),
        'avg_revenue_per_customer': round(float(row.total_revenue or 0) / ident, 2) if ident else 0.0,
    }
    return jsonify(format_response(data=data))


# ── 8. Diagnostics ────────────────────────────────────────────────────────────

@analytics_bp.route('/diagnostics')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def diagnostics():
    """
    - Trend deviation per day: revenue vs 7-day MA; flag if >20% deviation.
    - Rolling variance per top SKU (14-day and 30-day windows).
    - Margin drift: flag if gross margin dropped >3 pp vs prior month.
    """
    start, end = _date_range()
    sid = _store_id()

    # ── a. Revenue trend deviation ───────────────────────────────────────────
    # Fetch an extra 6 days before start for MA initialisation
    start_d = date.fromisoformat(start)
    ma_start = str(start_d - timedelta(days=6))

    store_rows = db.session.execute(text("""
        SELECT date, revenue, profit
        FROM daily_store_summary
        WHERE store_id = :sid AND date >= :ma_start AND date <= :end
        ORDER BY date ASC
    """), {'sid': sid, 'ma_start': ma_start, 'end': end}).fetchall()

    daily_rev = [{'date': str(r.date), 'revenue': float(r.revenue or 0), 'profit': float(r.profit or 0)} for r in store_rows]
    daily_rev = compute_7d_moving_avg(daily_rev, value_key='revenue')

    trend_deviations = []
    for row in daily_rev:
        if row['date'] < start:
            continue  # skip warm-up rows
        ma = row.get('moving_avg_7d', 0)
        rev = row['revenue']
        if ma > 0:
            dev_pct = (rev - ma) / ma
            trend_deviations.append({
                'date': row['date'],
                'revenue': rev,
                'moving_avg_7d': ma,
                'deviation_pct': round(dev_pct * 100, 2),
                'flagged': abs(dev_pct) > 0.20,
            })

    # ── b. Top SKU rolling variance ──────────────────────────────────────────
    top_sku_rows = db.session.execute(text("""
        SELECT product_id
        FROM daily_sku_summary
        WHERE store_id = :sid AND date >= :start AND date <= :end
        GROUP BY product_id
        ORDER BY SUM(revenue) DESC
        LIMIT 10
    """), {'sid': sid, 'start': start, 'end': end}).fetchall()
    top_pids = [r.product_id for r in top_sku_rows]

    sku_variance = []
    for pid in top_pids:
        # 30-day history ending at `end`
        end_d = date.fromisoformat(end)
        hist_start = str(end_d - timedelta(days=29))
        sales_rows = db.session.execute(text("""
            SELECT date, units_sold
            FROM daily_sku_summary
            WHERE store_id = :sid AND product_id = :pid
              AND date >= :hist_start AND date <= :end
            ORDER BY date ASC
        """), {'sid': sid, 'pid': pid, 'hist_start': hist_start, 'end': end}).fetchall()

        vals = [float(r.units_sold or 0) for r in sales_rows]
        if not vals:
            continue

        def _cv(window):
            if len(window) < 2:
                return None
            import statistics
            mean = statistics.mean(window)
            if mean == 0:
                return None
            return round(statistics.stdev(window) / mean, 4)

        sku_variance.append({
            'product_id': pid,
            'cv_14d': _cv(vals[-14:]),
            'cv_30d': _cv(vals[-30:]),
        })

    # ── c. Margin drift ──────────────────────────────────────────────────────
    end_d     = date.fromisoformat(end)
    month_start = end_d.replace(day=1)
    prev_month_end   = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    def _avg_margin(s, e):
        r = db.session.execute(text("""
            SELECT SUM(revenue) AS rev, SUM(profit) AS pft
            FROM daily_store_summary
            WHERE store_id = :sid AND date >= :s AND date <= :e
        """), {'sid': sid, 's': str(s), 'e': str(e)}).fetchone()
        if r and r.rev:
            return float(r.pft or 0) / float(r.rev) * 100
        return None

    curr_margin = _avg_margin(month_start, end_d)
    prev_margin = _avg_margin(prev_month_start, prev_month_end)

    margin_drift = None
    if curr_margin is not None and prev_margin is not None:
        drift = curr_margin - prev_margin
        margin_drift = {
            'current_month_margin_pct': round(curr_margin, 2),
            'prior_month_margin_pct':   round(prev_margin, 2),
            'drift_pp':                 round(drift, 2),
            'flagged':                  drift < -3.0,
        }

    return jsonify(format_response(data={
        'trend_deviations': trend_deviations,
        'sku_rolling_variance': sku_variance,
        'margin_drift': margin_drift,
    }))


# ── 9. Dashboard ─────────────────────────────────────────────────────────────

@analytics_bp.route('/dashboard')
@require_auth
@require_role('owner')
@cache_response(ttl=60)
def dashboard():
    """
    Single endpoint. Max 5 DB queries. Reads ONLY aggregation tables.
    Returns: today_kpis, revenue_7d, moving_avg_7d, alerts_summary,
             top_products_today, insights (NLP stub).
    """
    sid = _store_id()
    today = date.today()
    week_ago = today - timedelta(days=6)

    # ── Q1: today KPIs + 7-day revenue (single query) ────────────────────────
    kpi_rows = db.session.execute(text("""
        SELECT date, revenue, profit, transaction_count, avg_basket, units_sold
        FROM daily_store_summary
        WHERE store_id = :sid AND date >= :week_ago AND date <= :today
        ORDER BY date ASC
    """), {'sid': sid, 'week_ago': str(week_ago), 'today': str(today)}).fetchall()

    revenue_7d   = []
    today_kpis   = {}
    for r in kpi_rows:
        row_date = r.date if isinstance(r.date, date) else date.fromisoformat(str(r.date)[:10])
        entry = {
            'date': str(row_date),
            'revenue': float(r.revenue or 0),
            'profit': float(r.profit or 0),
            'transactions': r.transaction_count or 0,
            'avg_basket': float(r.avg_basket or 0),
            'units_sold': float(r.units_sold or 0),
        }
        revenue_7d.append(entry)
        if row_date == today:
            today_kpis = {**entry}

    revenue_7d = compute_7d_moving_avg(revenue_7d, value_key='revenue')
    moving_avg_7d = [{'date': r['date'], 'moving_avg': r.get('moving_avg_7d', 0)} for r in revenue_7d]

    if not today_kpis:
        today_kpis = {
            'date': str(today), 'revenue': 0.0, 'profit': 0.0,
            'transactions': 0, 'avg_basket': 0.0, 'units_sold': 0.0,
        }

    # ── Q2: Alerts summary ────────────────────────────────────────────────────
    alert_rows = db.session.execute(text("""
        SELECT priority, COUNT(*) AS cnt
        FROM alerts
        WHERE store_id = :sid AND resolved_at IS NULL
        GROUP BY priority
    """), {'sid': sid}).fetchall()

    alerts_summary = {r.priority: r.cnt for r in alert_rows}
    alerts_summary['total'] = sum(alerts_summary.values())

    # ── Q3: Top products today ────────────────────────────────────────────────
    top_rows = db.session.execute(text("""
        SELECT dss.product_id, p.name, dss.revenue, dss.units_sold
        FROM daily_sku_summary dss
        JOIN products p ON p.product_id = dss.product_id
        WHERE dss.store_id = :sid AND dss.date = :today
        ORDER BY dss.revenue DESC
        LIMIT 5
    """), {'sid': sid, 'today': str(today)}).fetchall()

    top_products_today = [
        {'product_id': r.product_id, 'name': r.name,
         'revenue': float(r.revenue or 0), 'units_sold': float(r.units_sold or 0)}
        for r in top_rows
    ]

    # ── NLP stub insights (no DB query) ──────────────────────────────────────
    insights = _generate_insight_stubs(today_kpis, revenue_7d, alerts_summary)

    return jsonify(format_response(data={
        'today_kpis':        today_kpis,
        'revenue_7d':        revenue_7d,
        'moving_avg_7d':     moving_avg_7d,
        'alerts_summary':    alerts_summary,
        'top_products_today': top_products_today,
        'insights':          insights,
    }))


def _generate_insight_stubs(kpis: dict, rev7d: list, alerts: dict) -> list[dict]:
    """
    Return 2-3 NLP-style insight cards computed purely from memory
    (no extra DB queries). Full NLP engine to be wired in nlp/ module.
    """
    cards = []
    rev_today = kpis.get('revenue', 0)
    ma = rev7d[-1].get('moving_avg_7d', 0) if rev7d else 0

    if ma and rev_today > 1.1 * ma:
        cards.append({
            'type': 'positive',
            'title': 'Revenue above trend',
            'body': f"Today's revenue ({rev_today:.0f}) is {((rev_today/ma-1)*100):.1f}% above the 7-day average.",
        })
    elif ma and rev_today < 0.8 * ma:
        cards.append({
            'type': 'warning',
            'title': 'Revenue below trend',
            'body': f"Today's revenue ({rev_today:.0f}) is {((1-rev_today/ma)*100):.1f}% below the 7-day average.",
        })

    critical = alerts.get('CRITICAL', 0)
    if critical:
        cards.append({
            'type': 'alert',
            'title': f'{critical} critical alert{"s" if critical > 1 else ""}',
            'body': 'Action required: review your open alerts dashboard.',
        })

    if not cards:
        cards.append({
            'type': 'info',
            'title': 'Store on track',
            'body': 'No significant anomalies detected today. Keep it up!',
        })

    return cards[:3]
