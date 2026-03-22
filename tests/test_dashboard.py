"""
Tests for dashboard endpoints.

Coverage:
- /overview: KPIs from daily_store_summary, inventory, POs, loyalty, online orders
- /alerts: real alerts from the alerts table, priority ordering
- /live-signals: market_signals table query
- /forecasts/stores: forecast_cache data
- /incidents/active: CRITICAL/HIGH alerts surfaced as incidents
- /alerts/feed: paginated alert feed
- /test: smoke test for the test route
- Empty-data scenarios: all endpoints return sensible defaults with no data
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app import db as _db
from app.models import (
    Alert,
    DailyStoreSummary,
    ForecastCache,
    Product,
    Store,
)
from app.models.missing_models import MarketSignal

# ── Helpers ───────────────────────────────────────────────────────────────────


def _seed_store_summary(store_id, target_date, revenue=1000.0, profit=200.0):
    """Insert a single daily_store_summary row."""
    row = DailyStoreSummary(
        date=target_date,
        store_id=store_id,
        revenue=revenue,
        profit=profit,
        transaction_count=10,
        avg_basket=revenue / 10,
        units_sold=20,
    )
    _db.session.add(row)
    _db.session.commit()


def _seed_alert(
    store_id, alert_type="LOW_STOCK", priority="HIGH", message="Test alert", product_name=None, resolved=False
):
    """Insert a single alert row."""
    alert = Alert(
        store_id=store_id,
        alert_type=alert_type,
        priority=priority,
        message=message,
        product_name=product_name,
        resolved_at=datetime.now(timezone.utc) if resolved else None,
    )
    _db.session.add(alert)
    _db.session.commit()
    return alert


def _seed_forecast(store_id, start_date, n_days=5, base_value=1000.0):
    """Insert forecast_cache rows."""
    for i in range(n_days):
        row = ForecastCache(
            store_id=store_id,
            product_id=None,
            forecast_date=start_date + timedelta(days=i),
            forecast_value=base_value + i * 100,
            lower_bound=(base_value + i * 100) * 0.85,
            upper_bound=(base_value + i * 100) * 1.15,
            model_type="PROPHET",
            training_window_days=90,
        )
        _db.session.add(row)
    _db.session.commit()


def _seed_market_signal(signal_type="PRICE_SPIKE", value=15.0, region="NORTH"):
    """Insert a market_signals row."""
    sig = MarketSignal(
        signal_type=signal_type,
        value=value,
        region_code=region,
        confidence=0.85,
        timestamp=datetime.now(timezone.utc),
    )
    _db.session.add(sig)
    _db.session.commit()
    return sig


def _seed_low_stock_product(store_id, name="Low Stock Item", stock=5.0, reorder=20.0):
    """Insert a product that is below reorder level."""
    p = Product(
        store_id=store_id,
        name=name,
        selling_price=100.0,
        cost_price=60.0,
        current_stock=stock,
        reorder_level=reorder,
        is_active=True,
    )
    _db.session.add(p)
    _db.session.commit()
    return p


# ── /test ─────────────────────────────────────────────────────────────────────


class TestDashboardTest:
    def test_smoke(self, client):
        resp = client.get("/api/v1/dashboard/test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Dashboard blueprint is working!" in data["message"]
        assert "/api/v1/dashboard/overview" in data["routes"]


# ── /overview ─────────────────────────────────────────────────────────────────


class TestDashboardOverview:
    def test_empty_store(self, client, owner_headers, test_store):
        """Overview with no data returns zeros."""
        resp = client.get("/api/v1/dashboard/overview", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["sales"] == 0
        assert data["gross_margin"] == 0.0
        assert "last_updated" in data

    def test_with_revenue_data(self, client, owner_headers, test_store):
        """Overview returns correct sales and margin from daily_store_summary."""
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)
        _seed_store_summary(test_store.store_id, today, revenue=5000.0, profit=2000.0)
        _seed_store_summary(test_store.store_id, yesterday, revenue=4000.0, profit=1600.0)

        resp = client.get("/api/v1/dashboard/overview", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["sales"] == 5000.0
        assert data["gross_margin"] == 40.0  # 2000/5000 * 100
        assert "+25.0%" in data["sales_delta"]  # (5000-4000)/4000 * 100

    def test_inventory_at_risk(self, client, owner_headers, test_store):
        """Overview reports products below reorder level."""
        _seed_low_stock_product(test_store.store_id, "Item A", stock=5, reorder=20)
        _seed_low_stock_product(test_store.store_id, "Item B", stock=0, reorder=10)

        resp = client.get("/api/v1/dashboard/overview", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["inventory_at_risk"] >= 2

    def test_requires_auth(self, client):
        """Overview requires authentication."""
        resp = client.get("/api/v1/dashboard/overview")
        assert resp.status_code in (401, 403)

    def test_sparklines_have_correct_shape(self, client, owner_headers, test_store):
        """Non-time-series KPIs return empty sparkline points arrays."""
        resp = client.get("/api/v1/dashboard/overview", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        # inventory_at_risk, outstanding_pos, loyalty, online all have empty points
        for key in (
            "inventory_at_risk_sparkline",
            "outstanding_pos_sparkline",
            "loyalty_redemptions_sparkline",
            "online_orders_sparkline",
        ):
            assert key in data
            assert data[key]["points"] == []
        # sales and gross_margin sparklines should have the metric name
        assert data["sales_sparkline"]["metric"] == "sales"
        assert data["gross_margin_sparkline"]["metric"] == "gross_margin"

    def test_delta_strings_present(self, client, owner_headers, test_store):
        """Overview includes delta strings for all KPIs."""
        resp = client.get("/api/v1/dashboard/overview", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        for key in (
            "sales_delta",
            "gross_margin_delta",
            "inventory_at_risk_delta",
            "outstanding_pos_delta",
            "loyalty_redemptions_delta",
            "online_orders_delta",
        ):
            assert key in data
            assert isinstance(data[key], str)


# ── /alerts ───────────────────────────────────────────────────────────────────


class TestDashboardAlerts:
    def test_empty_alerts(self, client, owner_headers, test_store):
        """Alerts with no data returns empty list."""
        resp = client.get("/api/v1/dashboard/alerts", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["alerts"] == []
        assert data["has_more"] is False

    def test_returns_unresolved_alerts(self, client, owner_headers, test_store):
        """Alerts endpoint returns unresolved alerts."""
        _seed_alert(test_store.store_id, "LOW_STOCK", "HIGH", "Rice is low", "Rice")
        _seed_alert(test_store.store_id, "SYSTEM", "LOW", "Minor issue")
        _seed_alert(test_store.store_id, "RESOLVED", "MEDIUM", "Fixed", resolved=True)

        resp = client.get("/api/v1/dashboard/alerts", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        alerts = data["alerts"]
        assert len(alerts) == 2  # resolved one is excluded
        assert alerts[0]["severity"] == "high"  # HIGH priority first

    def test_alert_structure(self, client, owner_headers, test_store):
        """Each alert has required fields."""
        _seed_alert(test_store.store_id, "LOW_STOCK", "CRITICAL", "Out of stock", "Flour")

        resp = client.get("/api/v1/dashboard/alerts", headers=owner_headers)
        body = resp.get_json()
        data = body.get("data", body)
        alert = data["alerts"][0]
        required_keys = {
            "id",
            "type",
            "severity",
            "title",
            "message",
            "timestamp",
            "source",
            "acknowledged",
            "resolved",
        }
        assert required_keys.issubset(alert.keys())

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard/alerts")
        assert resp.status_code in (401, 403)


# ── /live-signals ─────────────────────────────────────────────────────────────


class TestDashboardLiveSignals:
    def test_empty_signals(self, client, owner_headers, test_store):
        """Live signals with no data returns empty list."""
        resp = client.get("/api/v1/dashboard/live-signals", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["signals"] == []
        assert "last_updated" in data

    def test_returns_signals(self, client, owner_headers, test_store):
        """Live signals returns data from market_signals table."""
        _seed_market_signal("PRICE_SPIKE", 15.0, "NORTH")
        _seed_market_signal("DEMAND_DROP", -8.0, "SOUTH")

        resp = client.get("/api/v1/dashboard/live-signals", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["signals"]) == 2

    def test_signal_structure(self, client, owner_headers, test_store):
        """Each signal has required fields."""
        _seed_market_signal()

        resp = client.get("/api/v1/dashboard/live-signals", headers=owner_headers)
        body = resp.get_json()
        data = body.get("data", body)
        sig = data["signals"][0]
        required_keys = {"id", "sku", "product_name", "delta", "region", "insight", "recommendation", "timestamp"}
        assert required_keys.issubset(sig.keys())

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard/live-signals")
        assert resp.status_code in (401, 403)


# ── /forecasts/stores ─────────────────────────────────────────────────────────


class TestDashboardForecasts:
    def test_empty_forecasts(self, client, owner_headers, test_store):
        """Forecasts with no data returns empty forecast list."""
        resp = client.get("/api/v1/dashboard/forecasts/stores", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert isinstance(data["forecasts"], list)
        assert len(data["forecasts"]) == 1
        assert data["forecasts"][0]["forecast"] == []
        assert data["forecasts"][0]["total_predicted"] == 0

    def test_returns_forecast_data(self, client, owner_headers, test_store):
        """Forecasts endpoint returns data from forecast_cache."""
        today = datetime.now(timezone.utc).date()
        _seed_forecast(test_store.store_id, today, n_days=5, base_value=1000.0)

        resp = client.get("/api/v1/dashboard/forecasts/stores", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["forecasts"]) == 1
        assert len(data["forecasts"][0]["forecast"]) == 5
        assert data["forecasts"][0]["total_predicted"] > 0
        assert data["forecasts"][0]["store_name"] == test_store.store_name

    def test_forecast_point_structure(self, client, owner_headers, test_store):
        """Each forecast point has date, predicted_sales, confidence."""
        today = datetime.now(timezone.utc).date()
        _seed_forecast(test_store.store_id, today, n_days=1)

        resp = client.get("/api/v1/dashboard/forecasts/stores", headers=owner_headers)
        body = resp.get_json()
        data = body.get("data", body)
        point = data["forecasts"][0]["forecast"][0]
        assert "date" in point
        assert "predicted_sales" in point
        assert "confidence" in point

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard/forecasts/stores")
        assert resp.status_code in (401, 403)


# ── /incidents/active ─────────────────────────────────────────────────────────


class TestDashboardIncidents:
    def test_empty_incidents(self, client, owner_headers, test_store):
        """No incidents when no CRITICAL/HIGH alerts exist."""
        resp = client.get("/api/v1/dashboard/incidents/active", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["incidents"] == []

    def test_returns_critical_alerts_as_incidents(self, client, owner_headers, test_store):
        """CRITICAL and HIGH unresolved alerts are surfaced as incidents."""
        _seed_alert(test_store.store_id, "STOCKOUT", "CRITICAL", "Complete stockout")
        _seed_alert(test_store.store_id, "PAYMENT_FAIL", "HIGH", "Payment gateway down")
        _seed_alert(test_store.store_id, "MINOR", "LOW", "Minor cosmetic issue")

        resp = client.get("/api/v1/dashboard/incidents/active", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["incidents"]) == 2  # LOW is excluded

    def test_incident_structure(self, client, owner_headers, test_store):
        """Each incident has required fields."""
        _seed_alert(test_store.store_id, "STOCKOUT", "CRITICAL", "Critical stockout")

        resp = client.get("/api/v1/dashboard/incidents/active", headers=owner_headers)
        body = resp.get_json()
        data = body.get("data", body)
        incident = data["incidents"][0]
        required_keys = {
            "id",
            "title",
            "description",
            "severity",
            "status",
            "impacted_services",
            "created_at",
            "updated_at",
            "estimated_resolution",
        }
        assert required_keys.issubset(incident.keys())

    def test_resolved_not_shown(self, client, owner_headers, test_store):
        """Resolved alerts are not shown as incidents."""
        _seed_alert(test_store.store_id, "STOCKOUT", "CRITICAL", "Fixed now", resolved=True)

        resp = client.get("/api/v1/dashboard/incidents/active", headers=owner_headers)
        body = resp.get_json()
        data = body.get("data", body)
        assert data["incidents"] == []

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard/incidents/active")
        assert resp.status_code in (401, 403)


# ── /alerts/feed ──────────────────────────────────────────────────────────────


class TestDashboardAlertsFeed:
    def test_empty_feed(self, client, owner_headers, test_store):
        """Alert feed with no data returns empty list."""
        resp = client.get("/api/v1/dashboard/alerts/feed", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["alerts"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_pagination(self, client, owner_headers, test_store):
        """Alert feed respects limit parameter."""
        for i in range(5):
            _seed_alert(test_store.store_id, f"TYPE_{i}", "MEDIUM", f"Alert {i}")

        resp = client.get("/api/v1/dashboard/alerts/feed?limit=2", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["alerts"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    def test_offset_pagination(self, client, owner_headers, test_store):
        """Alert feed supports offset-based pagination."""
        for i in range(3):
            _seed_alert(test_store.store_id, f"TYPE_{i}", "MEDIUM", f"Alert {i}")

        resp = client.get("/api/v1/dashboard/alerts/feed?limit=2&offset=2", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["alerts"]) == 1
        assert data["has_more"] is False

    def test_invalid_limit_defaults(self, client, owner_headers, test_store):
        """Invalid limit parameter falls back to default 20."""
        for i in range(3):
            _seed_alert(test_store.store_id, f"TYPE_{i}", "MEDIUM", f"Alert {i}")

        resp = client.get("/api/v1/dashboard/alerts/feed?limit=abc", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["alerts"]) == 3  # all returned (fewer than default 20)

    def test_limit_capped_at_100(self, client, owner_headers, test_store):
        """Limit parameter is capped at 100."""
        _seed_alert(test_store.store_id, "TYPE", "HIGH", "Alert")

        resp = client.get("/api/v1/dashboard/alerts/feed?limit=999", headers=owner_headers)
        assert resp.status_code == 200
        # should not crash, limit silently capped

    def test_negative_offset_clamped(self, client, owner_headers, test_store):
        """Negative offset is clamped to 0."""
        _seed_alert(test_store.store_id, "TYPE", "HIGH", "Alert")

        resp = client.get("/api/v1/dashboard/alerts/feed?offset=-5", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert len(data["alerts"]) == 1

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/dashboard/alerts/feed")
        assert resp.status_code in (401, 403)


class TestDashboardForecastAccuracy:
    def test_accuracy_computed_from_bounds(self, client, owner_headers, test_store):
        """Accuracy is dynamically computed from forecast confidence bounds."""
        today = datetime.now(timezone.utc).date()
        _seed_forecast(test_store.store_id, today, n_days=3, base_value=1000.0)

        resp = client.get("/api/v1/dashboard/forecasts/stores", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        store_data = data["forecasts"][0]
        # accuracy should be present and numeric
        assert store_data["accuracy"] is not None
        assert 0 < store_data["accuracy"] <= 1.0

    def test_accuracy_none_when_no_forecasts(self, client, owner_headers, test_store):
        """Accuracy is None when there are no forecast data points."""
        resp = client.get("/api/v1/dashboard/forecasts/stores", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["forecasts"][0]["accuracy"] is None


# ── /ops/maintenance ──────────────────────────────────────────────────────────


class TestOpsMaintenance:
    def test_returns_empty_schedule(self, client):
        """Maintenance endpoint returns empty schedule with healthy status."""
        resp = client.get("/api/v1/ops/maintenance")
        assert resp.status_code == 200
        body = resp.get_json()
        data = body.get("data", body)
        assert data["scheduled_maintenance"] == []
        assert data["ongoing_incidents"] == []
        assert data["system_status"] == "healthy"
        assert "checked_at" in data
