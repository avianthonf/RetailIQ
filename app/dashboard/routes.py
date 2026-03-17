"""
RetailIQ Dashboard Routes
==========================
Provides aggregated dashboard data for the frontend executive dashboard.
Endpoints are registered at /api/v1/dashboard.
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import text

from app import db
from app.auth.decorators import require_auth, require_role
from app.auth.utils import format_response

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/test")
def test():
    """Simple test route."""
    return jsonify(
        {
            "message": "Dashboard blueprint is working!",
            "routes": [
                "/api/v1/dashboard/test",
                "/api/v1/dashboard/overview",
                "/api/v1/dashboard/alerts",
                "/api/v1/dashboard/live-signals",
            ],
        }
    )


def _store_id():
    """Get current user's store ID from auth context."""
    return g.current_user["store_id"]


@dashboard_bp.route("/overview")
@require_auth
def overview():
    """Get dashboard overview metrics."""
    from datetime import datetime, timedelta, timezone

    # Generate mock sparkline data (last 24 hours)
    sparkline_data = []
    now = datetime.now(timezone.utc)
    for i in range(24):
        hour = now - timedelta(hours=i)
        # Generate realistic looking data
        base_value = 1000
        variation = int((i % 6 - 3) * 100)  # Oscillating pattern
        value = max(100, base_value + variation)
        sparkline_data.append({"timestamp": hour.isoformat(), "value": float(value)})

    sparkline_data.reverse()  # Show oldest to newest

    # Generate different sparklines for each metric
    sales_sparkline = {"metric": "sales", "points": sparkline_data}

    gross_margin_sparkline = {
        "metric": "gross_margin",
        "points": [{"timestamp": p["timestamp"], "value": p["value"] * 0.42} for p in sparkline_data],
    }

    inventory_sparkline = {
        "metric": "inventory_at_risk",
        "points": [{"timestamp": p["timestamp"], "value": float(15 + (i % 10))} for i, p in enumerate(sparkline_data)],
    }

    pos_sparkline = {
        "metric": "outstanding_pos",
        "points": [{"timestamp": p["timestamp"], "value": float(5 + (i % 8))} for i, p in enumerate(sparkline_data)],
    }

    loyalty_sparkline = {
        "metric": "loyalty_redemptions",
        "points": [{"timestamp": p["timestamp"], "value": float(100 + (i % 50))} for i, p in enumerate(sparkline_data)],
    }

    online_orders_sparkline = {
        "metric": "online_orders",
        "points": [{"timestamp": p["timestamp"], "value": float(20 + (i % 30))} for i, p in enumerate(sparkline_data)],
    }

    return format_response(
        data={
            "sales": 15420.50,
            "sales_delta": "+12.5%",
            "sales_sparkline": sales_sparkline,
            "gross_margin": 42.3,
            "gross_margin_delta": "+2.1%",
            "gross_margin_sparkline": gross_margin_sparkline,
            "inventory_at_risk": 23,
            "inventory_at_risk_delta": "+5",
            "inventory_at_risk_sparkline": inventory_sparkline,
            "outstanding_pos": 8,
            "outstanding_pos_delta": "-2",
            "outstanding_pos_sparkline": pos_sparkline,
            "loyalty_redemptions": 342,
            "loyalty_redemptions_delta": "+18.2%",
            "loyalty_redemptions_sparkline": loyalty_sparkline,
            "online_orders": 127,
            "online_orders_delta": "+8.7%",
            "online_orders_sparkline": online_orders_sparkline,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    )


@dashboard_bp.route("/alerts")
@require_auth
def alerts():
    """Get alerts for the dashboard."""
    from datetime import datetime, timezone

    # Mock alerts data
    alerts = [
        {
            "id": "low-stock-001",
            "type": "stockout",
            "severity": "high",
            "title": "Low stock: Premium Rice",
            "message": "SKU SKU-001 has 5 units (reorder at 20)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            "source": "inventory",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "low-stock-002",
            "type": "stockout",
            "severity": "high",
            "title": "Critical stock: Wheat Flour",
            "message": "SKU SKU-002 has 0 units (reorder at 20)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            "source": "inventory",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "low-stock-003",
            "type": "stockout",
            "severity": "medium",
            "title": "Low stock: Cooking Oil",
            "message": "SKU SKU-003 has 8 units (reorder at 10)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "source": "inventory",
            "acknowledged": True,
            "resolved": False,
        },
        {
            "id": "system-001",
            "type": "system",
            "severity": "low",
            "title": "Scheduled maintenance",
            "message": "System maintenance scheduled for tonight at 2 AM",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "source": "system",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "perf-001",
            "type": "performance",
            "severity": "medium",
            "title": "Slow checkout detected",
            "message": "Average checkout time increased by 20% in the last hour",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
            "source": "performance",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "price-001",
            "type": "pricing",
            "severity": "medium",
            "title": "Price drift detected",
            "message": "Competitor price for SKU-045 is 15% lower",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            "source": "pricing",
            "acknowledged": False,
            "resolved": False,
        },
    ]

    return format_response(data={"alerts": alerts, "has_more": False, "next_cursor": None})


@dashboard_bp.route("/live-signals")
@require_auth
def live_signals():
    """Get live market signals."""
    from datetime import datetime, timezone

    # Mock live signals data
    signals = [
        {
            "id": "signal-1",
            "sku": "SKU-001",
            "product_name": "Premium Rice",
            "delta": "+15%",
            "region": "North",
            "insight": "Demand spike detected in North region due to festival season",
            "recommendation": "Increase stock by 20% to meet demand",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "signal-2",
            "sku": "SKU-045",
            "product_name": "Organic Tea",
            "delta": "-8%",
            "region": "South",
            "insight": "Price sensitivity detected - competitor launched promotion",
            "recommendation": "Consider promotional pricing or bundle offers",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        },
        {
            "id": "signal-3",
            "sku": "SKU-123",
            "product_name": "Palm Oil",
            "delta": "+22%",
            "region": "East",
            "insight": "Supply chain disruption expected - wholesale prices rising",
            "recommendation": "Bulk purchase recommended before price hike",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        },
        {
            "id": "signal-4",
            "sku": "SKU-089",
            "product_name": "Sugar",
            "delta": "+5%",
            "region": "West",
            "insight": "Seasonal demand increase - wedding season starting",
            "recommendation": "Monitor competitor pricing - opportunity for premium segment",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
        },
        {
            "id": "signal-5",
            "sku": "SKU-067",
            "product_name": "Lentils",
            "delta": "-12%",
            "region": "Central",
            "insight": "New harvest season - market prices expected to drop further",
            "recommendation": "Delay restocking - better prices expected in 2 weeks",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
        },
    ]

    return format_response(data={"signals": signals, "last_updated": datetime.now(timezone.utc).isoformat()})


@dashboard_bp.route("/forecasts/stores")
@require_auth
def forecasts_stores():
    """Get store-level forecasts."""
    from datetime import datetime, timedelta, timezone

    # Mock forecast data
    forecasts = []
    stores = ["Main Store", "North Branch", "South Branch", "East Branch", "West Branch"]

    for i, store in enumerate(stores):
        forecast_data = []
        for j in range(30):
            date = datetime.now(timezone.utc).date() + timedelta(days=j)
            value = 1000 + (i * 100) + (j * 10) + ((j % 7) * 50)
            forecast_data.append(
                {"date": date.isoformat(), "predicted_sales": float(value), "confidence": 0.85 - (j * 0.01)}
            )

        forecasts.append(
            {
                "store_id": i + 1,
                "store_name": store,
                "forecast": forecast_data,
                "total_predicted": sum(f["predicted_sales"] for f in forecast_data),
                "accuracy": 0.87,
            }
        )

    return format_response(data=forecasts)


@dashboard_bp.route("/incidents/active")
@require_auth
def active_incidents():
    """Get active incidents."""
    from datetime import datetime, timezone

    incidents = [
        {
            "id": "incident-001",
            "title": "Payment Gateway Slowness",
            "description": "UPI payments experiencing 30% delay",
            "severity": "medium",
            "status": "investigating",
            "impacted_services": ["payments", "checkout"],
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(),
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            "estimated_resolution": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
    ]

    return format_response(data=incidents)


@dashboard_bp.route("/alerts/feed")
@require_auth
def alerts_feed():
    """Get alerts feed with pagination."""
    from datetime import datetime, timezone

    limit = int(request.args.get("limit", 20))

    # Use the same alerts as the alerts endpoint
    alerts = [
        {
            "id": "low-stock-001",
            "type": "stockout",
            "severity": "high",
            "title": "Low stock: Premium Rice",
            "message": "SKU SKU-001 has 5 units (reorder at 20)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            "source": "inventory",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "low-stock-002",
            "type": "stockout",
            "severity": "high",
            "title": "Critical stock: Wheat Flour",
            "message": "SKU SKU-002 has 0 units (reorder at 20)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            "source": "inventory",
            "acknowledged": False,
            "resolved": False,
        },
        {
            "id": "low-stock-003",
            "type": "stockout",
            "severity": "medium",
            "title": "Low stock: Cooking Oil",
            "message": "SKU SKU-003 has 8 units (reorder at 10)",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "source": "inventory",
            "acknowledged": True,
            "resolved": False,
        },
    ]

    return format_response(
        data={
            "alerts": alerts[:limit],
            "has_more": len(alerts) > limit,
            "next_cursor": None if len(alerts) <= limit else "next-page-token",
        }
    )
