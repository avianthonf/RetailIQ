from unittest.mock import MagicMock, patch

import pytest

from app.nlp.routes import nlp_bp


def test_handle_query_forecast(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="forecast"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_row = MagicMock()
        mock_row.fc = 100.5
        mock_row.reg = "Growth"
        mock_execute.return_value.fetchone.return_value = mock_row

        response = client.post("/api/v1/nlp/", json={"query_text": "forecast"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "forecast"
        assert data["supporting_metrics"]["forecast_7d"] == 100.5
        assert data["supporting_metrics"]["regime"] == "Growth"


def test_handle_query_inventory(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="inventory"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_row = MagicMock()
        mock_row.product_id = 1
        mock_row.name = "Test Product"
        mock_row.current_stock = 10
        mock_row.reorder_level = 20
        mock_row.deficit = 10
        mock_execute.return_value.fetchone.return_value = mock_row

        response = client.post("/api/v1/nlp/", json={"query_text": "inventory"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "inventory"
        assert data["supporting_metrics"]["product_id"] == 1


def test_handle_query_inventory_no_deficit(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="inventory"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_execute.return_value.fetchone.return_value = None

        response = client.post("/api/v1/nlp/", json={"query_text": "inventory"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert "All products are above their reorder levels" in data["detail"]


def test_handle_query_revenue(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="revenue"),
        patch("app.db.session.execute") as mock_execute,
    ):
        import datetime

        mock_execute.return_value.scalar.return_value = datetime.date(2023, 1, 8)

        mock_row1 = MagicMock()
        mock_row1.date = datetime.date(2023, 1, 8)
        mock_row1.revenue = 500.0

        mock_row2 = MagicMock()
        mock_row2.date = datetime.date(2023, 1, 7)
        mock_row2.revenue = 400.0

        mock_execute.return_value.fetchall.return_value = [mock_row1, mock_row2]

        response = client.post("/api/v1/nlp/", json={"query_text": "revenue"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "revenue"
        assert data["supporting_metrics"]["today_revenue"] == 500.0


def test_handle_query_profit(client, owner_headers):
    with patch("app.nlp.routes.resolve_intent", return_value="profit"), patch("app.db.session.execute") as mock_execute:
        mock_row = MagicMock()
        mock_row.avg_margin = 25.5
        mock_row.product_count = 10
        mock_execute.return_value.fetchone.return_value = mock_row

        response = client.post("/api/v1/nlp/", json={"query_text": "profit"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "profit"
        assert data["supporting_metrics"]["avg_margin_pct"] == 25.5


def test_handle_query_top_products(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="top_products"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_row = MagicMock()
        mock_row.product_id = 1
        mock_row.name = "Top Item"
        mock_row.total_rev = 1000.0
        mock_row.total_units = 50
        mock_execute.return_value.fetchall.return_value = [mock_row]

        response = client.post("/api/v1/nlp/", json={"query_text": "top products"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "top_products"
        assert len(data["supporting_metrics"]["top_products"]) == 1


def test_handle_query_loyalty_summary(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="loyalty_summary"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_row = MagicMock()
        mock_row.enrolled = 100
        mock_row.issued = 5000
        mock_row.redeemed = -1000
        mock_execute.return_value.fetchone.return_value = mock_row

        response = client.post("/api/v1/nlp/", json={"query_text": "loyalty"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "loyalty_summary"
        assert data["supporting_metrics"]["points_issued"] == 5000


def test_handle_query_credit_overdue(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="credit_overdue"),
        patch("app.db.session.execute") as mock_execute,
    ):
        mock_row = MagicMock()
        mock_row.overdue_count = 5
        mock_row.total_overdue = 1500.0
        mock_execute.return_value.fetchone.return_value = mock_row

        response = client.post("/api/v1/nlp/", json={"query_text": "credit"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "credit_overdue"
        assert data["supporting_metrics"]["overdue_customers"] == 5


def test_handle_query_market_intelligence(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="market_intelligence"),
        patch("app.market_intelligence.engine.IntelligenceEngine.get_market_summary") as mock_summary,
    ):
        mock_summary.return_value = {"active_alerts": 2}

        response = client.post("/api/v1/nlp/", json={"query_text": "market"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "market_intelligence"
        assert data["supporting_metrics"]["active_alerts"] == 2


def test_handle_query_market_intelligence_exception(client, owner_headers):
    with (
        patch("app.nlp.routes.resolve_intent", return_value="market_intelligence"),
        patch("app.market_intelligence.engine.IntelligenceEngine.get_market_summary", side_effect=Exception("Error")),
    ):
        response = client.post("/api/v1/nlp/", json={"query_text": "market"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert "Unable to fetch" in data["detail"]


def test_handle_query_default(client, owner_headers):
    with patch("app.nlp.routes.resolve_intent", return_value="default"):
        response = client.post("/api/v1/nlp/", json={"query_text": "unknown"}, headers=owner_headers)

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["intent"] == "default"
        assert "baseline" in data["detail"]


def test_nlp_query_v2_success(client, owner_headers):
    with patch("app.nlp.routes.handle_assistant_query", return_value="AI Response"):
        response = client.post("/api/v1/nlp/v2/ai/nlp/query", json={"query": "test query"}, headers=owner_headers)
        assert response.status_code == 200
        assert response.get_json()["response"] == "AI Response"


def test_nlp_query_v2_missing_query(client, owner_headers):
    response = client.post("/api/v1/nlp/v2/ai/nlp/query", json={}, headers=owner_headers)
    assert response.status_code == 400


def test_recommend_v2(client, owner_headers):
    with patch("app.nlp.routes.get_ai_recommendations", return_value=["rec1", "rec2"]):
        response = client.post("/api/v1/nlp/v2/ai/recommend", json={"user_id": 1}, headers=owner_headers)
        assert response.status_code == 200
        assert len(response.get_json()["recommendations"]) == 2
