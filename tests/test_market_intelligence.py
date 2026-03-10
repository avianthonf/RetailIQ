"""
Tests for Market Intelligence Module
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.market_intelligence.engine import IntelligenceEngine
from app.models import Category, DataSource, MarketAlert, MarketSignal, PriceIndex
from app.pricing.engine import generate_market_aware_suggestions


@pytest.fixture
def market_setup(app):
    """Setup basic market data for tests"""
    with app.app_context():
        # Make sure we have a category
        cat = db.session.query(Category).first()
        if not cat:
            cat = Category(name="Test Category", color_tag="#FFFFFF")
            db.session.add(cat)
            db.session.commit()

        cat_id = cat.category_id

        # Add a data source
        source = DataSource(name="Test Source", source_type="API")
        db.session.add(source)
        db.session.commit()

        yield cat_id, source.id


def test_models_creation(app, market_setup):
    """Test creating market intelligence models"""
    cat_id, source_id = market_setup

    with app.app_context():
        # Create MarketSignal
        signal = MarketSignal(
            signal_type="PRICE",
            source_id=source_id,
            category_id=cat_id,
            value=105.5,
            confidence=0.9,
            quality_score=0.95,
        )
        db.session.add(signal)

        # Create PriceIndex
        idx = PriceIndex(category_id=cat_id, index_value=120.0, computation_method="laspeyres")
        db.session.add(idx)

        # Create MarketAlert
        alert = MarketAlert(alert_type="PRICE_SPIKE", severity="WARNING", merchant_id=1, message="Test Alert")
        db.session.add(alert)

        db.session.commit()

        assert db.session.query(MarketSignal).count() == 1
        assert db.session.query(PriceIndex).count() == 1
        assert db.session.query(MarketAlert).count() == 1


def test_engine_compute_index(app, market_setup):
    """Test price index computation logic"""
    cat_id, source_id = market_setup

    with app.app_context():
        # Insert test signals
        signals = [
            MarketSignal(
                signal_type="PRICE",
                source_id=source_id,
                category_id=cat_id,
                value=100.0,
                confidence=1.0,
                quality_score=1.0,
            ),
            MarketSignal(
                signal_type="PRICE",
                source_id=source_id,
                category_id=cat_id,
                value=110.0,
                confidence=1.0,
                quality_score=1.0,
            ),
        ]
        db.session.add_all(signals)
        db.session.commit()

        index_val = IntelligenceEngine.compute_price_index(cat_id)
        assert index_val == 105.0  # Average of 100 and 110

        # Verify it was saved
        saved_idx = db.session.query(PriceIndex).filter_by(category_id=cat_id).first()
        assert saved_idx is not None
        assert saved_idx.index_value == 105.0


def test_engine_anomaly_detection(app, market_setup):
    """Test Isolation Forest anomaly detection"""
    cat_id, source_id = market_setup

    with app.app_context():
        # Need >= 20 points for isolation forest
        now = datetime.now(timezone.utc)
        signals = []
        for i in range(25):
            val = 100.0 if i < 24 else 200.0  # Create one massive spike
            signals.append(
                MarketSignal(
                    signal_type="PRICE",
                    source_id=source_id,
                    category_id=cat_id,
                    value=val,
                    timestamp=now - timedelta(days=25 - i),
                )
            )

        db.session.add_all(signals)
        db.session.commit()

        anomalies = IntelligenceEngine.detect_anomalies(cat_id)
        # Should detect the 200.0 value as an anomaly
        assert len(anomalies) > 0
        assert any(a.value == 200.0 for a in anomalies)


def test_engine_sentiment(app):
    """Test basic sentiment analysis"""
    positive_text = "Market shows record growth and high profit."
    assert IntelligenceEngine.analyze_sentiment(positive_text) > 0

    negative_text = "Severe disruption and drop in supply causing crisis."
    assert IntelligenceEngine.analyze_sentiment(negative_text) < 0


def test_api_signals_endpoint(client, owner_headers, market_setup):
    """Test the /api/v2/market/signals endpoint"""
    cat_id, source_id = market_setup

    # Needs app context to insert
    with client.application.app_context():
        signal = MarketSignal(signal_type="DEMAND", source_id=source_id, category_id=cat_id, value=50.0)
        db.session.add(signal)
        db.session.commit()

    res = client.get("/api/v2/market/signals", headers=owner_headers)
    assert res.status_code == 200
    data = res.json["data"]
    assert len(data) >= 1
    assert any(s["signal_type"] == "DEMAND" for s in data)


def test_market_aware_pricing(app, market_setup):
    """Test that pricing suggestions consume market indices"""
    cat_id, source_id = market_setup

    with app.app_context():
        from app.models import DailySkuSummary, Product, Store

        # Setup store and product
        store = Store(store_name="Test Store", store_type="grocery")
        db.session.add(store)
        db.session.commit()

        prod = Product(
            store_id=store.store_id,
            category_id=cat_id,
            name="Test Prod",
            sku_code="SKU1",
            selling_price=10.0,
            cost_price=9.0,
        )  # 10% margin -> RAISE candidate
        db.session.add(prod)
        db.session.commit()

        # Add 30 days history to qualify for pricing engine
        now = datetime.now(timezone.utc)
        for i in range(35):
            summary = DailySkuSummary(
                store_id=store.store_id,
                product_id=prod.product_id,
                date=(now - timedelta(days=i)).date(),
                units_sold=5,
                revenue=50.0,
            )
            db.session.add(summary)

        # Add highly inflated market index
        idx = PriceIndex(category_id=cat_id, index_value=120.0, computed_at=now)
        db.session.add(idx)
        db.session.commit()

        suggestions = generate_market_aware_suggestions(store.store_id, db.session)
        assert len(suggestions) > 0
        sugg = suggestions[0]

        assert sugg["suggestion_type"] == "RAISE"
        assert sugg["market_context"].get("inflation_support") == True
        assert "inflation" in sugg["reason"]
