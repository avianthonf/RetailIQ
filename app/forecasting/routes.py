"""
RetailIQ Forecasting Routes
============================
Serves pre-computed forecasts from forecast_cache.
All heavy computation happens in Celery tasks (run_batch_forecasting).

Blueprint registered at /api/v1/forecasting (see app/__init__.py).
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import text

from app import db
from app.auth.decorators import require_auth, require_role
from app.auth.utils import format_response

forecasting_bp = Blueprint('forecasting', __name__)


def _store_id() -> int:
    return g.current_user['store_id']


def _rows_to_points(rows) -> list[dict]:
    if not rows:
        return []
    m_type = getattr(rows[0], 'model_type', 'flat')
    is_prophet = (m_type == 'prophet')

    return [
        {
            'date':          str(r.forecast_date),
            'predicted':     float(r.forecast_value or 0),
            'lower_bound':   float(r.lower_bound or 0) if is_prophet else None,
            'upper_bound':   float(r.upper_bound or 0) if is_prophet else None,
        }
        for r in rows
    ]


# ── Store-level forecast ──────────────────────────────────────────────────────

@forecasting_bp.route('/store')
@require_auth
@require_role('owner')
def forecast_store_endpoint():
    """
    Serve aggregated store-level forecast from forecast_cache
    (rows where product_id IS NULL).
    """
    sid     = _store_id()
    horizon = min(int(request.args.get('horizon', 7)), 90)
    today   = date.today()
    end     = today + timedelta(days=horizon)

    rows = db.session.execute(text("""
        SELECT forecast_date, forecast_value, lower_bound, upper_bound,
               regime, model_type, training_window_days, generated_at
        FROM forecast_cache
        WHERE store_id = :sid
          AND product_id IS NULL
          AND forecast_date > :today
          AND forecast_date <= :end
        ORDER BY forecast_date ASC
        LIMIT :horizon
    """), {'sid': sid, 'today': str(today), 'end': str(end), 'horizon': horizon}).fetchall()

    if not rows:
        return jsonify(format_response(
            False,
            error={'code': 'NOT_FOUND', 'message': 'No store forecast available. Run the batch forecasting task first.'},
            meta=None,
        )), 404

    points = _rows_to_points(rows)
    m_type = getattr(rows[0], 'model_type', 'flat')
    confidence_tier = m_type

    # Historical data
    window = getattr(rows[0], 'training_window_days', 30)
    if not isinstance(window, int) or window <= 0:
        window = 30

    hist_start = today - timedelta(days=window)
    hist_rows = db.session.execute(text("""
        SELECT date, units_sold
        FROM daily_store_summary
        WHERE store_id = :sid AND date > :hist_start AND date <= :today
        ORDER BY date ASC
    """), {'sid': sid, 'hist_start': str(hist_start), 'today': str(today)}).fetchall()

    historical = [{'date': str(r.date), 'actual': float(r.units_sold or 0)} for r in hist_rows]

    meta = {
        'regime':               rows[0].regime,
        'model_type':           m_type,
        'confidence_tier':      confidence_tier,
        'training_window_days': window,
        'generated_at':         str(rows[0].generated_at),
    }
    return jsonify(format_response(data={'historical': historical, 'forecast': points}, meta=meta))


# ── SKU-level forecast ────────────────────────────────────────────────────────

@forecasting_bp.route('/sku/<int:product_id>')
@require_auth
@require_role('owner')
def forecast_sku_endpoint(product_id: int):
    """
    Serve SKU-level forecast from forecast_cache.
    Only top-20% revenue SKUs are forecasted (Pareto filter applied in batch).
    Returns reorder_suggestion based on forecast_mean vs current_stock.
    """
    sid     = _store_id()
    horizon = min(int(request.args.get('horizon', 7)), 90)
    today   = date.today()
    end     = today + timedelta(days=horizon)

    # Verify product belongs to store
    product_row = db.session.execute(text("""
        SELECT product_id, name, current_stock, reorder_level, lead_time_days
        FROM products
        WHERE product_id = :pid AND store_id = :sid AND is_active = TRUE
    """), {'pid': product_id, 'sid': sid}).fetchone()

    if not product_row:
        return jsonify(format_response(
            False,
            error={'code': 'NOT_FOUND', 'message': 'Product not found'},
            meta=None,
        )), 404

    rows = db.session.execute(text("""
        SELECT forecast_date, forecast_value, lower_bound, upper_bound,
               regime, model_type, training_window_days, generated_at
        FROM forecast_cache
        WHERE store_id = :sid
          AND product_id = :pid
          AND forecast_date > :today
          AND forecast_date <= :end
        ORDER BY forecast_date ASC
        LIMIT :horizon
    """), {'sid': sid, 'pid': product_id, 'today': str(today), 'end': str(end), 'horizon': horizon}).fetchall()

    if not rows:
        return jsonify(format_response(
            False,
            error={
                'code': 'NOT_FOUND',
                'message': 'No forecast found for this SKU. It may not be in the top-20% revenue tier, '
                           'or the batch forecast has not run yet.',
            },
            meta=None,
        )), 404

    points = _rows_to_points(rows)
    m_type = getattr(rows[0], 'model_type', 'flat')
    confidence_tier = m_type

    # Historical data
    window = getattr(rows[0], 'training_window_days', 30)
    if not isinstance(window, int) or window <= 0:
        window = 30

    hist_start = today - timedelta(days=window)
    hist_rows = db.session.execute(text("""
        SELECT date, units_sold
        FROM daily_sku_summary
        WHERE store_id = :sid AND product_id = :pid AND date > :hist_start AND date <= :today
        ORDER BY date ASC
    """), {'sid': sid, 'pid': product_id, 'hist_start': str(hist_start), 'today': str(today)}).fetchall()

    historical = [{'date': str(r.date), 'actual': float(r.units_sold or 0)} for r in hist_rows]

    # Reorder suggestion
    total_forecast_demand = sum(p['predicted'] for p in points)
    current_stock = float(product_row.current_stock or 0)
    reorder_level = float(product_row.reorder_level or 0)
    lead_time     = int(product_row.lead_time_days or 3)

    # Expected demand during lead time
    per_day_demand = total_forecast_demand / horizon if horizon else 0
    lead_time_demand = per_day_demand * lead_time
    reorder_suggestion = {
        'should_reorder':     current_stock <= (reorder_level + lead_time_demand),
        'current_stock':      current_stock,
        'forecasted_demand':  round(total_forecast_demand, 2),
        'lead_time_days':     lead_time,
        'lead_time_demand':   round(lead_time_demand, 2),
        'suggested_order_qty': round(max(0.0, lead_time_demand + reorder_level - current_stock), 2),
    }

    meta = {
        'product_id':           product_id,
        'product_name':         product_row.name,
        'regime':               rows[0].regime,
        'model_type':           m_type,
        'confidence_tier':      confidence_tier,
        'training_window_days': window,
        'generated_at':         str(rows[0].generated_at),
        'reorder_suggestion':   reorder_suggestion,
    }
    return jsonify(format_response(data={'historical': historical, 'forecast': points}, meta=meta))
