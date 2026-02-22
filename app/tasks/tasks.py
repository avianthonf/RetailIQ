"""
RetailIQ Celery Tasks
=====================
All tasks use DB/Redis for guarantees, are idempotent, retry-able.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone, date as date_type

import redis as redis_lib
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import text

from .db_session import task_session

logger = get_task_logger(__name__)

def _redis_client():
    url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    return redis_lib.Redis.from_url(url, decode_responses=True)

class _RedisLock:
    def __init__(self, key: str, ttl: int = 900):
        self._key = key
        self._ttl = ttl
        self._r   = _redis_client()
        self.acquired = False

    def __enter__(self):
        self.acquired = bool(self._r.set(self._key, '1', nx=True, ex=self._ttl))
        return self.acquired

    def __exit__(self, *_):
        if self.acquired:
            self._r.delete(self._key)

def _log(task_name: str, **fields):
    payload = {"task": task_name, "ts": datetime.now(timezone.utc).isoformat(), **fields}
    logger.info(json.dumps(payload))

def _send_push_stub(store_id: int, alert_type: str, priority: str, message: str):
    if priority in ('CRITICAL', 'HIGH'):
        payload = {
            "fcm_target": f"store:{store_id}",
            "notification": {"title": alert_type, "body": message},
            "data": {"store_id": store_id, "alert_type": alert_type, "priority": priority},
        }
        _log("fcm_stub", payload=payload)

# ──────────────────────────────────────────────────────────────────────────────
# 1. rebuild_daily_aggregates
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name='tasks.rebuild_daily_aggregates',
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def rebuild_daily_aggregates(self, store_id: int, date_str: str):
    lock_key = f"lock:rebuild_agg:{store_id}:{date_str}"
    with _RedisLock(lock_key, ttl=600) as acquired:
        if not acquired:
            _log('rebuild_daily_aggregates', store_id=store_id, date=date_str, status='skipped_lock_held')
            return

        _log('rebuild_daily_aggregates', store_id=store_id, date=date_str, status='start')

        with task_session(isolation_level='REPEATABLE READ') as session:
            # daily_store_summary
            session.execute(text("""
                INSERT INTO daily_store_summary (date, store_id, revenue, profit,
                                                  transaction_count, avg_basket, units_sold)
                SELECT
                    :target_date,
                    t.store_id,
                    COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0),
                    COALESCE(SUM(ti.quantity * (ti.selling_price - ti.cost_price_at_time) - ti.discount_amount), 0),
                    COUNT(DISTINCT t.transaction_id),
                    CASE WHEN COUNT(DISTINCT t.transaction_id) > 0
                         THEN COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0)
                              / COUNT(DISTINCT t.transaction_id)
                         ELSE 0 END,
                    COALESCE(SUM(ti.quantity), 0)
                FROM transactions t
                JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
                WHERE t.store_id = :store_id
                  AND DATE(t.created_at) = :target_date
                  AND t.is_return = FALSE
                GROUP BY t.store_id
                ON CONFLICT (date, store_id) DO UPDATE SET
                    revenue            = EXCLUDED.revenue,
                    profit             = EXCLUDED.profit,
                    transaction_count  = EXCLUDED.transaction_count,
                    avg_basket         = EXCLUDED.avg_basket,
                    units_sold         = EXCLUDED.units_sold
            """), {"target_date": date_str, "store_id": store_id})

            # daily_category_summary
            session.execute(text("""
                INSERT INTO daily_category_summary (date, store_id, category_id,
                                                    revenue, profit, units_sold)
                SELECT
                    :target_date,
                    t.store_id,
                    p.category_id,
                    COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0),
                    COALESCE(SUM(ti.quantity * (ti.selling_price - ti.cost_price_at_time) - ti.discount_amount), 0),
                    COALESCE(SUM(ti.quantity), 0)
                FROM transactions t
                JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
                JOIN products p ON ti.product_id = p.product_id
                WHERE t.store_id = :store_id
                  AND DATE(t.created_at) = :target_date
                  AND p.category_id IS NOT NULL
                  AND t.is_return = FALSE
                GROUP BY t.store_id, p.category_id
                ON CONFLICT (date, store_id, category_id) DO UPDATE SET
                    revenue    = EXCLUDED.revenue,
                    profit     = EXCLUDED.profit,
                    units_sold = EXCLUDED.units_sold
            """), {"target_date": date_str, "store_id": store_id})

            # daily_sku_summary
            session.execute(text("""
                INSERT INTO daily_sku_summary (date, store_id, product_id,
                                               revenue, profit, units_sold, avg_selling_price)
                SELECT
                    :target_date,
                    t.store_id,
                    ti.product_id,
                    COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0),
                    COALESCE(SUM(ti.quantity * (ti.selling_price - ti.cost_price_at_time) - ti.discount_amount), 0),
                    COALESCE(SUM(ti.quantity), 0),
                    CASE WHEN COALESCE(SUM(ti.quantity), 0) > 0
                         THEN SUM(ti.quantity * ti.selling_price) / SUM(ti.quantity)
                         ELSE 0 END
                FROM transactions t
                JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
                WHERE t.store_id = :store_id
                  AND DATE(t.created_at) = :target_date
                  AND t.is_return = FALSE
                GROUP BY t.store_id, ti.product_id
                ON CONFLICT (date, store_id, product_id) DO UPDATE SET
                    revenue           = EXCLUDED.revenue,
                    profit            = EXCLUDED.profit,
                    units_sold        = EXCLUDED.units_sold,
                    avg_selling_price = EXCLUDED.avg_selling_price
            """), {"target_date": date_str, "store_id": store_id})

        _log('rebuild_daily_aggregates', store_id=store_id, date=date_str, status='done')


@shared_task(name='tasks.rebuild_daily_aggregates_all_stores')
def rebuild_daily_aggregates_all_stores():
    with task_session() as session:
        stores = session.execute(text("SELECT store_id FROM stores")).fetchall()
        today = date_type.today()
        yesterday = today - timedelta(days=1)
        for s in stores:
            rebuild_daily_aggregates.delay(s.store_id, str(today))
            rebuild_daily_aggregates.delay(s.store_id, str(yesterday))

# ──────────────────────────────────────────────────────────────────────────────
# 2. evaluate_alerts
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_alert(session, store_id, alert_type, priority, product_id, message, date_bucket):
    dialect = session.get_bind().dialect.name
    if dialect == 'sqlite':
        existing = session.execute(text("""
            SELECT alert_id FROM alerts
            WHERE store_id    = :store_id
              AND alert_type  = :alert_type
              AND (product_id = :product_id OR (product_id IS NULL AND :product_id IS NULL))
              AND DATE(created_at) = :date_bucket
              AND resolved_at IS NULL
            LIMIT 1
        """), {
            "store_id": store_id, "alert_type": alert_type,
            "product_id": product_id, "date_bucket": str(date_bucket),
        }).fetchone()
    else:
        existing = session.execute(text("""
            SELECT alert_id FROM alerts
            WHERE store_id    = :store_id
              AND alert_type  = :alert_type
              AND product_id IS NOT DISTINCT FROM :product_id
              AND DATE(created_at) = :date_bucket
              AND resolved_at IS NULL
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """), {
            "store_id": store_id, "alert_type": alert_type,
            "product_id": product_id, "date_bucket": str(date_bucket),
        }).fetchone()

    if existing: return False

    session.execute(text("""
        INSERT INTO alerts (store_id, alert_type, priority, product_id, message, created_at)
        VALUES (:store_id, :alert_type, :priority, :product_id, :message, CURRENT_TIMESTAMP)
    """), {
        "store_id": store_id, "alert_type": alert_type, "priority": priority,
        "product_id": product_id, "message": message,
    })
    return True

@shared_task(
    bind=True,
    name='tasks.evaluate_alerts',
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def evaluate_alerts(self, store_id: int):
    lock_key = f"lock:eval_alerts:{store_id}"
    with _RedisLock(lock_key, ttl=600) as acquired:
        if not acquired: return

        today = date_type.today()
        new_alerts = 0

        with task_session() as session:
            # a) LOW_STOCK
            low_stock_products = session.execute(text("""
                SELECT product_id, name, current_stock, reorder_level
                FROM products
                WHERE store_id = :store_id AND is_active = TRUE AND current_stock <= reorder_level
            """), {"store_id": store_id}).fetchall()
            for row in low_stock_products:
                msg = f"Low stock: '{row.name}' has {float(row.current_stock):.2f} units."
                if _upsert_alert(session, store_id, 'LOW_STOCK', 'CRITICAL', row.product_id, msg, today):
                    new_alerts += 1
                    _send_push_stub(store_id, 'LOW_STOCK', 'CRITICAL', msg)

            # b) MARGIN_WARNING
            margin_products = session.execute(text("""
                SELECT product_id, name, cost_price, selling_price
                FROM products
                WHERE store_id = :store_id AND is_active = TRUE AND cost_price >= selling_price
            """), {"store_id": store_id}).fetchall()
            for row in margin_products:
                msg = f"Margin warning: '{row.name}' cost >= selling price."
                if _upsert_alert(session, store_id, 'MARGIN_WARNING', 'CRITICAL', row.product_id, msg, today):
                    new_alerts += 1
                    _send_push_stub(store_id, 'MARGIN_WARNING', 'CRITICAL', msg)

            # c+d) Revenue anomalies (7-day MA)
            ma_start = today - timedelta(days=8)
            ma_end   = today - timedelta(days=1)
            ma_row = session.execute(text("""
                SELECT AVG(revenue) AS ma_revenue FROM daily_store_summary
                WHERE store_id = :store_id AND date >= :start AND date <= :end
            """), {"store_id": store_id, "start": str(ma_start), "end": str(ma_end)}).fetchone()

            today_row = session.execute(text("SELECT revenue FROM daily_store_summary WHERE store_id = :store_id AND date = :today"),
                                        {"store_id": store_id, "today": str(today)}).fetchone()

            if ma_row and ma_row.ma_revenue and today_row and today_row.revenue:
                ma = float(ma_row.ma_revenue)
                today_r = float(today_row.revenue)
                if ma > 0 and today_r < 0.7 * ma:
                    msg = f"Revenue drop: today {today_r:.2f} is < 70% of 7-day avg {ma:.2f}"
                    if _upsert_alert(session, store_id, 'REVENUE_DROP', 'HIGH', None, msg, today):
                        new_alerts += 1
                        _send_push_stub(store_id, 'REVENUE_DROP', 'HIGH', msg)
                elif ma > 0 and today_r > 1.5 * ma:
                    msg = f"Sales spike: today {today_r:.2f} is > 150% of 7-day avg {ma:.2f}"
                    if _upsert_alert(session, store_id, 'SALES_SPIKE', 'INFO', None, msg, today):
                        new_alerts += 1

        _log('evaluate_alerts', store_id=store_id, status='done', new_alerts=new_alerts)


@shared_task(name='tasks.evaluate_alerts_all_stores')
def evaluate_alerts_all_stores():
    with task_session() as session:
        stores = session.execute(text("SELECT store_id FROM stores")).fetchall()
        for s in stores:
            evaluate_alerts.delay(s.store_id)



# ──────────────────────────────────────────────────────────────────────────────
# 3. run_batch_forecasting
# ──────────────────────────────────────────────────────────────────────────────

MAX_SKUS_PER_STORE = 200
MIN_HISTORY_DAYS   = 14    # minimum rows needed to attempt any forecast
HORIZON_DAYS       = 7
PARETO_WINDOW_DAYS = 90    # look-back for Pareto revenue ranking


def _get_top_skus(session, store_id: int) -> list[int]:
    """Return product_ids in top 20% by revenue over the last 90 days."""
    rows = session.execute(text("""
        SELECT product_id, SUM(revenue) AS total_rev
        FROM daily_sku_summary
        WHERE store_id = :sid
          AND date >= CURRENT_DATE - :window
        GROUP BY product_id
        ORDER BY total_rev DESC, product_id ASC
    """), {"sid": store_id, "window": PARETO_WINDOW_DAYS}).fetchall()

    if not rows:
        return []
    n_top = max(1, round(len(rows) * 0.20))
    top = [r.product_id for r in rows[:n_top]]
    return top[:MAX_SKUS_PER_STORE]


def _fetch_sku_history(session, store_id: int, product_id: int):
    """Return (dates, values) sorted ascending. Empty if no data."""
    rows = session.execute(text("""
        SELECT date, units_sold
        FROM daily_sku_summary
        WHERE store_id = :sid AND product_id = :pid
        ORDER BY date ASC
    """), {"sid": store_id, "pid": product_id}).fetchall()
    
    if not rows:
        return [], []
        
    # Zero-fill missing dates for continuous time series
    from datetime import timedelta
    date_dict = {r.date: float(r.units_sold or 0) for r in rows}
    start_date = rows[0].date
    end_date = rows[-1].date
    
    filled_dates = []
    filled_values = []
    curr = start_date
    while curr <= end_date:
        filled_dates.append(curr)
        filled_values.append(date_dict.get(curr, 0.0))
        curr += timedelta(days=1)
        
    return filled_dates, filled_values


def _fetch_store_history(session, store_id: int):
    """Return (dates, values) for store-level daily revenue sorted ascending."""
    rows = session.execute(text("""
        SELECT date, revenue
        FROM daily_store_summary
        WHERE store_id = :sid
        ORDER BY date ASC
    """), {"sid": store_id}).fetchall()
    
    if not rows:
        return [], []
        
    # Zero-fill missing dates for continuous time series
    from datetime import timedelta
    date_dict = {r.date: float(r.revenue or 0) for r in rows}
    start_date = rows[0].date
    end_date = rows[-1].date
    
    filled_dates = []
    filled_values = []
    curr = start_date
    while curr <= end_date:
        filled_dates.append(curr)
        filled_values.append(date_dict.get(curr, 0.0))
        curr += timedelta(days=1)
        
    return filled_dates, filled_values


def _upsert_forecast(session, store_id, product_id, result, dialect):
    """Write forecast points into forecast_cache (upsert by store+product+date)."""
    from app.forecasting.engine import ForecastResult
    for pt in result.points:
        if dialect == 'sqlite':
            # SQLite: manual upsert
            existing = session.execute(text("""
                SELECT id FROM forecast_cache
                WHERE store_id = :sid
                  AND (product_id = :pid OR (product_id IS NULL AND :pid IS NULL))
                  AND forecast_date = :fd
            """), {
                "sid": store_id, "pid": product_id,
                "fd": str(pt.forecast_date),
            }).fetchone()
            if existing:
                session.execute(text("""
                    UPDATE forecast_cache
                    SET forecast_value=:fv, lower_bound=:lb, upper_bound=:ub,
                        regime=:regime, model_type=:mt, training_window_days=:twd,
                        generated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                """), {
                    "fv": pt.forecast_mean, "lb": pt.lower_bound, "ub": pt.upper_bound,
                    "regime": result.regime, "mt": result.model_type,
                    "twd": result.training_window_days, "id": existing.id,
                })
            else:
                session.execute(text("""
                    INSERT INTO forecast_cache
                        (store_id, product_id, forecast_date, forecast_value,
                         lower_bound, upper_bound, regime, model_type,
                         training_window_days, generated_at)
                    VALUES (:sid, :pid, :fd, :fv, :lb, :ub, :regime, :mt, :twd, CURRENT_TIMESTAMP)
                """), {
                    "sid": store_id, "pid": product_id, "fd": str(pt.forecast_date),
                    "fv": pt.forecast_mean, "lb": pt.lower_bound, "ub": pt.upper_bound,
                    "regime": result.regime, "mt": result.model_type,
                    "twd": result.training_window_days,
                })
        else:
            session.execute(text("""
                INSERT INTO forecast_cache
                    (store_id, product_id, forecast_date, forecast_value,
                     lower_bound, upper_bound, regime, model_type,
                     training_window_days, generated_at)
                VALUES (:sid, :pid, :fd, :fv, :lb, :ub, :regime, :mt, :twd, CURRENT_TIMESTAMP)
                ON CONFLICT (store_id, product_id, forecast_date) DO UPDATE SET
                    forecast_value        = EXCLUDED.forecast_value,
                    lower_bound           = EXCLUDED.lower_bound,
                    upper_bound           = EXCLUDED.upper_bound,
                    regime                = EXCLUDED.regime,
                    model_type            = EXCLUDED.model_type,
                    training_window_days  = EXCLUDED.training_window_days,
                    generated_at          = CURRENT_TIMESTAMP
            """), {
                "sid": store_id, "pid": product_id, "fd": str(pt.forecast_date),
                "fv": pt.forecast_mean, "lb": pt.lower_bound, "ub": pt.upper_bound,
                "regime": result.regime, "mt": result.model_type,
                "twd": result.training_window_days,
            })


@shared_task(bind=True, name='tasks.forecast_store', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def forecast_store(self, store_id: int):
    lock_key = f"lock:forecast:{store_id}:{date_type.today()}"
    with _RedisLock(lock_key, ttl=1800) as acquired:
        if not acquired:
            _log('forecast_store', store_id=store_id, status='skipped_lock_held')
            return
        _log('forecast_store', store_id=store_id, status='start')

        from app.forecasting.engine import run_forecast

        with task_session() as session:
            dialect = session.get_bind().dialect.name

            # ── 1. Store-level forecast (product_id = NULL) ──────────────────
            s_dates, s_vals = _fetch_store_history(session, store_id)
            if len(s_dates) >= MIN_HISTORY_DAYS:
                try:
                    result = run_forecast(s_dates, s_vals, horizon=HORIZON_DAYS)
                    _upsert_forecast(session, store_id, None, result, dialect)
                except Exception as exc:
                    _log('forecast_store', store_id=store_id, status='store_level_error', error=str(exc))

            # ── 2. SKU-level forecasts (Pareto top 20%) ───────────────────────
            top_skus = _get_top_skus(session, store_id)
            forecasted = 0
            for pid in top_skus:
                dates, vals = _fetch_sku_history(session, store_id, pid)
                if len(dates) < MIN_HISTORY_DAYS:
                    continue
                try:
                    result = run_forecast(dates, vals, horizon=HORIZON_DAYS)
                    _upsert_forecast(session, store_id, pid, result, dialect)
                    forecasted += 1
                except Exception as exc:
                    _log('forecast_store', store_id=store_id, product_id=pid, status='sku_error', error=str(exc))

        _log('forecast_store', store_id=store_id, status='done', skus_forecasted=forecasted)


@shared_task(bind=True, name='tasks.run_batch_forecasting', max_retries=1)
def run_batch_forecasting(self):
    lock_key = f"lock:batch_forecast:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired: return
        batch_size = 50
        offset = 0
        with task_session() as session:
            while True:
                stores = session.execute(
                    text("SELECT store_id FROM stores ORDER BY store_id LIMIT :limit OFFSET :offset"),
                    {"limit": batch_size, "offset": offset}
                ).fetchall()
                if not stores: break
                for s in stores:
                    forecast_store.delay(s.store_id)
                offset += batch_size



# ──────────────────────────────────────────────────────────────────────────────
# 4. detect_slow_movers
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.detect_slow_movers', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def detect_slow_movers(self):
    lock_key = f"lock:slow_movers:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired: return

        today = date_type.today()
        week_start = today - timedelta(days=today.weekday())
        threshold_date = today - timedelta(days=30)

        with task_session() as session:
            slow_products = session.execute(text("""
                SELECT p.product_id, p.store_id, p.name
                FROM products p
                WHERE p.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM daily_sku_summary dss
                      WHERE dss.product_id = p.product_id AND dss.store_id = p.store_id
                        AND dss.date >= :threshold_date AND dss.units_sold > 0
                  )
            """), {"threshold_date": str(threshold_date)}).fetchall()

            for row in slow_products:
                msg = f"Slow mover: '{row.name}' zero sales 30 days."
                _upsert_alert(session, row.store_id, 'SLOW_MOVER', 'LOW', row.product_id, msg, week_start)


# ──────────────────────────────────────────────────────────────────────────────
# 5. send_weekly_digest
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.send_weekly_digest', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def send_weekly_digest(self):
    lock_key = f"lock:digest:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired: return
        today = date_type.today()
        week_start = today - timedelta(days=7)

        with task_session() as session:
            stores = session.execute(text("SELECT store_id FROM stores")).fetchall()
            for s in stores:
                rev_row = session.execute(text("""
                    SELECT COALESCE(SUM(revenue), 0) AS revenue FROM daily_store_summary
                    WHERE store_id = :sid AND date >= :start AND date < :today
                """), {"sid": s.store_id, "start": str(week_start), "today": str(today)}).fetchone()
                
                top_skus = session.execute(text("""
                    SELECT p.name, SUM(dss.revenue) AS rev FROM daily_sku_summary dss
                    JOIN products p ON p.product_id = dss.product_id
                    WHERE dss.store_id = :sid AND dss.date >= :start AND dss.date < :today
                    GROUP BY p.name ORDER BY rev DESC LIMIT 5
                """), {"sid": s.store_id, "start": str(week_start), "today": str(today)}).fetchall()

                _log('send_weekly_digest', store_id=s.store_id, weekly_revenue=float(rev_row.revenue))
