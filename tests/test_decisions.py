from datetime import date, timedelta

import pytest

from app.decisions.engine import build_context, evaluate_rules
from app.decisions.helpers import get_zero_filled_history
from app.decisions.rules import high_margin_opportunity, reorder_alert, revenue_drop, safety_stock_reorder, slow_mover


# --- Helper / Math Tests ---
def test_zero_filled_history():
    today = date(2023, 10, 31)
    raw = [
        {"date": date(2023, 10, 20), "units_sold": 5},
        {"date": date(2023, 10, 25), "units_sold": 10},
    ] # Gap between 20th and 25th, and up to 30th

    # 30 day sequence from 10/01 to 10/30 (excluding today 10/31)
    history = get_zero_filled_history(raw, today, window=30, metric="units_sold")
    assert len(history) == 30
    assert history[19] == 5.0  # 10/20 is index 19 (0-indexed starting 10/01)
    assert history[24] == 10.0
    assert sum(history) == 15.0

# --- Rule Logic Tests ---
def test_reorder_alert_suppressed_volatile():
    ctx = {
        "product_id": 1,
        "current_stock": 10.0,
        "lead_time_days": 3,
        "forecast_demand_7d": 15.0, # > current_stock
        "regime": "Volatile",
        "units_sold_30d": [5.0]*30, # enough history
    }
    # Should be None because Volatile suppresses it
    res = reorder_alert(ctx)
    assert res is None

def test_reorder_alert_not_enough_history():
    ctx = {
        "product_id": 1,
        "current_stock": 10.0, "lead_time_days": 3, "forecast_demand_7d": 15.0,
        "regime": "Stable",
        "units_sold_30d": [5.0]*10, # < 14 days
    }
    # Capped confidence 0.5 and skip reorder formula
    res = reorder_alert(ctx)
    assert res is None

def test_reorder_alert_success():
    ctx = {
        "product_id": 1, "current_stock": 5.0, "lead_time_days": 4,
        "forecast_demand_7d": 10.0, "regime": "Stable",
        "units_sold_30d": [10.0]*15 + [0.0]*15 # sigma will be > 0. Stddev of half 10s half 0s is ~5.08
    }
    res = reorder_alert(ctx)
    assert res is not None
    assert res["rule_name"] == "reorder_alert"
    assert res["priority"] == 4
    num = res["numerical_reasoning"]
    assert num["result"] > 0 # Q > 0

def test_safety_stock_reorder():
    ctx = {
        "product_id": 2,
        "current_stock": 5.0,
        "reorder_level": 10.0
    }
    res = safety_stock_reorder(ctx)
    assert res is not None
    assert res["priority"] == 5
    assert res["time_sensitive"] is True

def test_safety_stock_reorder_skip():
    ctx = {
        "product_id": 2,
        "current_stock": 15.0,
        "reorder_level": 10.0
    }
    assert safety_stock_reorder(ctx) is None

def test_slow_mover():
    ctx = {"product_id": 3, "units_sold_30d": [0.0]*30, "current_stock": 50.0}
    res = slow_mover(ctx)
    assert res is not None
    assert res["rule_name"] == "slow_mover"
    assert res["priority"] == 2

def test_slow_mover_with_sales():
    ctx = {"product_id": 3, "units_sold_30d": [0.0]*29 + [1.0], "current_stock": 50.0}
    assert slow_mover(ctx) is None

def test_revenue_drop():
    ctx = {"product_id": None, "store_revenue_today": 50.0, "store_revenue_7d_ma": 100.0}
    # 50 < 0.7 * 100
    res = revenue_drop(ctx)
    assert res is not None
    assert res["rule_name"] == "revenue_drop"
    assert res["priority"] == 3

def test_high_margin_opportunity():
    ctx = {"product_id": 4, "margin_pct": 35.0, "in_top_20_pct": True}
    res = high_margin_opportunity(ctx)
    assert res is not None
    assert res["priority"] == 1

def test_engine_dedup_and_sort():
    mock_rules = [
        {"rule_name": "A", "product_id": 1, "priority": 1, "confidence": 0.5, "time_sensitive": False},
        {"rule_name": "A", "product_id": 1, "priority": 1, "confidence": 0.9, "time_sensitive": False}, # Dedup wins
        {"rule_name": "B", "product_id": 2, "priority": 5, "confidence": 0.8, "time_sensitive": True},  # Highest priority
    ]
    # In engine, if identical rule/product, take highest confidence. Sort by time_sensitive, priority, confidence
    # (assuming we import a testable engine deduction function)
    from app.decisions.engine import _dedup_and_sort
    final = _dedup_and_sort(mock_rules)
    assert len(final) == 2
    assert final[0]["rule_name"] == "B" # Time sensitive
    assert final[1]["rule_name"] == "A"
    assert final[1]["confidence"] == 0.9
