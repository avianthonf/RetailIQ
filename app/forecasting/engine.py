"""
RetailIQ Forecasting Engine
============================
Produces daily unit-sales forecasts for a single SKU given its history.

Decision tree:
  ≥ 60 days data → Multi-model Ensemble (Prophet + XGBoost + LSTM)
  < 60 days data → Linear regression fallback

Regime detection (applied before storing):
  Stable:   rolling CV (std/mean) < 0.25
  Trending: Mann-Kendall p < 0.05 (scipy)
  Seasonal: ACF spike at lag 7 > 0.4 (statsmodels)
  Volatile: rolling CV >= 0.5

All public functions are pure (no DB side-effects) and therefore testable
without a database.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import NamedTuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────


class ForecastPoint(NamedTuple):
    forecast_date: date
    forecast_mean: float
    lower_bound: float
    upper_bound: float
    base_forecast: float = 0.0


class ForecastResult(NamedTuple):
    points: list[ForecastPoint]
    regime: str  # Stable | Trending | Seasonal | Volatile
    model_type: str  # ensemble | prophet | linear_regression
    training_window_days: int


# ── Regime detection ──────────────────────────────────────────────────────────


def detect_regime(series: list[float]) -> str:
    """
    Classify a univariate daily sales series into one of:
        Stable | Trending | Seasonal | Volatile
    Priority: Volatile > Trending > Seasonal > Stable
    """
    if len(series) < 7:
        return "Stable"

    arr = np.array(series, dtype=float)
    mean = arr.mean()

    # Coefficient of variation
    cv = arr.std() / mean if mean > 0 else 0.0

    if cv >= 0.5:
        return "Volatile"

    # Mann-Kendall trend test
    try:
        from scipy.stats import kendalltau

        n = len(arr)
        tau, p_value = kendalltau(np.arange(n), arr)
        if p_value < 0.05:
            return "Trending"
    except Exception:
        pass

    # ACF at lag 7
    try:
        from statsmodels.tsa.stattools import acf

        if len(arr) >= 14:
            acf_vals = acf(arr, nlags=7, fft=True)
            if abs(acf_vals[7]) > 0.4:
                return "Seasonal"
    except Exception:
        pass

    if cv < 0.25:
        return "Stable"

    return "Stable"


# ── Linear regression fallback ────────────────────────────────────────────────


def _linear_regression_forecast(
    history: pd.DataFrame,
    horizon: int,
    interval_width: float = 0.80,
) -> tuple[list[ForecastPoint], str]:
    """
    Features: day_of_week (one-hot), days_since_start, lag_7, lag_14.
    Target: units_sold.
    Returns forecast points with symmetric PI based on residual std.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import OneHotEncoder

    df = history.copy().sort_values("ds")
    df["days_since_start"] = (df["ds"] - df["ds"].min()).dt.days
    df["lag_7"] = df["y"].shift(7)
    df["lag_14"] = df["y"].shift(14)
    df["dow"] = df["ds"].dt.dayofweek  # 0=Mon

    df_train = df.dropna(subset=["lag_7", "lag_14"])
    if df_train.empty:
        # Fallback: return mean
        mean_val = max(0.0, float(df["y"].mean()))
        return _flat_forecast(history, horizon, mean_val, interval_width), "flat"

    X = df_train[["dow", "days_since_start", "lag_7", "lag_14"]].values
    y = df_train["y"].values

    ct = ColumnTransformer(
        [
            ("dow_enc", OneHotEncoder(sparse_output=False, categories=[list(range(7))]), [0]),
        ],
        remainder="passthrough",
    )
    model = Pipeline([("ct", ct), ("ridge", Ridge(alpha=1.0))])
    model.fit(X, y)

    residuals = y - model.predict(X)
    sigma = float(np.std(residuals))
    from scipy.stats import norm

    z = norm.ppf(0.5 + interval_width / 2)

    # Build inference
    last_date = df["ds"].max().date()
    last_y = list(df["y"].values)
    last_days = int(df["days_since_start"].max())
    points = []
    for i in range(1, horizon + 1):
        fc_date = last_date + timedelta(days=i)
        dow_val = fc_date.weekday()
        days_val = last_days + i
        lag7_val = last_y[-7] if len(last_y) >= 7 else (last_y[0] if last_y else 0)
        lag14_val = last_y[-14] if len(last_y) >= 14 else (last_y[0] if last_y else 0)

        x_row = np.array([[dow_val, days_val, lag7_val, lag14_val]])
        pred = float(model.predict(x_row)[0])
        pred = max(0.0, pred)
        last_y.append(pred)

        points.append(
            ForecastPoint(
                forecast_date=fc_date,
                forecast_mean=round(pred, 3),
                lower_bound=round(max(0.0, pred - z * sigma), 3),
                upper_bound=round(pred + z * sigma, 3),
                base_forecast=round(pred, 3),
            )
        )
    return points, "ridge"


def _flat_forecast(history: pd.DataFrame, horizon: int, value: float, interval_width: float) -> list[ForecastPoint]:
    from scipy.stats import norm

    std = float(history["y"].std()) if len(history) > 1 else value * 0.2
    z = norm.ppf(0.5 + interval_width / 2)
    last_date = history["ds"].max().date()
    return [
        ForecastPoint(
            forecast_date=last_date + timedelta(days=i),
            forecast_mean=round(value, 3),
            lower_bound=round(max(0.0, value - z * std), 3),
            upper_bound=round(value + z * std, 3),
            base_forecast=round(value, 3),
        )
        for i in range(1, horizon + 1)
    ]


# ── Prophet forecast ──────────────────────────────────────────────────────────


def _prophet_forecast(
    history: pd.DataFrame,
    horizon: int,
    interval_width: float = 0.80,
    events: list[dict] = None,
) -> list[ForecastPoint]:
    """
    Runs Prophet with the specified config. On any error raises so caller
    can fall back to linear regression.
    """
    from prophet import Prophet  # type: ignore

    m = Prophet(
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        weekly_seasonality=True,
        yearly_seasonality=True,
        daily_seasonality=False,
        interval_width=interval_width,
    )

    active_regressors = []
    if events:
        filtered_events = []
        for e in events:
            impact = abs(float(e["expected_impact_pct"])) if e.get("expected_impact_pct") is not None else 0.0
            filtered_events.append((impact, e))
        # Top 5 events by impact magnitude
        filtered_events.sort(key=lambda x: x[0], reverse=True)
        top_events = [e[1] for e in filtered_events[:5]]

        for e in top_events:
            event_id_unique = str(e["id"])[:8]
            # Ensure unique internal column name even if prefixes collide
            idx = 1
            col_name = f"event_{event_id_unique}"
            while col_name in [r[0] for r in active_regressors]:
                col_name = f"event_{event_id_unique}_{idx}"
                idx += 1

            active_regressors.append((col_name, e))

            # Add binary column to history
            history[col_name] = history["ds"].apply(
                lambda d: 1.0 if e["start_date"] <= d.date() <= e["end_date"] else 0.0
            )

            impact_pct = e.get("expected_impact_pct")
            prior_scale = 10.0 if impact_pct is None else None
            m.add_regressor(col_name, prior_scale=prior_scale)

    m.fit(history[["ds", "y"] + [r[0] for r in active_regressors]])
    future = m.make_future_dataframe(periods=horizon)

    # Populate regressor columns in future dataframe
    for col_name, e in active_regressors:
        future[col_name] = future["ds"].apply(lambda d: 1.0 if e["start_date"] <= d.date() <= e["end_date"] else 0.0)

    forecast = m.predict(future)
    tail = forecast.tail(horizon)

    points = []
    for _, row in tail.iterrows():
        fc_date = row["ds"].date()
        mean = max(0.0, float(row["yhat"]))
        lb = max(0.0, float(row["yhat_lower"]))
        ub = max(0.0, float(row["yhat_upper"]))

        # Determine base forecast
        extra_regressors = float(row.get("extra_regressors_additive", 0.0))
        base_forecast = max(0.0, mean - extra_regressors)

        points.append(
            ForecastPoint(
                forecast_date=fc_date,
                forecast_mean=round(mean, 3),
                lower_bound=round(lb, 3),
                upper_bound=round(ub, 3),
                base_forecast=round(base_forecast, 3),
            )
        )
    return points


# ── Ensemble forecast ─────────────────────────────────────────────────────────


def _ensemble_forecast(
    history: pd.DataFrame,
    horizon: int,
    interval_width: float = 0.80,
) -> list[ForecastPoint]:
    """
    Runs the Multi-model Ensemble (Prophet + XGBoost + LSTM).
    """
    from .ensemble import run_ensemble_forecast

    dates = history["ds"].dt.date.tolist()
    values = history["y"].tolist()

    forecast_df = run_ensemble_forecast(dates, values, horizon=horizon)

    points = []
    for _, row in forecast_df.iterrows():
        points.append(
            ForecastPoint(
                forecast_date=row["ds"].date(),
                forecast_mean=round(float(row["yhat"]), 3),
                lower_bound=round(float(row["yhat_lower"]), 3),
                upper_bound=round(float(row["yhat_upper"]), 3),
                base_forecast=round(float(row["yhat"]), 3),
            )
        )
    return points


# ── Public entry-point ────────────────────────────────────────────────────────

MIN_DAYS_PROPHET = 60


def run_forecast(
    dates: list[date],
    values: list[float],
    horizon: int = 7,
    interval_width: float = 0.80,
    events: list[dict] = None,
) -> ForecastResult:
    """
    Main entry point.

    Args:
        dates:  list of historical dates (sorted ascending).
        values: list of daily units_sold corresponding to `dates`.
        horizon: number of future days to forecast.
        interval_width: prediction interval width (default 0.80).

    Returns ForecastResult with regime, model_type, training_window_days.
    """
    if len(dates) != len(values):
        raise ValueError("dates and values must be the same length")

    regime = detect_regime(values)
    n = len(dates)
    training_window_days = n

    history = pd.DataFrame({"ds": pd.to_datetime(dates), "y": [float(v) for v in values]})
    # Data Cleaning: ensure unique dates, sorted order, and remove time components
    history["ds"] = history["ds"].dt.normalize()
    history = history.sort_values("ds").drop_duplicates(subset=["ds"], keep="last")
    history = history.reset_index(drop=True)

    # Try Ensemble if sufficient data (MIN_DAYS_PROPHET used as threshold)
    if n >= MIN_DAYS_PROPHET:
        if events:
            logger.info("Events present; skipping ensemble and using Prophet directly.")
            try:
                points = _prophet_forecast(history, horizon, interval_width, events=events)
                return ForecastResult(
                    points=points,
                    regime=regime,
                    model_type="prophet",
                    training_window_days=training_window_days,
                )
            except Exception as exc2:
                logger.warning("Prophet failed (%s); falling back to linear regression.", exc2)
        else:
            try:
                points = _ensemble_forecast(history, horizon, interval_width)
                return ForecastResult(
                    points=points,
                    regime=regime,
                    model_type="ensemble",
                    training_window_days=training_window_days,
                )
            except Exception as exc:
                print(f"DEBUG: Ensemble failed: {exc}", flush=True)
                logger.warning("Ensemble failed (%s); falling back to Prophet", exc)
                try:
                    points = _prophet_forecast(history, horizon, interval_width, events=events)
                    return ForecastResult(
                        points=points,
                        regime=regime,
                        model_type="prophet",
                        training_window_days=training_window_days,
                    )
                except Exception as exc2:
                    import traceback

                    logger.warning("Prophet failed (%s); falling back to linear regression.", exc2)

    # Linear regression fallback
    try:
        points, m_type = _linear_regression_forecast(history, horizon, interval_width)
    except Exception as exc:
        logger.warning("Linear regression failed (%s); using flat mean", exc)
        mean_val = max(0.0, float(history["y"].mean()))
        points = _flat_forecast(history, horizon, mean_val, interval_width)
        m_type = "flat"

    return ForecastResult(
        points=points,
        regime=regime,
        model_type=m_type,
        training_window_days=training_window_days,
    )


def generate_demand_forecast(store_id: int, product_id: int, session, horizon: int = 14) -> dict:
    """
    Senses demand for a specific product, integrating historical sales and future events.
    Writes the forecast snapshot to demand_sensing_log and returns the JSON payload.
    """
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.models import BusinessEvent, DemandSensingLog

    cutoff_90 = datetime.now(timezone.utc).date() - timedelta(days=90)
    horizon_date = datetime.now(timezone.utc).date() + timedelta(days=horizon)

    # 1. Fetch historical sales
    history = session.execute(
        text("""
            SELECT date, units_sold
            FROM daily_sku_summary
            WHERE store_id = :sid AND product_id = :pid AND date >= :cutoff
            ORDER BY date ASC
        """),
        {"sid": store_id, "pid": product_id, "cutoff": str(cutoff_90)},
    ).fetchall()

    if not history:
        raise ValueError("Insufficient history to forecast")

    dates = [h.date for h in history]
    values = [float(h.units_sold) for h in history]

    # 2. Fetch business events that overlap the period
    events = (
        session.query(BusinessEvent)
        .filter(
            BusinessEvent.store_id == store_id,
            BusinessEvent.end_date >= cutoff_90,
            BusinessEvent.start_date <= horizon_date,
        )
        .all()
    )

    events_list = []
    for e in events:
        events_list.append(
            {
                "id": str(e.id),
                "event_name": e.event_name,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "expected_impact_pct": e.expected_impact_pct,
                "event_type": e.event_type,
            }
        )

    # 3. Run forecast
    result = run_forecast(dates, values, horizon=horizon, interval_width=0.80, events=events_list)

    # Filter active events out to save in the log
    # For a point, an event is active if start <= date <= end
    active_payload_list = []
    for fp in result.points:
        day_events = [e for e in events_list if e["start_date"] <= fp.forecast_date <= e["end_date"]]
        # Sort by absolute expected_impact_pct descending, consistent with regressor selection
        day_events.sort(
            key=lambda e: abs(float(e["expected_impact_pct"])) if e.get("expected_impact_pct") is not None else 0.0,
            reverse=True,
        )
        active_payload = [{"id": e["id"], "event_name": e["event_name"]} for e in day_events[:5]]

        # 4. Save to demand_sensing_log
        log_entry = DemandSensingLog(
            store_id=store_id,
            product_id=product_id,
            date=fp.forecast_date,
            actual_demand=None,
            base_forecast=fp.base_forecast,
            event_adjusted_forecast=fp.forecast_mean,
            active_events=active_payload,
        )
        session.add(log_entry)

        active_payload_list.append(
            {
                "date": fp.forecast_date.isoformat(),
                "base_forecast": fp.base_forecast,
                "event_adjusted_forecast": fp.forecast_mean,
                "active_events": active_payload,
            }
        )

    session.commit()

    return {
        "model_type": result.model_type,
        "regime": result.regime,
        "training_window_days": result.training_window_days,
        "forecast": active_payload_list,
    }
