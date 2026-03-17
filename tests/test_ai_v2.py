from datetime import datetime, timedelta

import pytest
from flask import json

from app import db
from app.models import DailySkuSummary, Product


def test_forecast_v2(client, owner_headers):
    # Setup mock data for forecasting
    p = Product(name="Test Milk", store_id=1, cost_price=10.0, selling_price=15.0, is_active=True)
    db.session.add(p)
    db.session.commit()

    # Add history (need at least 1 day for flat fallback, 60 for ensemble)
    for i in range(5):
        day = datetime.now() - timedelta(days=i + 1)
        summ = DailySkuSummary(store_id=1, product_id=p.product_id, date=day.date(), units_sold=5.0, revenue=75.0)
        db.session.add(summ)
    db.session.commit()

    resp = client.post(
        "/api/v2/ai/forecast",
        data=json.dumps({"product_id": p.product_id}),
        headers=owner_headers,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True
    assert "forecast" in data["data"]


def test_pricing_optimize_v2(client, owner_headers):
    p = Product(name="Test Bread", store_id=1, cost_price=20.0, selling_price=25.0, is_active=True)
    db.session.add(p)
    db.session.commit()

    # Add some history for pricing
    day = datetime.now() - timedelta(days=1)
    summ = DailySkuSummary(
        store_id=1, product_id=p.product_id, date=day.date(), units_sold=10.0, revenue=250.0, avg_selling_price=25.0
    )
    db.session.add(summ)
    db.session.commit()

    resp = client.post(
        "/api/v2/ai/pricing/optimize",
        data=json.dumps({"product_ids": [p.product_id]}),
        headers=owner_headers,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True
    # results is a list of dicts, check if p.product_id is in any dict
    assert any(str(item["product_id"]) == str(p.product_id) for item in data["data"])


def test_vision_shelf_v2(client, owner_headers):
    resp = client.post(
        "/api/v2/ai/vision/shelf-scan",
        data=json.dumps({"image_url": "http://example.com/shelf.jpg"}),
        headers=owner_headers,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["success"] is True
    assert "analysis" in data["data"]


def test_nlp_query_v2(client, owner_headers):
    resp = client.post(
        "/api/v2/ai/nlp/query",
        data=json.dumps({"query": "What is the demand for milk?"}),
        headers=owner_headers,
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "response" in data


def test_recommend_v2(client, owner_headers):
    resp = client.post(
        "/api/v2/ai/recommend", data=json.dumps({"user_id": 1}), headers=owner_headers, content_type="application/json"
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "recommendations" in data
