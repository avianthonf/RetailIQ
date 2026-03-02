"""
RetailIQ Celery Tasks
=====================
All tasks use DB/Redis for guarantees, are idempotent, retry-able.
"""
import json
import logging
import os
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis as redis_lib
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import text

from app.models import AnalyticsSnapshot

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

    if existing:
        return False

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
        if not acquired:
            return

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




def _coerce_to_date(value):
    """Normalize DB date values across dialects (date/datetime/ISO string)."""
    if value is None:
        return None
    if hasattr(value, 'date') and not isinstance(value, date_type):
        # datetime -> date
        try:
            return value.date()
        except Exception:
            pass
    if isinstance(value, date_type):
        return value
    if isinstance(value, str):
        return date_type.fromisoformat(value[:10])
    return value

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
    date_dict = {_coerce_to_date(r.date): float(r.units_sold or 0) for r in rows}
    start_date = _coerce_to_date(rows[0].date)
    end_date = _coerce_to_date(rows[-1].date)

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
    date_dict = {_coerce_to_date(r.date): float(r.revenue or 0) for r in rows}
    start_date = _coerce_to_date(rows[0].date)
    end_date = _coerce_to_date(rows[-1].date)

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
        if not acquired:
            return
        batch_size = 50
        offset = 0
        with task_session() as session:
            while True:
                stores = session.execute(
                    text("SELECT store_id FROM stores ORDER BY store_id LIMIT :limit OFFSET :offset"),
                    {"limit": batch_size, "offset": offset}
                ).fetchall()
                if not stores:
                    break
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
        if not acquired:
            return

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
        if not acquired:
            return
        today = date_type.today()
        week_start = today - timedelta(days=7)

        with task_session() as session:
            stores = session.execute(text("SELECT store_id FROM stores")).fetchall()
            for s in stores:
                rev_row = session.execute(text("""
                    SELECT COALESCE(SUM(revenue), 0) AS revenue FROM daily_store_summary
                    WHERE store_id = :sid AND date >= :start AND date < :today
                """), {"sid": s.store_id, "start": str(week_start), "today": str(today)}).fetchone()

                session.execute(text("""
                    SELECT p.name, SUM(dss.revenue) AS rev FROM daily_sku_summary dss
                    JOIN products p ON p.product_id = dss.product_id
                    WHERE dss.store_id = :sid AND dss.date >= :start AND dss.date < :today
                    GROUP BY p.name ORDER BY rev DESC LIMIT 5
                """), {"sid": s.store_id, "start": str(week_start), "today": str(today)}).fetchall()

                _log('send_weekly_digest', store_id=s.store_id, weekly_revenue=float(rev_row.revenue))

# ──────────────────────────────────────────────────────────────────────────────
# 6. check_overdue_purchase_orders
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.check_overdue_purchase_orders', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def check_overdue_purchase_orders(self):
    lock_key = f"lock:overdue_po:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired:
            return

        today = date_type.today()

        with task_session() as session:
            overdue_pos = session.execute(text("""
                SELECT po.id, po.store_id, po.expected_delivery_date, s.name as supplier_name
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.id
                WHERE po.status = 'SENT'
                  AND po.expected_delivery_date < :today
            """), {"today": str(today)}).fetchall()

            for row in overdue_pos:
                n_days = (today - _coerce_to_date(row.expected_delivery_date)).days
                msg = f"PO #{row.id} from {row.supplier_name} is overdue by {n_days} days."
                _upsert_alert(session, row.store_id, 'OVERDUE_PO', 'MEDIUM', None, msg, today)

# ──────────────────────────────────────────────────────────────────────────────
# 7. auto_close_open_sessions (Staff Performance)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.auto_close_open_sessions', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def auto_close_open_sessions(self):
    """Daily job. Closes all OPEN staff sessions older than 16 hours."""
    lock_key = f"lock:auto_close_sessions:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired:
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=16)

        with task_session() as session:
            # We use ORM syntax or raw SQL, let's use raw SQL for consistency here
            session.execute(text("""
                UPDATE staff_sessions
                SET status = 'CLOSED', ended_at = CURRENT_TIMESTAMP
                WHERE status = 'OPEN' AND started_at < :cutoff
            """), {"cutoff": str(cutoff_time)})

            _log('auto_close_open_sessions', cutoff=cutoff_time.isoformat())

# ──────────────────────────────────────────────────────────────────────────────
# 8. generate_staff_daily_summary
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.generate_staff_daily_summary', max_retries=3, default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def generate_staff_daily_summary(self):
    """Daily. Computes yesterday's actual vs target for each staff, stores in Redis cache."""
    yesterday = date_type.today() - timedelta(days=1)
    lock_key = f"lock:generate_staff_summary:{yesterday}"

    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired:
            return

        with task_session() as session:
            # Get all targets for yesterday
            targets = session.execute(text("""
                SELECT t.store_id, t.user_id, t.revenue_target, t.transaction_count_target, u.full_name, u.mobile_number
                FROM staff_daily_targets t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.target_date = :yesterday
            """), {"yesterday": str(yesterday)}).fetchall()

            r = _redis_client()

            for row in targets:
                # Calculate actuals from yesterday logic
                # Transactions done by user OR in session owned by user
                actuals = session.execute(text("""
                    SELECT
                        COUNT(DISTINCT t.transaction_id) as txn_count,
                        COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0) as revenue
                    FROM transactions t
                    JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
                    LEFT JOIN staff_sessions ss ON t.session_id = ss.id
                    WHERE t.store_id = :store_id
                      AND t.is_return = FALSE
                      AND DATE(t.created_at) = :yesterday
                      AND ss.user_id = :user_id
                """), {
                    "store_id": row.store_id,
                    "yesterday": str(yesterday),
                    "user_id": row.user_id
                }).fetchone()

                summary = {
                    "user_id": row.user_id,
                    "name": row.full_name or row.mobile_number,
                    "target_date": str(yesterday),
                    "target_revenue": float(row.revenue_target) if row.revenue_target else None,
                    "target_txns": row.transaction_count_target,
                    "actual_revenue": float(actuals.revenue) if actuals else 0.0,
                    "actual_txns": int(actuals.txn_count) if actuals else 0
                }

                cache_key = f"staff_summary:{row.store_id}:{yesterday}"
                r.hset(cache_key, str(row.user_id), json.dumps(summary))
                # Expire in 30 days
                r.expire(cache_key, 86400 * 30)

            _log('generate_staff_daily_summary', summary_date=str(yesterday), count=len(targets))

@shared_task(name="tasks.build_analytics_snapshot", bind=True, max_retries=3)
def build_analytics_snapshot(self, store_id):
    """
    Builds the compact 50KB offline JSON payload for a store and upserts it.
    """
    logger.info(f"Building analytics snapshot for store_id={store_id}")
    with task_session() as db:
        from app.offline.builder import build_snapshot

        try:
            snapshot_data = build_snapshot(store_id, db)
            serialized_len = len(json.dumps(snapshot_data).encode('utf-8'))

            # Upsert
            existing = db.query(AnalyticsSnapshot).filter_by(store_id=store_id).first()
            if existing:
                existing.snapshot_data = snapshot_data
                existing.built_at = datetime.fromisoformat(snapshot_data["built_at"])
                existing.size_bytes = serialized_len
            else:
                new_snap = AnalyticsSnapshot(
                    store_id=store_id,
                    snapshot_data=snapshot_data,
                    built_at=datetime.fromisoformat(snapshot_data["built_at"]),
                    size_bytes=serialized_len
                )
                db.add(new_snap)

            db.commit()
            _log('build_analytics_snapshot', store_id=store_id, size=serialized_len)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to build analytics snapshot for store {store_id}: {e}")
            raise self.retry(exc=e, countdown=60)

@shared_task(name="tasks.build_all_analytics_snapshots")
def build_all_analytics_snapshots():
    """Triggers snapshot generation for all active stores."""
    logger.info("Starting batch analytics snapshots generation")
    with task_session() as db:
        from app.models import Store
        stores = db.session.query(Store).filter(Store.is_active is True).all()
        for store in stores:
            build_analytics_snapshot.delay(store.store_id)

    _log('build_all_analytics_snapshots', count=len(stores))

# ──────────────────────────────────────────────────────────────────────────────
# 11. expire_loyalty_points
# ──────────────────────────────────────────────────────────────────────────────
@shared_task(name="tasks.expire_loyalty_points", bind=True, max_retries=3)
def expire_loyalty_points(self):
    """Monthly task on the 1st: expire points older than expiry_days due to inactivity."""
    from decimal import Decimal

    from app.models import CustomerLoyaltyAccount, LoyaltyProgram, LoyaltyTransaction
    with task_session() as session:
        programs = session.query(LoyaltyProgram).filter_by(is_active=True).all()
        for prog in programs:
            expiry_date = datetime.utcnow() - timedelta(days=prog.expiry_days)
            # Fetch accounts and evaluate conditions in python to bypass SQLite string/Numeric typing mismatches
            accounts = session.query(CustomerLoyaltyAccount).filter_by(store_id=prog.store_id).all()

            for acc in accounts:
                if acc.redeemable_points is None or acc.redeemable_points <= 0:
                    continue
                if acc.last_activity_at is None or acc.last_activity_at >= expiry_date:
                    continue

                expired_points = Decimal(str(acc.redeemable_points))
                acc.total_points = Decimal(str(acc.total_points)) - expired_points
                acc.redeemable_points = 0
                acc.last_activity_at = datetime.utcnow()

                ltxn = LoyaltyTransaction(
                    account_id=acc.id,
                    type='EXPIRE',
                    points=-expired_points,
                    balance_after=acc.total_points,
                    notes=f"Points expired after {prog.expiry_days} days of inactivity"
                )
                session.add(ltxn)

        _log('expire_loyalty_points', processed_programs=len(programs))

# ──────────────────────────────────────────────────────────────────────────────
# 12. credit_overdue_alerts
# ──────────────────────────────────────────────────────────────────────────────
@shared_task(name="tasks.credit_overdue_alerts", bind=True, max_retries=3)
def credit_overdue_alerts(self):
    """Daily task: create HIGH-priority alerts for customers with credit > 0 and no repayment in 30 days."""
    from app.models import CreditLedger, Customer
    with task_session() as session:
        overdue_date = datetime.utcnow() - timedelta(days=30)
        ledgers = session.query(CreditLedger).filter(
            CreditLedger.balance > 0,
            CreditLedger.updated_at < overdue_date
        ).all()

        date_bucket = datetime.utcnow().strftime("%Y-%m-%d")
        for ledger in ledgers:
            customer = session.query(Customer).filter_by(customer_id=ledger.customer_id).first()
            if customer:
                _upsert_alert(
                    session,
                    store_id=ledger.store_id,
                    alert_type="credit_overdue",
                    priority="HIGH",
                    product_id=None,
                    message=f"Customer {customer.name} has overdue credit balance of ₹{ledger.balance} (No repayment in 30 days).",
                    date_bucket=date_bucket
                )

        _log('credit_overdue_alerts', alerts_created=len(ledgers))

# ──────────────────────────────────────────────────────────────────────────────
# 13. compile_monthly_gst
# ──────────────────────────────────────────────────────────────────────────────
@shared_task(name="tasks.compile_monthly_gst", bind=True, max_retries=3)
def compile_monthly_gst(self, store_id, period):
    """Monthly task: aggregate gst_transactions into a gst_filing_period and generate GSTR-1 JSON."""
    import json
    import os

    from app.models import GSTFilingPeriod, GSTTransaction, Store, StoreGSTConfig

    with task_session() as session:
        gst_txns = session.query(GSTTransaction).filter_by(store_id=store_id, period=period).all()

        total_taxable = Decimal('0')
        total_cgst = Decimal('0')
        total_sgst = Decimal('0')
        total_igst = Decimal('0')
        hsn_agg = {}

        for gt in gst_txns:
            total_taxable += Decimal(str(gt.taxable_amount or 0))
            total_cgst += Decimal(str(gt.cgst_amount or 0))
            total_sgst += Decimal(str(gt.sgst_amount or 0))
            total_igst += Decimal(str(gt.igst_amount or 0))
            if gt.hsn_breakdown:
                for hsn, detail in gt.hsn_breakdown.items():
                    if hsn not in hsn_agg:
                        hsn_agg[hsn] = {'taxable': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'rate': detail.get('rate', 0)}
                    hsn_agg[hsn]['taxable'] += detail.get('taxable', 0)
                    hsn_agg[hsn]['cgst'] += detail.get('cgst', 0)
                    hsn_agg[hsn]['sgst'] += detail.get('sgst', 0)
                    hsn_agg[hsn]['igst'] += detail.get('igst', 0)

        # Upsert filing period
        filing = session.query(GSTFilingPeriod).filter_by(store_id=store_id, period=period).first()
        if not filing:
            filing = GSTFilingPeriod(store_id=store_id, period=period)
            session.add(filing)
            session.flush()

        filing.total_taxable = round(total_taxable, 2)
        filing.total_cgst = round(total_cgst, 2)
        filing.total_sgst = round(total_sgst, 2)
        filing.total_igst = round(total_igst, 2)
        filing.invoice_count = len(gst_txns)
        filing.compiled_at = datetime.utcnow()
        filing.status = 'COMPILED'

        # Build GSTR-1 JSON structure
        config = session.query(StoreGSTConfig).filter_by(store_id=store_id).first()
        store = session.query(Store).filter_by(store_id=store_id).first()

        gstr1 = {
            'gstin': config.gstin if config else None,
            'fp': period.replace('-', ''),  # GSTR-1 uses MMYYYY format
            'store_name': store.store_name if store else None,
            'b2b': [],  # B2B invoices (placeholder)
            'b2cs': [],  # B2C small invoices
            'hsn': {
                'data': [
                    {
                        'hsn_sc': hsn,
                        'txval': round(d['taxable'], 2),
                        'camt': round(d['cgst'], 2),
                        'samt': round(d['sgst'], 2),
                        'iamt': round(d['igst'], 2),
                        'rt': d['rate']
                    }
                    for hsn, d in hsn_agg.items()
                ]
            },
            'doc_issue': {'doc_det': [{'num': len(gst_txns), 'from': '1', 'to': str(len(gst_txns))}]},
            'total_taxable': float(round(total_taxable, 2)),
            'total_cgst': float(round(total_cgst, 2)),
            'total_sgst': float(round(total_sgst, 2)),
            'total_igst': float(round(total_igst, 2)),
        }

        # Write JSON to filesystem
        gstr1_dir = os.environ.get('GSTR1_OUTPUT_DIR', '/tmp/gstr1')
        os.makedirs(gstr1_dir, exist_ok=True)
        json_path = os.path.join(gstr1_dir, f'{store_id}_{period}.json')
        with open(json_path, 'w') as f:
            json.dump(gstr1, f, indent=2)

        filing.gstr1_json_path = json_path
        _log('compile_monthly_gst', store_id=store_id, period=period, invoices=len(gst_txns))

# ──────────────────────────────────────────────────────────────────────────────
# 14. update_gst_transactions_task
# ──────────────────────────────────────────────────────────────────────────────
@shared_task(name="tasks.update_gst_transactions_task", bind=True, max_retries=3)
def update_gst_transactions_task(self):
    """Sweep for transactions in the current period missing GST rows and backfill them."""
    from app.models import Category, GSTTransaction, HSNMaster, Product, StoreGSTConfig, Transaction, TransactionItem

    with task_session() as session:
        current_period = datetime.utcnow().strftime('%Y-%m')

        # Find GST-enabled stores
        configs = session.query(StoreGSTConfig).filter_by(is_gst_enabled=True, registration_type='REGULAR').all()

        for config in configs:
            store_id = config.store_id

            # Find transactions in current period without a GST row
            existing_gst_txn_ids = session.query(GSTTransaction.transaction_id).filter_by(
                store_id=store_id, period=current_period
            ).subquery()

            txns = session.query(Transaction).filter(
                Transaction.store_id == store_id,
                Transaction.created_at >= datetime.strptime(current_period + '-01', '%Y-%m-%d'),
                Transaction.is_return is False,
                ~Transaction.transaction_id.in_(existing_gst_txn_ids)
            ).all()

            for txn in txns:
                items = session.query(TransactionItem).filter_by(transaction_id=txn.transaction_id).all()
                hsn_breakdown = {}
                total_taxable = Decimal('0')
                total_cgst = Decimal('0')
                total_sgst = Decimal('0')

                for item in items:
                    product = session.query(Product).filter_by(product_id=item.product_id).first()
                    if not product:
                        continue

                    cat = getattr(product, 'gst_category', 'REGULAR') or 'REGULAR'
                    if cat in ('EXEMPT', 'ZERO'):
                        continue

                    gst_rate = Decimal('0')
                    hsn_code_val = getattr(product, 'hsn_code', None) or 'NONE'
                    if product.hsn_code:
                        hsn_entry = session.query(HSNMaster).filter_by(hsn_code=product.hsn_code).first()
                        if hsn_entry and hsn_entry.default_gst_rate:
                            gst_rate = Decimal(str(hsn_entry.default_gst_rate))
                    if gst_rate == 0 and product.category_id:
                        category = session.query(Category).filter_by(category_id=product.category_id).first()
                        if category and category.gst_rate:
                            gst_rate = Decimal(str(category.gst_rate))
                    if gst_rate == 0:
                        continue

                    qty = Decimal(str(item.quantity or 0))
                    sp = Decimal(str(item.selling_price or 0))
                    disc = Decimal(str(item.discount_amount or 0))
                    line_total = qty * sp - disc
                    taxable = line_total / (1 + gst_rate / 100)
                    tax = line_total - taxable
                    cgst = tax / 2
                    sgst = tax / 2

                    total_taxable += taxable
                    total_cgst += cgst
                    total_sgst += sgst

                    if hsn_code_val not in hsn_breakdown:
                        hsn_breakdown[hsn_code_val] = {'taxable': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'rate': float(gst_rate)}
                    hsn_breakdown[hsn_code_val]['taxable'] += float(round(taxable, 2))
                    hsn_breakdown[hsn_code_val]['cgst'] += float(round(cgst, 2))
                    hsn_breakdown[hsn_code_val]['sgst'] += float(round(sgst, 2))

                if total_taxable > 0 or total_cgst > 0:
                    gst_row = GSTTransaction(
                        transaction_id=txn.transaction_id,
                        store_id=store_id,
                        period=current_period,
                        taxable_amount=round(total_taxable, 2),
                        cgst_amount=round(total_cgst, 2),
                        sgst_amount=round(total_sgst, 2),
                        igst_amount=Decimal('0'),
                        total_gst=round(total_cgst + total_sgst, 2),
                        hsn_breakdown=hsn_breakdown
                    )
                    session.add(gst_row)

        _log('update_gst_transactions_task', stores_checked=len(configs))



# ──────────────────────────────────────────────────────────────────────────────
# CHAIN & MULTI-STORE TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.aggregate_chain_daily_all_groups')
def aggregate_chain_daily_all_groups(self):
    """Orchestrator to run daily aggregation for all chain groups"""
    with task_session() as session:
        groups = session.execute(text("SELECT id FROM store_groups")).fetchall()
        for g in groups:
            aggregate_chain_daily.delay(str(g.id))

import uuid as _uuid


@shared_task(bind=True, name='tasks.aggregate_chain_daily', max_retries=3)
def aggregate_chain_daily(self, group_id_str):
    """
    Rolls up DailyStoreSummary sums into ChainDailyAggregate for the group.
    """
    today = date_type.today()
    lock_key = f"lock:chain_agg:{group_id_str}:{today}"
    with _RedisLock(lock_key, ttl=1800) as acquired:
        if not acquired:
            return

        with task_session() as session:
            memberships = session.execute(
                text("SELECT store_id FROM store_group_memberships WHERE group_id = :gid"),
                {"gid": group_id_str}
            ).fetchall()

            for m in memberships:
                daily_sum = session.execute(text("""
                    SELECT revenue, profit, transaction_count
                    FROM daily_store_summary
                    WHERE store_id = :sid AND date = :tdate
                """), {"sid": m.store_id, "tdate": str(today)}).fetchone()

                if not daily_sum:
                    continue

                session.execute(text("""
                    INSERT INTO chain_daily_aggregates (id, group_id, store_id, date, revenue, profit, transaction_count)
                    VALUES (:id, :gid, :sid, :tdate, :rev, :prof, :tx_count)
                    ON CONFLICT (group_id, store_id, date)
                    DO UPDATE SET revenue = EXCLUDED.revenue, profit = EXCLUDED.profit, transaction_count = EXCLUDED.transaction_count
                """), {
                    "id": str(_uuid.uuid4()),
                    "gid": group_id_str,
                    "sid": m.store_id,
                    "tdate": str(today),
                    "rev": float(daily_sum.revenue) if daily_sum.revenue else 0.0,
                    "prof": float(daily_sum.profit) if daily_sum.profit else 0.0,
                    "tx_count": daily_sum.transaction_count
                })
            session.commit()


@shared_task(bind=True, name='tasks.detect_transfer_opportunities_all_groups')
def detect_transfer_opportunities_all_groups(self):
    """Orchestrator to run transfer detection for all groups weekly"""
    with task_session() as session:
        groups = session.execute(text("SELECT id FROM store_groups")).fetchall()
        for g in groups:
            detect_transfer_opportunities.delay(str(g.id))


@shared_task(bind=True, name='tasks.detect_transfer_opportunities', max_retries=3)
def detect_transfer_opportunities(self, group_id_str):
    """
    Finds critical reorder alerts. Matches them with surplus stock in sibling stores
    and generates an InterStoreTransferSuggestion.
    """
    lock_key = f"lock:transfer_opp:{group_id_str}:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired:
            return

        with task_session() as session:
            memberships = session.execute(
                text("SELECT store_id FROM store_group_memberships WHERE group_id = :gid"),
                {"gid": group_id_str}
            ).fetchall()
            store_ids = [m.store_id for m in memberships]

            if len(store_ids) < 2:
                return

            placeholder = ", ".join(str(sid) for sid in store_ids)

            critical_alerts = session.execute(text(
                "SELECT store_id, product_id FROM alerts"
                " WHERE alert_type IN ('LOW_STOCK', 'STOCKOUT_SOON')"
                " AND priority = 'CRITICAL'"
                " AND resolved_at IS NULL"
                f" AND store_id IN ({placeholder})"
            )).fetchall()

            for alert in critical_alerts:
                short_store = alert.store_id
                pid = alert.product_id

                surplus_candidates = session.execute(text(
                    "SELECT p.store_id, p.current_stock, p.reorder_level"
                    " FROM products p"
                    " WHERE p.product_id = :pid"
                    f" AND p.store_id IN ({placeholder})"
                    " AND p.store_id != :short_store"
                    " AND p.current_stock > (p.reorder_level * 1.5)"
                    " AND NOT EXISTS ("
                    "   SELECT 1 FROM alerts a"
                    "   WHERE a.store_id = p.store_id"
                    "   AND a.product_id = p.product_id"
                    "   AND a.priority = 'CRITICAL'"
                    "   AND a.resolved_at IS NULL"
                    " )"
                ), {"pid": pid, "short_store": short_store}).fetchall()

                if not surplus_candidates:
                    continue

                best_target = max(surplus_candidates, key=lambda x: x.current_stock)
                suggested_qty = round(
                    (float(best_target.current_stock) - float(best_target.reorder_level)) * 0.5
                )

                if suggested_qty <= 0:
                    continue

                session.execute(text("""
                    INSERT INTO inter_store_transfer_suggestions
                        (id, group_id, from_store_id, to_store_id, product_id, suggested_qty, reason)
                    VALUES (:id, :gid, :from_store, :to_store, :pid, :qty, :reason)
                """), {
                    "id": str(_uuid.uuid4()),
                    "gid": group_id_str,
                    "from_store": best_target.store_id,
                    "to_store": short_store,
                    "pid": pid,
                    "qty": suggested_qty,
                    "reason": f"Surplus identified in sibling Store {best_target.store_id}"
                })

            session.commit()


# ──────────────────────────────────────────────────────────────────────────────
# PRICING ANALYSIS TASK
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='tasks.run_weekly_pricing_analysis', max_retries=3,
             default_retry_delay=120, autoretry_for=(Exception,), retry_backoff=True)
def run_weekly_pricing_analysis(self):
    """
    Weekly (Sunday 03:00): generate pricing suggestions for all stores.
    Upserts suggestions; skips if a PENDING suggestion for the same product
    was already created within the last 7 days.
    """
    import uuid as _uuid
    lock_key = f"lock:pricing_analysis:{date_type.today()}"
    with _RedisLock(lock_key, ttl=3600) as acquired:
        if not acquired:
            _log('run_weekly_pricing_analysis', status='skipped_lock_held')
            return

        _log('run_weekly_pricing_analysis', status='start')

        from app.pricing.engine import generate_price_suggestions

        cutoff_7d = date_type.today() - timedelta(days=7)

        with task_session() as session:
            dialect = session.get_bind().dialect.name
            stores = session.execute(text("SELECT store_id FROM stores")).fetchall()
            total_inserted = 0

            for store_row in stores:
                sid = store_row.store_id
                try:
                    suggestions = generate_price_suggestions(sid, session)
                except Exception as exc:
                    _log('run_weekly_pricing_analysis', store_id=sid,
                         status='engine_error', error=str(exc))
                    continue

                for sg in suggestions:
                    pid = sg['product_id']

                    # Check for recent PENDING suggestion for same product
                    if dialect == 'sqlite':
                        recent = session.execute(text("""
                            SELECT id FROM pricing_suggestions
                            WHERE store_id   = :sid
                              AND product_id = :pid
                              AND status     = 'PENDING'
                              AND created_at >= :cutoff
                            LIMIT 1
                        """), {
                            "sid": sid, "pid": pid,
                            "cutoff": str(cutoff_7d),
                        }).fetchone()
                    else:
                        recent = session.execute(text("""
                            SELECT id FROM pricing_suggestions
                            WHERE store_id   = :sid
                              AND product_id = :pid
                              AND status     = 'PENDING'
                              AND created_at >= :cutoff
                            LIMIT 1
                        """), {
                            "sid": sid, "pid": pid,
                            "cutoff": str(cutoff_7d),
                        }).fetchone()

                    if recent:
                        continue  # skip – recent suggestion already exists

                    current  = float(sg['current_price'])
                    proposed = float(sg['suggested_price'])
                    change_pct = round((proposed - current) / current * 100, 2) if current else 0

                    session.execute(text("""
                        INSERT INTO pricing_suggestions
                            (product_id, store_id, suggested_price, current_price,
                             price_change_pct, reason, confidence, status, created_at)
                        VALUES
                            (:pid, :sid, :suggested, :current,
                             :pct, :reason, :confidence, 'PENDING', CURRENT_TIMESTAMP)
                    """), {
                        "pid": pid,
                        "sid": sid,
                        "suggested": proposed,
                        "current": current,
                        "pct": change_pct,
                        "reason": sg['reason'][:256],
                        "confidence": sg['confidence'][:16],
                    })
                    total_inserted += 1

            _log('run_weekly_pricing_analysis', status='done',
                 stores=len(stores), suggestions_inserted=total_inserted)


@shared_task(bind=True, max_retries=1)
def process_ocr_job(self, job_id: str):
    """
    Process an uploaded invoice image via OCR.
    Extract items, match products via pg_trgm, and transition job to REVIEW.
    """
    import uuid

    import pytesseract
    from PIL import Image

    from app.vision.parser import parse_invoice_text

    _log('process_ocr_job', job_id=job_id, status='started')

    with task_session() as session:
        # Load job
        job_row = session.execute(
            text("SELECT * FROM ocr_jobs WHERE id = :jid FOR UPDATE"),
            {"jid": job_id}
        ).fetchone()

        if not job_row:
            _log('process_ocr_job', job_id=job_id, error='Job not found')
            return

        if job_row.status not in ('QUEUED',):
            _log('process_ocr_job', job_id=job_id, error='Job not QUEUED')
            return

        # Mark PROCESSING
        session.execute(
            text("UPDATE ocr_jobs SET status = 'PROCESSING' WHERE id = :jid"),
            {"jid": job_id}
        )
        session.commit()

    # Execute OCR and processing safely
    try:
        image_path = job_row.image_path
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")

        img = Image.open(image_path)
        raw_text = pytesseract.image_to_string(img, config='--psm 6')

        parsed_items = parse_invoice_text(raw_text)

        with task_session() as session:
            # 1. Update job with raw_text
            session.execute(
                text("UPDATE ocr_jobs SET raw_ocr_text = :text WHERE id = :jid"),
                {"text": raw_text, "jid": job_id}
            )

            # 2. Match products and insert line items
            for item in parsed_items:
                product_name = item['product_name']

                # Try to fuzzy match
                match = session.execute(
                    text("""
                        SELECT product_id, similarity(product_name, :search) as sim
                        FROM products
                        WHERE store_id = :sid AND similarity(product_name, :search) > 0.4
                        ORDER BY sim DESC LIMIT 1
                    """),
                    {"search": product_name, "sid": job_row.store_id}
                ).fetchone()

                matched_id = match.product_id if match else None
                confidence = float(match.sim) if match else 0.0

                item_id = str(uuid.uuid4())
                session.execute(
                    text("""
                        INSERT INTO ocr_job_items
                        (id, job_id, raw_text, matched_product_id, confidence, quantity, unit_price, is_confirmed)
                        VALUES (:id, :jid, :rtext, :mid, :conf, :qty, :price, FALSE)
                    """),
                    {
                        "id": item_id,
                        "jid": job_id,
                        "rtext": item['raw_text'][:256],
                        "mid": matched_id,
                        "conf": confidence,
                        "qty": item['quantity'],
                        "price": item['unit_price']
                    }
                )

            # 3. Mark job REVIEW
            session.execute(
                text("UPDATE ocr_jobs SET status = 'REVIEW' WHERE id = :jid"),
                {"jid": job_id}
            )
            session.commit()

        _log('process_ocr_job', job_id=job_id, status='completed', items=len(parsed_items))

    except Exception as e:
        logger.exception("OCR job failed")
        with task_session() as session:
            session.execute(
                text("UPDATE ocr_jobs SET status = 'FAILED', error_message = :err WHERE id = :jid"),
                {"err": str(e), "jid": job_id}
            )
            session.commit()
