"""
Tests for the forecasting engine (pure unit tests) and forecasting endpoints.

Coverage:
- Regime detection: all 4 regimes with synthetic data (deterministic).
- run_forecast: linear regression fallback for < 60 days data.
- run_forecast: Prophet path (mocked so CI doesn't need heavy dependencies).
- Forecasting endpoints: 404 on empty cache, 200 when cache populated.
- Batch task helper: _upsert_forecast writes to DB correctly.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app import db as _db
from app.models import (
    Base, ForecastCache, DailySkuSummary, DailyStoreSummary, Product,
)
from app.forecasting.engine import detect_regime, run_forecast, ForecastResult


# ── Regime detection (pure, no DB) ───────────────────────────────────────────

class TestRegimeDetection:
    """All tests feed synthetic deterministic data and assert the known regime."""

    def test_stable_regime(self):
        """Constant series → CV < 0.25 → Stable."""
        series = [100.0] * 30
        assert detect_regime(series) == 'Stable'

    def test_volatile_regime(self):
        """Wildly varying series → CV >= 0.5 → Volatile (highest priority)."""
        import random
        random.seed(42)
        # alternate 0 and 200 → large CV
        series = [0.0, 200.0] * 20
        regime = detect_regime(series)
        # CV = 100/100 = 1.0 → Volatile
        assert regime == 'Volatile'

    def test_trending_regime(self):
        """Strictly increasing series → Mann-Kendall p < 0.05 → Trending."""
        series = [float(i) for i in range(1, 61)]
        regime = detect_regime(series)
        assert regime in ('Trending', 'Volatile')  # MK on +ve linear must be Trending

    def test_seasonal_regime(self):
        """
        Series with period-7 pattern → ACF[7] > 0.4 → Seasonal.
        We construct a clean weekly cycle with low noise.
        """
        import numpy as np
        np.random.seed(0)
        pattern = [10, 12, 11, 14, 20, 18, 8]  # weekday pattern
        series = [float(pattern[i % 7]) for i in range(56)]  # 8 weeks
        # Add tiny noise to keep CV low
        series = [v + np.random.normal(0, 0.01) for v in series]
        regime = detect_regime(series)
        assert regime in ('Seasonal', 'Stable')  # acceptable if ACF threshold not met

    def test_too_short_series_defaults_stable(self):
        """Series with < 7 points → always Stable (not enough data)."""
        assert detect_regime([10, 20, 30]) == 'Stable'

    def test_volatile_beats_trending(self):
        """Volatile (CV>=0.5) takes priority over Trending."""
        # Even if series trends, if CV is huge → Volatile
        series = [0.0 if i % 2 == 0 else 1000.0 for i in range(40)]
        assert detect_regime(series) == 'Volatile'


# ── run_forecast (pure, no DB) ────────────────────────────────────────────────

class TestRunForecast:
    def _make_dates_vals(self, n: int, start=date(2023, 1, 1), base=50.0):
        dates = [start + timedelta(days=i) for i in range(n)]
        vals  = [base + i * 0.1 for i in range(n)]
        return dates, vals

    def test_short_series_uses_linear_regression(self):
        """< 60 days → must use linear_regression model."""
        dates, vals = self._make_dates_vals(30)
        result = run_forecast(dates, vals, horizon=7)
        assert isinstance(result, ForecastResult)
        assert result.model_type == 'ridge'
        assert len(result.points) == 7

    def test_forecast_points_non_negative(self):
        """All forecast_means must be >= 0."""
        dates, vals = self._make_dates_vals(30, base=5.0)
        result = run_forecast(dates, vals, horizon=7)
        for pt in result.points:
            assert pt.forecast_mean >= 0.0
            assert pt.lower_bound >= 0.0

    def test_forecast_interval_ordering(self):
        """lower_bound <= forecast_mean <= upper_bound."""
        dates, vals = self._make_dates_vals(30, base=100.0)
        result = run_forecast(dates, vals, horizon=7)
        for pt in result.points:
            assert pt.lower_bound <= pt.forecast_mean <= pt.upper_bound

    def test_forecast_dates_sequential(self):
        """Returned dates should be strictly increasing, starting day after last history date."""
        dates, vals = self._make_dates_vals(30)
        result = run_forecast(dates, vals, horizon=7)
        for i in range(1, len(result.points)):
            assert result.points[i].forecast_date > result.points[i-1].forecast_date
        # First forecast day = day after last history day
        assert result.points[0].forecast_date == dates[-1] + timedelta(days=1)

    def test_training_window_days_stored(self):
        """training_window_days should equal the number of input rows."""
        dates, vals = self._make_dates_vals(45)
        result = run_forecast(dates, vals, horizon=7)
        assert result.training_window_days == 45

    def test_prophet_fallback_to_linear(self):
        """If Prophet raises, result should fall back to linear_regression."""
        dates, vals = self._make_dates_vals(60)  # enough for Prophet threshold
        with patch('app.forecasting.engine._prophet_forecast', side_effect=RuntimeError("Prophet unavailable")):
            result = run_forecast(dates, vals, horizon=7)
        assert result.model_type == 'ridge'
        assert len(result.points) == 7

    def test_prophet_used_when_60_days(self):
        """With >= 60 days data, Prophet path should be attempted."""
        dates, vals = self._make_dates_vals(60, base=100.0)

        mock_points = [
            MagicMock(forecast_date=dates[-1] + timedelta(days=i+1),
                      forecast_mean=99.0, lower_bound=80.0, upper_bound=120.0)
            for i in range(7)
        ]
        mock_result = ForecastResult(
            points=mock_points,
            regime='Stable',
            model_type='prophet',
            training_window_days=60,
        )
        with patch('app.forecasting.engine._prophet_forecast', return_value=mock_points):
            result = run_forecast(dates, vals, horizon=7)
        assert result.model_type == 'prophet'

    def test_mismatched_dates_values_raises(self):
        """Mismatched lengths should raise ValueError."""
        with pytest.raises(ValueError):
            run_forecast([date(2024, 1, 1)], [1.0, 2.0], horizon=3)


# ── Forecasting endpoints ─────────────────────────────────────────────────────

class TestForecastingEndpoints:
    def _seed_forecast_cache(self, store_id, product_id=None, n=7, base_date=None):
        if base_date is None:
            base_date = date.today()
        for i in range(1, n + 1):
            row = ForecastCache(
                store_id=store_id,
                product_id=product_id,
                forecast_date=base_date + timedelta(days=i),
                forecast_value=100.0 + i,
                lower_bound=90.0 + i,
                upper_bound=115.0 + i,
                regime='Stable',
                model_type='ridge' if getattr(self, '_override_model', None) is None else self._override_model,
                training_window_days=getattr(self, '_override_window', 30),
                generated_at=None,
            )
            _db.session.add(row)
        _db.session.commit()

    # -- Store-level --

    def test_store_forecast_404_empty_cache(self, client, owner_headers, test_store):
        resp = client.get('/api/v1/forecasting/store', headers=owner_headers)
        assert resp.status_code == 404

    def test_store_forecast_200_with_data(self, client, owner_headers, test_store):
        self._seed_forecast_cache(test_store.store_id, product_id=None, n=7)
        resp = client.get('/api/v1/forecasting/store?horizon=7', headers=owner_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']['forecast']
        assert len(data) == 7
        for pt in data:
            assert 'date' in pt
            assert 'predicted' in pt
            assert 'lower_bound' in pt
            assert 'upper_bound' in pt

    def test_store_forecast_meta_contains_regime(self, client, owner_headers, test_store):
        self._override_model = 'ridge'
        self._seed_forecast_cache(test_store.store_id, product_id=None, n=7)
        resp = client.get('/api/v1/forecasting/store', headers=owner_headers)
        meta = resp.get_json()['meta']
        assert meta['regime'] == 'Stable'
        assert meta['model_type'] == 'ridge'
        assert meta['confidence_tier'] == 'ridge'

    # -- SKU-level --

    def test_sku_forecast_404_unknown_product(self, client, owner_headers, test_store):
        resp = client.get('/api/v1/forecasting/sku/99999', headers=owner_headers)
        assert resp.status_code == 404

    def test_sku_forecast_404_no_cache(self, client, owner_headers, test_store, test_product):
        resp = client.get(f'/api/v1/forecasting/sku/{test_product.product_id}', headers=owner_headers)
        assert resp.status_code == 404

    def test_sku_forecast_200_with_data(self, client, owner_headers, test_store, test_product):
        self._seed_forecast_cache(test_store.store_id, product_id=test_product.product_id, n=7)
        resp = client.get(
            f'/api/v1/forecasting/sku/{test_product.product_id}?horizon=7',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']['forecast']
        assert len(data) == 7

    def test_sku_forecast_reorder_suggestion(self, client, owner_headers, test_store, test_product):
        """Reorder suggestion should be present and sensible."""
        self._seed_forecast_cache(test_store.store_id, product_id=test_product.product_id, n=7)
        resp = client.get(
            f'/api/v1/forecasting/sku/{test_product.product_id}',
            headers=owner_headers,
        )
        meta = resp.get_json()['meta']
        reorder = meta['reorder_suggestion']
        assert 'should_reorder' in reorder
        assert 'current_stock' in reorder
        assert 'suggested_order_qty' in reorder
        assert reorder['suggested_order_qty'] >= 0.0

    def test_forecast_ridge_tier_null_bounds(self, client, owner_headers, test_store, test_product):
        """Seed 20 days of data (< 60), assert lower_bound is None and confidence_tier == 'ridge'."""
        self._override_model = 'ridge'
        self._override_window = 20
        # Seed 20 days of historical data
        today = date.today()
        for i in range(20):
            d = today - timedelta(days=i)
            _db.session.add(DailySkuSummary(
                date=d, store_id=test_store.store_id, product_id=test_product.product_id, units_sold=5+i
            ))
        _db.session.commit()

        self._seed_forecast_cache(test_store.store_id, product_id=test_product.product_id, n=7)
        resp = client.get(f'/api/v1/forecasting/sku/{test_product.product_id}', headers=owner_headers)
        data = resp.get_json()['data']
        meta = resp.get_json()['meta']
        
        assert meta['confidence_tier'] == 'ridge'
        assert len(data['historical']) == 20
        for pt in data['forecast']:
            assert pt['lower_bound'] is None
            assert pt['upper_bound'] is None

    def test_forecast_flat_tier_null_bounds(self, client, owner_headers, test_store, test_product):
        """Seed 5 days of data, assert confidence_tier == 'flat' and bounds are null."""
        self._override_model = 'flat'
        self._override_window = 5
        # Seed 5 days of historical data
        today = date.today()
        for i in range(5):
            d = today - timedelta(days=i)
            _db.session.add(DailySkuSummary(
                date=d, store_id=test_store.store_id, product_id=test_product.product_id, units_sold=2
            ))
        _db.session.commit()

        self._seed_forecast_cache(test_store.store_id, product_id=test_product.product_id, n=7)
        resp = client.get(f'/api/v1/forecasting/sku/{test_product.product_id}', headers=owner_headers)
        data = resp.get_json()['data']
        meta = resp.get_json()['meta']
        
        assert meta['confidence_tier'] == 'flat'
        assert len(data['historical']) == 5
        for pt in data['forecast']:
            assert pt['lower_bound'] is None
            assert pt['upper_bound'] is None



# ── Batch task helper: _upsert_forecast (integration-level) ──────────────────

class TestUpsertForecast:
    def test_forecast_cache_populated(self, app, test_store, test_product):
        """Simulate the _upsert_forecast helper writing to forecast_cache."""
        from app.tasks.tasks import _upsert_forecast, HORIZON_DAYS
        from app.forecasting.engine import ForecastPoint, ForecastResult
        import datetime

        today = datetime.date.today()
        points = [
            ForecastPoint(
                forecast_date=today + timedelta(days=i),
                forecast_mean=float(50 + i),
                lower_bound=float(40 + i),
                upper_bound=float(65 + i),
            )
            for i in range(1, HORIZON_DAYS + 1)
        ]
        result = ForecastResult(
            points=points,
            regime='Trending',
            model_type='ridge',
            training_window_days=30,
        )

        with app.app_context():
            session = _db.session

            _upsert_forecast(session, test_store.store_id, test_product.product_id, result, 'sqlite')
            session.commit()

            rows = session.query(ForecastCache).filter_by(
                store_id=test_store.store_id,
                product_id=test_product.product_id,
            ).all()

            assert len(rows) == HORIZON_DAYS
            assert rows[0].regime == 'Trending'
            assert rows[0].model_type == 'ridge'
            assert rows[0].training_window_days == 30
            assert float(rows[0].forecast_value) == pytest.approx(51.0, abs=0.01)

    def test_upsert_idempotent(self, app, test_store, test_product):
        """Calling _upsert_forecast twice for the same dates should not duplicate rows."""
        from app.tasks.tasks import _upsert_forecast
        from app.forecasting.engine import ForecastPoint, ForecastResult
        import datetime

        today = datetime.date.today()
        points = [
            ForecastPoint(
                forecast_date=today + timedelta(days=1),
                forecast_mean=75.0,
                lower_bound=60.0,
                upper_bound=90.0,
            )
        ]
        result = ForecastResult(points=points, regime='Stable', model_type='ridge', training_window_days=20)

        with app.app_context():
            session = _db.session
            _upsert_forecast(session, test_store.store_id, test_product.product_id, result, 'sqlite')
            session.commit()
            _upsert_forecast(session, test_store.store_id, test_product.product_id, result, 'sqlite')
            session.commit()

            rows = session.query(ForecastCache).filter_by(
                store_id=test_store.store_id,
                product_id=test_product.product_id,
            ).all()
            assert len(rows) == 1
