"""
RetailIQ Forecasting Engine
============================
Produces daily unit-sales forecasts for a single SKU given its history.

Decision tree:
  ≥ 60 days data → Prophet
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


class ForecastResult(NamedTuple):
    points: list[ForecastPoint]
    regime: str          # Stable | Trending | Seasonal | Volatile
    model_type: str      # prophet | linear_regression
    training_window_days: int


# ── Regime detection ──────────────────────────────────────────────────────────

def detect_regime(series: list[float]) -> str:
    """
    Classify a univariate daily sales series into one of:
        Stable | Trending | Seasonal | Volatile
    Priority: Volatile > Trending > Seasonal > Stable
    """
    if len(series) < 7:
        return 'Stable'

    arr = np.array(series, dtype=float)
    mean = arr.mean()

    # Coefficient of variation
    cv = arr.std() / mean if mean > 0 else 0.0

    if cv >= 0.5:
        return 'Volatile'

    # Mann-Kendall trend test
    try:
        from scipy.stats import kendalltau
        n = len(arr)
        tau, p_value = kendalltau(np.arange(n), arr)
        if p_value < 0.05:
            return 'Trending'
    except Exception:
        pass

    # ACF at lag 7
    try:
        from statsmodels.tsa.stattools import acf
        if len(arr) >= 14:
            acf_vals = acf(arr, nlags=7, fft=True)
            if abs(acf_vals[7]) > 0.4:
                return 'Seasonal'
    except Exception:
        pass

    if cv < 0.25:
        return 'Stable'

    return 'Stable'


# ── Linear regression fallback ────────────────────────────────────────────────

def _linear_regression_forecast(
    history: pd.DataFrame,
    horizon: int,
    interval_width: float = 0.80,
) -> list[ForecastPoint]:
    """
    Features: day_of_week (one-hot), days_since_start, lag_7, lag_14.
    Target: units_sold.
    Returns forecast points with symmetric PI based on residual std.
    """
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.pipeline import make_pipeline
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline

    df = history.copy().sort_values('ds')
    df['days_since_start'] = (df['ds'] - df['ds'].min()).dt.days
    df['lag_7']  = df['y'].shift(7)
    df['lag_14'] = df['y'].shift(14)
    df['dow']    = df['ds'].dt.dayofweek  # 0=Mon

    df_train = df.dropna(subset=['lag_7', 'lag_14'])
    if df_train.empty:
        # Fallback: return mean
        mean_val = max(0.0, float(df['y'].mean()))
        return _flat_forecast(history, horizon, mean_val, interval_width)

    X = df_train[['dow', 'days_since_start', 'lag_7', 'lag_14']].values
    y = df_train['y'].values

    ct = ColumnTransformer([
        ('dow_enc', OneHotEncoder(sparse_output=False, categories=[list(range(7))]), [0]),
    ], remainder='passthrough')
    model = Pipeline([('ct', ct), ('ridge', Ridge(alpha=1.0))])
    model.fit(X, y)

    residuals = y - model.predict(X)
    sigma = float(np.std(residuals))
    from scipy.stats import norm
    z = norm.ppf(0.5 + interval_width / 2)

    # Build inference
    last_date = df['ds'].max().date()
    last_y    = list(df['y'].values)
    last_days = int(df['days_since_start'].max())
    points = []
    for i in range(1, horizon + 1):
        fc_date = last_date + timedelta(days=i)
        dow_val = fc_date.weekday()
        days_val = last_days + i
        lag7_val  = last_y[-7]  if len(last_y) >= 7  else (last_y[0] if last_y else 0)
        lag14_val = last_y[-14] if len(last_y) >= 14 else (last_y[0] if last_y else 0)

        x_row = np.array([[dow_val, days_val, lag7_val, lag14_val]])
        pred = float(model.predict(x_row)[0])
        pred = max(0.0, pred)
        last_y.append(pred)

        points.append(ForecastPoint(
            forecast_date=fc_date,
            forecast_mean=round(pred, 3),
            lower_bound=round(max(0.0, pred - z * sigma), 3),
            upper_bound=round(pred + z * sigma, 3),
        ))
    return points


def _flat_forecast(history: pd.DataFrame, horizon: int, value: float, interval_width: float) -> list[ForecastPoint]:
    from scipy.stats import norm
    std = float(history['y'].std()) if len(history) > 1 else value * 0.2
    z   = norm.ppf(0.5 + interval_width / 2)
    last_date = history['ds'].max().date()
    return [
        ForecastPoint(
            forecast_date=last_date + timedelta(days=i),
            forecast_mean=round(value, 3),
            lower_bound=round(max(0.0, value - z * std), 3),
            upper_bound=round(value + z * std, 3),
        )
        for i in range(1, horizon + 1)
    ]


# ── Prophet forecast ──────────────────────────────────────────────────────────

def _prophet_forecast(
    history: pd.DataFrame,
    horizon: int,
    interval_width: float = 0.80,
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
    m.fit(history[['ds', 'y']])
    future = m.make_future_dataframe(periods=horizon)
    forecast = m.predict(future)
    tail = forecast.tail(horizon)

    points = []
    for _, row in tail.iterrows():
        fc_date = row['ds'].date()
        mean    = max(0.0, float(row['yhat']))
        lb      = max(0.0, float(row['yhat_lower']))
        ub      = max(0.0, float(row['yhat_upper']))
        points.append(ForecastPoint(
            forecast_date=fc_date,
            forecast_mean=round(mean, 3),
            lower_bound=round(lb, 3),
            upper_bound=round(ub, 3),
        ))
    return points


# ── Public entry-point ────────────────────────────────────────────────────────

MIN_DAYS_PROPHET = 60


def run_forecast(
    dates: list[date],
    values: list[float],
    horizon: int = 7,
    interval_width: float = 0.80,
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
    n      = len(dates)
    training_window_days = n

    history = pd.DataFrame({'ds': pd.to_datetime(dates), 'y': [float(v) for v in values]})

    # Try Prophet if sufficient data
    if n >= MIN_DAYS_PROPHET:
        try:
            points = _prophet_forecast(history, horizon, interval_width)
            return ForecastResult(
                points=points,
                regime=regime,
                model_type='prophet',
                training_window_days=training_window_days,
            )
        except Exception as exc:
            logger.warning("Prophet failed (%s); falling back to linear regression", exc)

    # Linear regression fallback
    try:
        points = _linear_regression_forecast(history, horizon, interval_width)
    except Exception as exc:
        logger.warning("Linear regression failed (%s); using flat mean", exc)
        mean_val = max(0.0, float(history['y'].mean()))
        points = _flat_forecast(history, horizon, mean_val, interval_width)

    return ForecastResult(
        points=points,
        regime=regime,
        model_type='linear_regression',
        training_window_days=training_window_days,
    )
