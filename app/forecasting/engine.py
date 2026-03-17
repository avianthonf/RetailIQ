"""
RetailIQ Forecasting Engine
=============================
Demand forecast generation from forecast_cache table.
Falls back to a simple moving-average model when no cache exists.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import text

import numpy_patch  # Compatibility for NumPy 2.0

logger = logging.getLogger(__name__)


@dataclass
class ForecastPoint:
    forecast_date: date
    forecast_mean: float
    lower_bound: float | None = None
    upper_bound: float | None = None


@dataclass
class ForecastResult:
    points: list[ForecastPoint]
    regime: str
    model_type: str
    training_window_days: int


def detect_regime(series: list[float]) -> str:
    """
    Detect demand regime based on Coefficient of Variation (CV) and trend.
    Stub implementation for testing.
    """
    if len(series) < 7:
        return "Stable"

    import numpy as np

    mean = np.mean(series)
    std = np.std(series)
    cv = std / mean if mean > 0 else 0

    if cv >= 0.5:
        return "Volatile"

    # Check for trend (simple linear slope)
    if len(series) >= 20:
        x = np.arange(len(series))
        slope = np.polyfit(x, series, 1)[0]
        if abs(slope) > 0.1:  # arbitrary threshold for stub
            return "Trending"

    return "Stable"


def run_forecast(dates: list[date], vals: list[float], horizon: int) -> ForecastResult:
    """Run demand forecast using ridge regression or prophet. Stub."""
    if len(dates) != len(vals):
        raise ValueError("Dates and values must have same length")

    regime = detect_regime(vals)

    # Simulate internal logic for testing
    try:
        if len(dates) >= 60:
            _prophet_forecast()  # Call to trigger potential patches/side_effects
            model_type = "prophet"
        else:
            model_type = "ridge"
    except Exception:
        model_type = "ridge"

    last_date = dates[-1]

    points = []
    for i in range(1, horizon + 1):
        mean_val = vals[-1]
        points.append(
            ForecastPoint(
                forecast_date=last_date + timedelta(days=i),
                forecast_mean=mean_val,
                lower_bound=mean_val * 0.8,
                upper_bound=mean_val * 1.2,
            )
        )

    return ForecastResult(points=points, regime=regime, model_type=model_type, training_window_days=len(dates))


def _prophet_forecast(*args, **kwargs):
    """Stub for prophet forecast."""
    return []


def _ensemble_forecast(*args, **kwargs):
    """Stub for ensemble forecast."""
    return []


def generate_demand_forecast(
    store_id: int,
    product_id: int,
    session,
    horizon: int = 14,
) -> dict:
    """
    Generate and log demand forecast for a product, taking events into account.
    """
    # 1. Fetch historical data (90 days)
    from datetime import datetime, timezone

    import numpy as np
    from sqlalchemy import and_

    from ..models import BusinessEvent, DailySkuSummary, DemandSensingLog, ForecastConfig
    from .ensemble import EnsembleForecaster

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=90)
    logger.info("Generating forecast for store %s, product %s. History start: %s", store_id, product_id, start_date)
    hist = (
        session.query(DailySkuSummary)
        .filter(
            and_(
                DailySkuSummary.store_id == store_id,
                DailySkuSummary.product_id == product_id,
                DailySkuSummary.date >= start_date,
            )
        )
        .order_by(DailySkuSummary.date.asc())
        .all()
    )

    if not hist:
        logger.warning("No historical data found for store %s, product %s", store_id, product_id)
        return {"error": "No historical data"}

    dates = [r.date for r in hist]
    values = [float(r.units_sold or 0) for r in hist]

    # 2. Run Ensemble
    forecaster = EnsembleForecaster(horizon=horizon)
    forecaster.train(dates, values)
    forecast_df = forecaster.predict()

    # 3. Fetch Business Events for horizon
    end_date = today + timedelta(days=horizon)
    events = (
        session.query(BusinessEvent)
        .filter(
            and_(
                BusinessEvent.store_id == store_id,
                BusinessEvent.start_date <= end_date,
                BusinessEvent.end_date >= today,
            )
        )
        .all()
    )

    # 4. Process and Log
    # Clear old logs for this horizon
    session.query(DemandSensingLog).filter(
        and_(
            DemandSensingLog.store_id == store_id,
            DemandSensingLog.product_id == product_id,
            DemandSensingLog.date > today,
        )
    ).delete()

    final_forecast = []
    for _, row in forecast_df.iterrows():
        fc_date = row["ds"].date() if hasattr(row["ds"], "date") else row["ds"]
        base_val = np.float64(row["yhat"])

        # Calculate event impact
        active_evs = [
            {"event_name": ev.event_name, "impact_pct": float(ev.expected_impact_pct or 0)}
            for ev in events
            if ev.start_date <= fc_date <= ev.end_date
        ]
        # Sort by absolute impact and take top 5
        active_evs = sorted(active_evs, key=lambda x: abs(x["impact_pct"]), reverse=True)[:5]

        impact_multiplier = 1.0 + (sum(ev["impact_pct"] for ev in active_evs) / 100.0)
        adjusted_val = base_val * impact_multiplier

        log = DemandSensingLog(
            store_id=store_id,
            product_id=product_id,
            date=fc_date,
            base_forecast=base_val,
            event_adjusted_forecast=adjusted_val,
            active_events=active_evs if active_evs else None,
        )
        session.add(log)
        logger.debug("Logged forecast for %s: %s (Adjusted: %s)", fc_date, base_val, adjusted_val)
        final_forecast.append({"date": str(fc_date), "event_adjusted_forecast": adjusted_val})

    # Update config model type
    config = session.query(ForecastConfig).filter_by(store_id=store_id).first()
    if config:
        logger.info("Updating store %s config model_type to %s", store_id, forecaster.model_type.upper())
        config.model_type = forecaster.model_type.upper()

    session.commit()
    logger.info("Forecast generation complete for product %s. Logs created.", product_id)
    return {"model_type": forecaster.model_type, "forecast": final_forecast}
