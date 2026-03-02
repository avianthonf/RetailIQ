"""
Pricing Engine for RetailIQ
============================
Generates margin-optimized pricing suggestions per store using
90-day sales history from daily_sku_summary.
"""
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ── Tuning constants ──────────────────────────────────────────────────────────
MIN_HISTORY_DAYS = 30          # minimum days of history to qualify
ELASTICITY_WINDOW_DAYS = 90    # window for price elasticity proxy calc
LOW_VELOCITY_DAYS = 14         # lookback for zero-velocity check
MARGIN_RAISE_THRESHOLD = 0.15  # < 15% margin → candidate for RAISE
MARGIN_LOWER_THRESHOLD = 0.30  # > 30% margin → candidate for LOWER
ELASTICITY_INELASTIC = -0.3    # proxy > -0.3 → demand inelastic
RAISE_DELTA_PCT = 0.05         # suggest +5% price increase
LOWER_DELTA_PCT = 0.10         # suggest -10% price decrease


def _compute_pearson(xs: list[float], ys: list[float]) -> float | None:
    """Returns Pearson correlation coefficient or None if undetermined."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    denom_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    denom_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return None
    return num / (denom_x * denom_y)


def _has_anomaly_in_14d(session, store_id: int, product_id: int) -> bool:
    """Rough anomaly check: zero sales 14d while store overall had sales."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=LOW_VELOCITY_DAYS)
    row = session.execute(
        text("""
            SELECT COALESCE(SUM(revenue), 0) AS store_rev
            FROM daily_store_summary
            WHERE store_id = :sid
              AND date >= :cutoff
        """),
        {"sid": store_id, "cutoff": str(cutoff)},
    ).fetchone()
    # If the store itself had zero revenue we can't call it an anomaly
    return row and float(row.store_rev or 0) == 0


def generate_price_suggestions(store_id: int, session) -> list[dict]:
    """
    For each qualifying product (>= MIN_HISTORY_DAYS of SKU history):
      - Compute price_elasticity_proxy and margin_pct
      - Emit RAISE suggestion when margin < 15% & demand is inelastic
      - Emit LOWER suggestion when 14-day velocity is zero, no anomaly, margin > 30%

    Returns a list of dicts with keys:
      product_id, product_name, suggested_price, current_price,
      price_change_pct, reason, confidence, suggestion_type
    """
    suggestions: list[dict] = []

    cutoff_90 = datetime.now(timezone.utc).date() - timedelta(days=ELASTICITY_WINDOW_DAYS)
    cutoff_14 = datetime.now(timezone.utc).date() - timedelta(days=LOW_VELOCITY_DAYS)

    # Fetch products with enough history
    products = session.execute(
        text("""
            SELECT
                p.product_id,
                p.name,
                p.selling_price,
                p.cost_price,
                p.store_id,
                COUNT(DISTINCT dss.date) AS history_days
            FROM products p
            JOIN daily_sku_summary dss
              ON dss.product_id = p.product_id
             AND dss.store_id   = p.store_id
            WHERE p.store_id = :sid
              AND p.is_active  = TRUE
              AND p.selling_price IS NOT NULL
              AND p.cost_price    IS NOT NULL
              AND p.selling_price > 0
              AND dss.date >= :cutoff
            GROUP BY p.product_id, p.name, p.selling_price, p.cost_price, p.store_id
            HAVING COUNT(DISTINCT dss.date) >= :min_days
        """),
        {
            "sid": store_id,
            "cutoff": str(cutoff_90),
            "min_days": MIN_HISTORY_DAYS,
        },
    ).fetchall()

    for prod in products:
        selling_price = float(prod.selling_price)
        cost_price = float(prod.cost_price)
        product_id = prod.product_id

        if selling_price <= 0:
            continue

        margin_pct = (selling_price - cost_price) / selling_price

        # ── Price elasticity proxy ────────────────────────────────────────────
        # Get 90-day daily history: (date, avg_selling_price, units_sold)
        history = session.execute(
            text("""
                SELECT date, avg_selling_price, units_sold
                FROM daily_sku_summary
                WHERE store_id  = :sid
                  AND product_id = :pid
                  AND date >= :cutoff
                ORDER BY date ASC
            """),
            {"sid": store_id, "pid": product_id, "cutoff": str(cutoff_90)},
        ).fetchall()

        elasticity_proxy: float | None = None
        if len(history) >= 2:
            prices = [float(r.avg_selling_price or selling_price) for r in history]
            units  = [float(r.units_sold or 0) for r in history]

            # median price for this window
            median_price = statistics.median(prices)

            # Binary: 1 if price > median, 0 otherwise
            above_median_flags = [1.0 if p > median_price else 0.0 for p in prices]

            elasticity_proxy = _compute_pearson(above_median_flags, units)

        # If correlation is undetermined (e.g. constant demand or constant price),
        # treat as perfectly inelastic (proxy = 0.0).  Constant demand regardless
        # of price fluctuations is the textbook definition of perfect inelasticity.
        if elasticity_proxy is None:
            elasticity_proxy = 0.0

        # ── 14-day velocity ───────────────────────────────────────────────────
        vel_row = session.execute(
            text("""
                SELECT COALESCE(SUM(units_sold), 0) AS total_units
                FROM daily_sku_summary
                WHERE store_id  = :sid
                  AND product_id = :pid
                  AND date >= :cutoff
            """),
            {"sid": store_id, "pid": product_id, "cutoff": str(cutoff_14)},
        ).fetchone()
        units_14d = float(vel_row.total_units) if vel_row else 0.0

        # ── Decision logic ────────────────────────────────────────────────────
        suggestion: dict | None = None

        # RAISE: low-margin AND inelastic demand
        if (
            margin_pct < MARGIN_RAISE_THRESHOLD
            and elasticity_proxy > ELASTICITY_INELASTIC
        ):
            new_price = round(selling_price * (1 + RAISE_DELTA_PCT), 2)
            change_pct = round(RAISE_DELTA_PCT * 100, 2)
            suggestion = {
                "product_id": product_id,
                "product_name": prod.name,
                "suggested_price": new_price,
                "current_price": selling_price,
                "price_change_pct": change_pct,
                "reason": (
                    f"Low margin ({margin_pct*100:.1f}%) with inelastic demand "
                    f"(elasticity proxy={elasticity_proxy:.3f}). "
                    "Raising price to improve margin."
                ),
                "confidence": "HIGH" if elasticity_proxy > 0.1 else "MEDIUM",
                "suggestion_type": "RAISE",
            }

        # LOWER: zero velocity AND margin is healthy AND no store-wide anomaly
        elif (
            units_14d == 0
            and margin_pct > MARGIN_LOWER_THRESHOLD
            and not _has_anomaly_in_14d(session, store_id, product_id)
        ):
            new_price = round(selling_price * (1 - LOWER_DELTA_PCT), 2)
            change_pct = round(-LOWER_DELTA_PCT * 100, 2)
            suggestion = {
                "product_id": product_id,
                "product_name": prod.name,
                "suggested_price": new_price,
                "current_price": selling_price,
                "price_change_pct": change_pct,
                "reason": (
                    f"Zero sales in last {LOW_VELOCITY_DAYS} days with healthy margin "
                    f"({margin_pct*100:.1f}%). "
                    "Lowering price to stimulate demand."
                ),
                "confidence": "MEDIUM",
                "suggestion_type": "LOWER",
            }

        if suggestion:
            suggestions.append(suggestion)

    logger.info(
        "generate_price_suggestions store_id=%s produced %d suggestions",
        store_id,
        len(suggestions),
    )
    return suggestions
