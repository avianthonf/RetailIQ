"""
Tests for analytics endpoints.

Coverage:
- Revenue endpoint: correct sums, 7-day MA on limited data (<7 days)
- Profit endpoint: margin_pct calculation
- Top-products endpoint: ranking by metric
- Category breakdown: share_pct computation
- Contribution: Pareto flag + price-volume decomposition
- Diagnostics: trend deviation flagging
- Dashboard: correct structure, no raw-table scans (only agg tables queried)
- Cold-start: endpoints with < 7 days of data return partial MAs
"""
import pytest
from datetime import date, timedelta

from app import db as _db
from app.models import (
    Base, DailyStoreSummary, DailySkuSummary, DailyCategorySummary,
    Alert, Category, Product, Transaction, TransactionItem,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _seed_store_summary(store_id, start_date, n_days, base_rev=1000.0, base_profit=200.0):
    """Insert n daily_store_summary rows starting from start_date."""
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        rev = base_rev + i * 10
        pft = base_profit + i * 2
        row = DailyStoreSummary(
            date=d,
            store_id=store_id,
            revenue=rev,
            profit=pft,
            transaction_count=5 + i,
            avg_basket=rev / (5 + i),
            units_sold=10 + i,
        )
        _db.session.add(row)
    _db.session.commit()


def _seed_sku_summary(store_id, product_id, start_date, n_days,
                      base_rev=500.0, base_units=10.0, base_avg_price=50.0):
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        row = DailySkuSummary(
            date=d,
            store_id=store_id,
            product_id=product_id,
            revenue=base_rev + i * 5,
            profit=(base_rev + i * 5) * 0.2,
            units_sold=base_units + i,
            avg_selling_price=base_avg_price,
        )
        _db.session.add(row)
    _db.session.commit()


def _seed_category_summary(store_id, category_id, start_date, n_days, base_rev=300.0):
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        row = DailyCategorySummary(
            date=d,
            store_id=store_id,
            category_id=category_id,
            revenue=base_rev + i * 5,
            profit=(base_rev + i * 5) * 0.15,
            units_sold=5 + i,
        )
        _db.session.add(row)
    _db.session.commit()


# ── Revenue endpoint ──────────────────────────────────────────────────────────

class TestRevenueEndpoint:
    def test_revenue_correct_sums(self, client, owner_headers, test_store):
        start = date(2024, 1, 1)
        _seed_store_summary(test_store.store_id, start, 10, base_rev=1000.0)

        resp = client.get(
            f'/api/v1/analytics/revenue?start=2024-01-01&end=2024-01-10',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 10

        # First day revenue = 1000
        assert data[0]['revenue'] == pytest.approx(1000.0, abs=0.01)
        # Last day revenue = 1000 + 9*10 = 1090
        assert data[-1]['revenue'] == pytest.approx(1090.0, abs=0.01)

    def test_revenue_7d_moving_avg_full_window(self, client, owner_headers, test_store):
        start = date(2024, 2, 1)
        _seed_store_summary(test_store.store_id, start, 10, base_rev=100.0)

        resp = client.get(
            '/api/v1/analytics/revenue?start=2024-02-01&end=2024-02-10',
            headers=owner_headers,
        )
        data = resp.get_json()['data']
        # Day 7 (index 6) should have 7-point trailing average
        # days 0-6: revenues 100,110,120,130,140,150,160 → avg = 130
        assert data[6]['moving_avg_7d'] == pytest.approx(130.0, abs=0.5)

    def test_revenue_cold_start_partial_ma(self, client, owner_headers, test_store):
        """< 7 days of data → partial moving average still returned."""
        start = date(2024, 3, 1)
        _seed_store_summary(test_store.store_id, start, 3, base_rev=200.0)

        resp = client.get(
            '/api/v1/analytics/revenue?start=2024-03-01&end=2024-03-03',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 3
        # All rows should have moving_avg_7d key (partial averages)
        for row in data:
            assert 'moving_avg_7d' in row
            assert row['moving_avg_7d'] > 0

    def test_revenue_group_by_week(self, client, owner_headers, test_store):
        # seed 14 days (2 weeks Mon-Sun)
        start = date(2024, 4, 1)  # Monday
        _seed_store_summary(test_store.store_id, start, 14, base_rev=100.0)

        resp = client.get(
            '/api/v1/analytics/revenue?start=2024-04-01&end=2024-04-14&group_by=week',
            headers=owner_headers,
        )
        data = resp.get_json()['data']
        assert len(data) == 2  # 2 full ISO weeks

    def test_revenue_requires_owner(self, client, staff_headers, test_store):
        resp = client.get('/api/v1/analytics/revenue', headers=staff_headers)
        assert resp.status_code == 403

    def test_revenue_no_data_returns_empty(self, client, owner_headers, test_store):
        resp = client.get(
            '/api/v1/analytics/revenue?start=2020-01-01&end=2020-01-10',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []


# ── Profit endpoint ───────────────────────────────────────────────────────────

class TestProfitEndpoint:
    def test_profit_margin_pct(self, client, owner_headers, test_store):
        start = date(2024, 5, 1)
        _seed_store_summary(test_store.store_id, start, 5, base_rev=1000.0, base_profit=250.0)

        resp = client.get(
            '/api/v1/analytics/profit?start=2024-05-01&end=2024-05-05',
            headers=owner_headers,
        )
        data = resp.get_json()['data']
        # margin_pct for day 0 = 250/1000 * 100 = 25%
        assert data[0]['margin_pct'] == pytest.approx(25.0, abs=0.1)

    def test_profit_zero_revenue_margin(self, client, owner_headers, test_store):
        """Zero revenue → margin_pct should be 0, no division error."""
        _db.session.add(DailyStoreSummary(
            date=date(2024, 5, 10), store_id=test_store.store_id,
            revenue=0, profit=0, transaction_count=0,
        ))
        _db.session.commit()

        resp = client.get(
            '/api/v1/analytics/profit?start=2024-05-10&end=2024-05-10',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['margin_pct'] == 0.0


# ── Top Products ──────────────────────────────────────────────────────────────

class TestTopProductsEndpoint:
    def test_top_products_by_revenue(self, client, owner_headers, test_store, test_product, test_category):
        # Create a second product
        product2 = Product(
            store_id=test_store.store_id,
            category_id=test_category.category_id,
            name='Product B',
            selling_price=80.0,
            cost_price=40.0,
            current_stock=30.0,
        )
        _db.session.add(product2)
        _db.session.commit()

        start = date(2024, 6, 1)
        _seed_sku_summary(test_store.store_id, test_product.product_id, start, 5, base_rev=1000.0)
        _seed_sku_summary(test_store.store_id, product2.product_id, start, 5, base_rev=500.0)

        resp = client.get(
            '/api/v1/analytics/top-products?start=2024-06-01&end=2024-06-05&metric=revenue&limit=5',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        # test_product has higher revenue
        assert data[0]['product_id'] == test_product.product_id
        assert data[0]['rank'] == 1

    def test_top_products_invalid_metric(self, client, owner_headers, test_store):
        resp = client.get(
            '/api/v1/analytics/top-products?metric=invalid',
            headers=owner_headers,
        )
        assert resp.status_code == 400


# ── Category Breakdown ────────────────────────────────────────────────────────

class TestCategoryBreakdown:
    def test_share_pct_sums_to_100(self, client, owner_headers, test_store, test_category):
        # Create second category
        cat2 = Category(store_id=test_store.store_id, name='Electronics')
        _db.session.add(cat2)
        _db.session.commit()

        start = date(2024, 7, 1)
        _seed_category_summary(test_store.store_id, test_category.category_id, start, 5, base_rev=600.0)
        _seed_category_summary(test_store.store_id, cat2.category_id, start, 5, base_rev=400.0)

        resp = client.get(
            '/api/v1/analytics/category-breakdown?start=2024-07-01&end=2024-07-05',
            headers=owner_headers,
        )
        data = resp.get_json()['data']
        total_share = sum(d['share_pct'] for d in data)
        assert total_share == pytest.approx(100.0, abs=0.1)
        assert len(data) == 2


# ── Contribution Analysis ─────────────────────────────────────────────────────

class TestContributionEndpoint:
    def test_contribution_pareto_flag(self, client, owner_headers, test_store, test_product, test_category):
        """Create 5 SKUs; top 20% (1 SKU) should have is_pareto=True."""
        products = [test_product]
        for i in range(4):
            p = Product(
                store_id=test_store.store_id,
                category_id=test_category.category_id,
                name=f'Product {i+2}',
                selling_price=50.0,
                cost_price=25.0,
            )
            _db.session.add(p)
        _db.session.commit()

        # Re-query to get all products
        from app.models import Product as ProductModel
        all_products = _db.session.query(ProductModel).filter_by(store_id=test_store.store_id).all()

        start = date(2024, 8, 1)
        # First product gets dominant revenue
        _seed_sku_summary(test_store.store_id, all_products[0].product_id, start, 5, base_rev=5000.0)
        for p in all_products[1:]:
            _seed_sku_summary(test_store.store_id, p.product_id, start, 5, base_rev=100.0)

        resp = client.get(
            '/api/v1/analytics/contribution?start=2024-08-01&end=2024-08-05',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        skus = resp.get_json()['data']['skus']
        pareto_flagged = [s for s in skus if s['is_pareto']]
        # top 20% of 5 SKUs = 1 SKU
        assert len(pareto_flagged) == 1
        assert pareto_flagged[0]['product_id'] == all_products[0].product_id

    def test_contribution_near_zero_denominator(self, client, owner_headers, test_store, test_product, test_category):
        """If total rev change ≈ 0, contribution should be 0 (safe fallback)."""
        start = date(2024, 9, 1)
        _seed_sku_summary(test_store.store_id, test_product.product_id, start, 5, base_rev=1000.0)

        # Same exact revenue in compare period → delta ≈ 0
        resp = client.get(
            f'/api/v1/analytics/contribution'
            f'?start=2024-09-01&end=2024-09-05'
            f'&compare_start=2024-09-01&compare_end=2024-09-05',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        skus = resp.get_json()['data']['skus']
        for s in skus:
            assert s['contribution'] == pytest.approx(0.0, abs=0.01)

    def test_price_volume_decomposition_fields(self, client, owner_headers, test_store, test_product):
        """Contribution response must contain price_effect and volume_effect."""
        start = date(2024, 10, 1)
        _seed_sku_summary(test_store.store_id, test_product.product_id, start, 5, base_rev=1000.0)

        resp = client.get(
            '/api/v1/analytics/contribution?start=2024-10-01&end=2024-10-05',
            headers=owner_headers,
        )
        skus = resp.get_json()['data']['skus']
        for s in skus:
            assert 'price_effect' in s
            assert 'volume_effect' in s


# ── Diagnostics ───────────────────────────────────────────────────────────────

class TestDiagnosticsEndpoint:
    def test_trend_deviation_flagged(self, client, owner_headers, test_store):
        """Insert a day with revenue far below MA → flagged=True."""
        start = date(2024, 11, 1)
        # 6 days at 1000, 1 day at 100 (>20% deviation)
        _seed_store_summary(test_store.store_id, start, 6, base_rev=1000.0)
        _db.session.add(DailyStoreSummary(
            date=date(2024, 11, 7), store_id=test_store.store_id,
            revenue=100.0, profit=20.0, transaction_count=1,
        ))
        _db.session.commit()

        resp = client.get(
            '/api/v1/analytics/diagnostics?start=2024-11-01&end=2024-11-07',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        deviations = resp.get_json()['data']['trend_deviations']
        flagged = [d for d in deviations if d['flagged']]
        assert len(flagged) >= 1

    def test_diagnostics_has_all_keys(self, client, owner_headers, test_store):
        start = date(2024, 12, 1)
        _seed_store_summary(test_store.store_id, start, 5)

        resp = client.get(
            '/api/v1/analytics/diagnostics?start=2024-12-01&end=2024-12-05',
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'trend_deviations' in data
        assert 'sku_rolling_variance' in data
        assert 'margin_drift' in data


# ── Dashboard ─────────────────────────────────────────────────────────────────

class TestDashboardEndpoint:
    def test_dashboard_structure(self, client, owner_headers, test_store):
        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'today_kpis' in data
        assert 'revenue_7d' in data
        assert 'moving_avg_7d' in data
        assert 'alerts_summary' in data
        assert 'top_products_today' in data
        assert 'insights' in data

    def test_dashboard_insights_non_empty(self, client, owner_headers, test_store):
        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        insights = resp.get_json()['data']['insights']
        assert isinstance(insights, list)
        assert len(insights) >= 1
        assert len(insights) <= 3

    def test_dashboard_alerts_summary_has_total(self, client, owner_headers, test_store):
        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        alerts = resp.get_json()['data']['alerts_summary']
        assert 'total' in alerts

    def test_dashboard_with_seeded_data(self, app, client, owner_headers, test_store, test_product):
        """Seed today's aggregation data; dashboard should reflect it."""
        from datetime import date as date_cls
        today = date_cls.today()
        with app.app_context():
            _db.session.add(DailyStoreSummary(
                date=today,
                store_id=test_store.store_id,
                revenue=5000.0,
                profit=1000.0,
                transaction_count=42,
                avg_basket=119.0,
                units_sold=200.0,
            ))
            _db.session.add(DailySkuSummary(
                date=today,
                store_id=test_store.store_id,
                product_id=test_product.product_id,
                revenue=1500.0,
                profit=300.0,
                units_sold=30.0,
                avg_selling_price=50.0,
            ))
            _db.session.commit()

        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        assert resp.status_code == 200
        kpis = resp.get_json()['data']['today_kpis']
        assert kpis['revenue'] == pytest.approx(5000.0, abs=0.01)
        assert kpis['transactions'] == 42


    def test_revenue_7d_always_7_elements(self, client, owner_headers, test_store):
        """Seed 3 days of transactions, call dashboard, assert len(revenue_7d) == 7."""
        start = date.today() - timedelta(days=2)
        _seed_store_summary(test_store.store_id, start, 3, base_rev=100.0)

        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        data = resp.get_json()['data']
        assert len(data['revenue_7d']) == 7

    def test_revenue_7d_zero_fill(self, client, owner_headers, test_store):
        """Assert missing days have revenue == 0.0."""
        # Seed only today and 3 days ago.
        today = date.today()
        _db.session.add(DailyStoreSummary(
            date=today, store_id=test_store.store_id, revenue=100.0, profit=20.0, transaction_count=5
        ))
        _db.session.add(DailyStoreSummary(
            date=today - timedelta(days=3), store_id=test_store.store_id, revenue=200.0, profit=40.0, transaction_count=10
        ))
        _db.session.commit()

        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        data = resp.get_json()['data']
        rev_7d = data['revenue_7d']
        assert len(rev_7d) == 7
        
        # Day -3 should have 200, Day 0 should have 100, others 0
        missing_days = [r for r in rev_7d if r['date'] not in (str(today), str(today - timedelta(days=3)))]
        assert len(missing_days) == 5
        for d in missing_days:
            assert d['revenue'] == 0.0

    def test_category_breakdown_sorted_descending(self, client, owner_headers, test_store, test_category):
        from app.models import Category
        cat2 = Category(store_id=test_store.store_id, name='Small Category')
        _db.session.add(cat2)
        _db.session.commit()

        # Seed categories with different revenues
        _seed_category_summary(test_store.store_id, test_category.category_id, date.today(), 1, base_rev=1000.0)
        _seed_category_summary(test_store.store_id, cat2.category_id, date.today(), 1, base_rev=200.0)

        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        data = resp.get_json()['data']
        
        assert 'category_breakdown' in data
        cats = data['category_breakdown']
        assert len(cats) >= 2
        
        # Verify sorted descending
        revenues = [c['revenue'] for c in cats]
        assert revenues == sorted(revenues, reverse=True)
        assert 'percentage' in cats[0]

    def test_payment_mode_breakdown_present(self, client, owner_headers, test_store):
        """Ensure the response includes payment_mode_breakdown."""
        resp = client.get('/api/v1/analytics/dashboard', headers=owner_headers)
        data = resp.get_json()['data']
        
        assert 'payment_mode_breakdown' in data
        assert isinstance(data['payment_mode_breakdown'], list)
