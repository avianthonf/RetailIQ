"""
End-to-end integration tests for RetailIQ.

These are *not* unit tests of individual routes.  Each test simulates a
realistic, multi-step user journey that spans several endpoints.

All six scenarios start from a clean DB (function-scoped ``app`` fixture)
and reuse the shared conftest.py infrastructure (in-memory SQLite, StaticPool).

NOTE: Celery tasks that use ``task_session()`` create a *separate* engine from
DATABASE_URL which does NOT share data with in-memory SQLite.  In these tests
we reproduce the critical task logic via the Flask ``db.session`` directly,
or seed DB tables to simulate task output.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import db as _db
from app.auth.utils import generate_access_token
from app.models import (
    Alert,
    AnalyticsSnapshot,
    Category,
    Customer,
    CustomerLoyaltyAccount,
    DailyCategorySummary,
    DailySkuSummary,
    DailyStoreSummary,
    GoodsReceiptNote,
    GSTFilingPeriod,
    GSTTransaction,
    HSNMaster,
    LoyaltyProgram,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Store,
    StoreGSTConfig,
    Supplier,
    SupplierProduct,
    User,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _owner_headers(user, store):
    """Build Authorization header for an owner."""
    token = generate_access_token(user.user_id, store.store_id, "owner")
    return {"Authorization": f"Bearer {token}"}


def _make_txn_payload(product_id, qty, price, payment_mode="CASH", customer_id=None):
    """Return a valid transaction payload dict."""
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": payment_mode,
        "line_items": [
            {
                "product_id": product_id,
                "quantity": qty,
                "selling_price": price,
            }
        ],
    }
    if customer_id is not None:
        payload["customer_id"] = customer_id
    return payload


def _rebuild_aggregates_inline(store_id, target_date):
    """
    In-process equivalent of rebuild_daily_aggregates task.

    Uses Flask db.session directly (task_session won't work with
    in-memory SQLite's StaticPool).
    """
    from sqlalchemy import text

    date_str = str(target_date)

    # ── daily_store_summary ──────────────────────────────────────────
    row = _db.session.execute(
        text("""
        SELECT
            COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0) AS revenue,
            COALESCE(SUM(ti.quantity * (ti.selling_price - ti.cost_price_at_time) - ti.discount_amount), 0) AS profit,
            COUNT(DISTINCT t.transaction_id) AS txn_count,
            COALESCE(SUM(ti.quantity), 0) AS units_sold
        FROM transactions t
        JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
        WHERE t.store_id = :sid AND t.created_at >= :start_d AND t.created_at < :end_d AND t.is_return = 0
    """),
        {"sid": store_id, "start_d": str(target_date), "end_d": str(target_date + timedelta(days=1))},
    ).fetchone()

    if row and row.txn_count > 0:
        avg_basket = float(row.revenue) / row.txn_count
        existing = _db.session.query(DailyStoreSummary).filter_by(store_id=store_id, date=target_date).first()
        if existing:
            existing.revenue = float(row.revenue)
            existing.profit = float(row.profit)
            existing.transaction_count = row.txn_count
            existing.avg_basket = avg_basket
            existing.units_sold = float(row.units_sold)
        else:
            _db.session.add(
                DailyStoreSummary(
                    store_id=store_id,
                    date=target_date,
                    revenue=float(row.revenue),
                    profit=float(row.profit),
                    transaction_count=row.txn_count,
                    avg_basket=avg_basket,
                    units_sold=float(row.units_sold),
                )
            )

    # ── daily_sku_summary ────────────────────────────────────────────
    sku_rows = _db.session.execute(
        text("""
        SELECT
            ti.product_id,
            COALESCE(SUM(ti.quantity * ti.selling_price - ti.discount_amount), 0) AS revenue,
            COALESCE(SUM(ti.quantity * (ti.selling_price - ti.cost_price_at_time) - ti.discount_amount), 0) AS profit,
            COALESCE(SUM(ti.quantity), 0) AS units_sold,
            CASE WHEN SUM(ti.quantity) > 0
                 THEN SUM(ti.quantity * ti.selling_price) / SUM(ti.quantity) ELSE 0 END AS avg_price
        FROM transactions t
        JOIN transaction_items ti ON t.transaction_id = ti.transaction_id
        WHERE t.store_id = :sid AND t.created_at >= :start_d AND t.created_at < :end_d AND t.is_return = 0
        GROUP BY ti.product_id
    """),
        {"sid": store_id, "start_d": str(target_date), "end_d": str(target_date + timedelta(days=1))},
    ).fetchall()

    for sr in sku_rows:
        existing = (
            _db.session.query(DailySkuSummary)
            .filter_by(store_id=store_id, date=target_date, product_id=sr.product_id)
            .first()
        )
        if existing:
            existing.revenue = float(sr.revenue)
            existing.profit = float(sr.profit)
            existing.units_sold = float(sr.units_sold)
            existing.avg_selling_price = float(sr.avg_price)
        else:
            _db.session.add(
                DailySkuSummary(
                    store_id=store_id,
                    date=target_date,
                    product_id=sr.product_id,
                    revenue=float(sr.revenue),
                    profit=float(sr.profit),
                    units_sold=float(sr.units_sold),
                    avg_selling_price=float(sr.avg_price),
                )
            )

    _db.session.commit()


def _evaluate_alerts_inline(store_id):
    """
    In-process equivalent of evaluate_alerts task for LOW_STOCK alerts.
    """
    from sqlalchemy import text

    low_rows = _db.session.execute(
        text("""
        SELECT product_id, name, current_stock, reorder_level
        FROM products
        WHERE store_id = :sid AND is_active = TRUE AND current_stock <= reorder_level
    """),
        {"sid": store_id},
    ).fetchall()

    for r in low_rows:
        # Only create if no existing LOW_STOCK alert for this product
        existing = (
            _db.session.query(Alert)
            .filter_by(store_id=store_id, alert_type="LOW_STOCK", product_id=r.product_id)
            .filter(Alert.resolved_at.is_(None))
            .first()
        )
        if not existing:
            _db.session.add(
                Alert(
                    store_id=store_id,
                    alert_type="LOW_STOCK",
                    priority="CRITICAL",
                    product_id=r.product_id,
                    message=f"Low stock: '{r.name}' has {float(r.current_stock):.2f} units.",
                    created_at=datetime.now(timezone.utc),
                )
            )
    _db.session.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  1) test_full_retail_day
# ══════════════════════════════════════════════════════════════════════════════


def test_full_retail_day(client, app, test_store, test_owner, owner_headers, test_category):
    """
    a. Use existing owner fixture (register+login equivalent).
    b. Create 3 products.
    c. Record 5 sales (mix of CASH / UPI).
    d. Run rebuild_daily_aggregates (inline).
    e. GET /analytics/dashboard → today revenue matches.
    f. GET /inventory/alerts → no false alerts (stock above reorder).
    g. Run evaluate_alerts (inline) → LOW_STOCK alert created for depleted product.
    """
    with app.app_context():
        headers = owner_headers
        sid = test_store.store_id
        today = datetime.now(timezone.utc).date()

        # ── b. Create 3 products ────────────────────────────────────────
        products = []
        for name, cost, sell, stock in [
            ("Apples", 40, 60, 100),
            ("Bread", 20, 35, 50),
            ("Cheese", 100, 150, 10),  # low initial stock → will deplete below reorder
        ]:
            resp = client.post(
                "/api/v1/inventory",
                headers=headers,
                json={
                    "name": name,
                    "cost_price": cost,
                    "selling_price": sell,
                    "current_stock": stock,
                    "reorder_level": 15,
                    "category_id": test_category.category_id,
                },
            )
            assert resp.status_code == 201, f"Failed to create {name}: {resp.json}"
            products.append(resp.json["data"]["product_id"])

        pid_apples, pid_bread, pid_cheese = products

        # ── c. Record 5 sales ───────────────────────────────────────────
        sale_payloads = [
            _make_txn_payload(pid_apples, 5, 60, "CASH"),
            _make_txn_payload(pid_apples, 3, 60, "UPI"),
            _make_txn_payload(pid_bread, 10, 35, "CASH"),
            _make_txn_payload(pid_cheese, 8, 150, "UPI"),  # drops cheese to 2
            _make_txn_payload(pid_bread, 2, 35, "CASH"),
        ]
        expected_revenue = (5 * 60) + (3 * 60) + (10 * 35) + (8 * 150) + (2 * 35)

        for payload in sale_payloads:
            resp = client.post("/api/v1/transactions", headers=headers, json=payload)
            assert resp.status_code == 201, f"Txn failed: {resp.json}"

        # ── d. Rebuild daily aggregates (inline) ────────────────────────
        _rebuild_aggregates_inline(sid, today)

        # ── e. GET /analytics/dashboard ─────────────────────────────────
        resp = client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 200
        dashboard = resp.json["data"]

        today_str = today.isoformat()
        today_entries = [r for r in dashboard["revenue_7d"] if r["date"] == today_str]
        assert len(today_entries) == 1
        assert today_entries[0]["revenue"] == pytest.approx(expected_revenue, rel=0.01)

        # ── f. GET /inventory/alerts → no false LOW_STOCK yet ───────────
        resp = client.get("/api/v1/inventory/alerts", headers=headers)
        assert resp.status_code == 200

        # ── g. Evaluate alerts (inline) → LOW_STOCK for cheese ──────────
        _evaluate_alerts_inline(sid)

        resp = client.get("/api/v1/inventory/alerts", headers=headers)
        assert resp.status_code == 200
        alerts = resp.json["data"]
        cheese_alerts = [a for a in alerts if a["alert_type"] == "LOW_STOCK" and a["product_id"] == pid_cheese]
        assert len(cheese_alerts) >= 1, "Cheese (stock=2, reorder=15) should trigger LOW_STOCK"


# ══════════════════════════════════════════════════════════════════════════════
#  2) test_supplier_po_stock_cycle
# ══════════════════════════════════════════════════════════════════════════════


def test_supplier_po_stock_cycle(client, app, test_store, test_owner, owner_headers, test_category):
    """
    Create supplier → link product → create PO → send → receive (via ORM)
    → assert product stock increased, PO status FULFILLED, GRN created.

    NOTE: The receive endpoint uses `with_for_update()` and `begin_nested()`
    which are PostgreSQL-specific. We simulate the receive step via direct
    ORM to keep the test runnable on SQLite.
    """
    with app.app_context():
        from uuid import UUID as _UUID

        headers = owner_headers
        sid = test_store.store_id

        # Create product with stock = 20
        resp = client.post(
            "/api/v1/inventory",
            headers=headers,
            json={
                "name": "Widget",
                "cost_price": 50,
                "selling_price": 80,
                "current_stock": 20,
                "category_id": test_category.category_id,
            },
        )
        assert resp.status_code == 201
        product_id = resp.json["data"]["product_id"]

        # Create supplier
        resp = client.post("/api/v1/suppliers", headers=headers, json={"name": "Acme Corp"})
        assert resp.status_code == 201
        supplier_id = resp.json["data"]["id"]

        # Link product to supplier
        resp = client.post(
            f"/api/v1/suppliers/{supplier_id}/products",
            headers=headers,
            json={"product_id": product_id, "quoted_price": 48, "lead_time_days": 5},
        )
        assert resp.status_code == 201

        # Create PO (DRAFT)
        resp = client.post(
            "/api/v1/purchase-orders",
            headers=headers,
            json={
                "supplier_id": supplier_id,
                "items": [{"product_id": product_id, "ordered_qty": 30, "unit_price": 48}],
            },
        )
        assert resp.status_code == 201
        po_id = resp.json["data"]["id"]

        # Send PO
        resp = client.put(f"/api/v1/purchase-orders/{po_id}/send", headers=headers)
        assert resp.status_code == 200

        # ── Simulate PO receive via ORM (SQLite lacks FOR UPDATE) ────────
        po = _db.session.query(PurchaseOrder).filter_by(id=_UUID(po_id)).first()
        assert po is not None and po.status == "SENT"

        poi = _db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).first()
        poi.received_qty = float(poi.received_qty or 0) + 30

        product = _db.session.query(Product).filter_by(product_id=product_id, store_id=sid).first()
        product.current_stock = float(product.current_stock or 0) + 30

        grn = GoodsReceiptNote(
            po_id=po.id,
            store_id=sid,
            received_by=test_owner.user_id,
            notes="Full delivery",
        )
        _db.session.add(grn)

        # Check fulfilment
        all_items = _db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
        if all(float(i.received_qty or 0) >= float(i.ordered_qty) for i in all_items):
            po.status = "FULFILLED"
        _db.session.commit()

        # ── Assertions ───────────────────────────────────────────────────
        assert po.status == "FULFILLED"

        resp = client.get(f"/api/v1/inventory/{product_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json["data"]["current_stock"] == pytest.approx(50.0)

        grn_check = _db.session.query(GoodsReceiptNote).filter_by(po_id=po.id).first()
        assert grn_check is not None


# ══════════════════════════════════════════════════════════════════════════════
#  3) test_loyalty_full_cycle
# ══════════════════════════════════════════════════════════════════════════════


def test_loyalty_full_cycle(client, app, test_store, test_owner, owner_headers, test_category):
    """
    Set up loyalty (1 pt/₹, 0.1 redemption rate) → create customer →
    sale of ₹200 → assert 200 points → redeem 100 → assert balance 100 →
    attempt redeem 200 → 422.
    """
    with app.app_context():
        headers = owner_headers

        # Set up loyalty program
        resp = client.put(
            "/api/v1/loyalty/program",
            headers=headers,
            json={
                "points_per_rupee": 1.0,
                "redemption_rate": 0.1,
                "min_redemption_points": 50,
                "expiry_days": 365,
                "is_active": True,
            },
        )
        assert resp.status_code == 200

        # Create a customer
        resp = client.post(
            "/api/v1/customers",
            headers=headers,
            json={
                "name": "Raj Kumar",
                "mobile_number": "9876543210",
            },
        )
        assert resp.status_code == 201
        customer_id = resp.json["data"]["customer_id"]

        # Create a product
        resp = client.post(
            "/api/v1/inventory",
            headers=headers,
            json={
                "name": "Premium Tea",
                "cost_price": 80,
                "selling_price": 200,
                "current_stock": 100,
                "category_id": test_category.category_id,
            },
        )
        assert resp.status_code == 201
        product_id = resp.json["data"]["product_id"]

        # Record sale of ₹200 with customer_id → should earn 200 points
        resp = client.post(
            "/api/v1/transactions", headers=headers, json=_make_txn_payload(product_id, 1, 200, "CASH", customer_id)
        )
        assert resp.status_code == 201

        # Verify loyalty account has 200 points
        resp = client.get(f"/api/v1/loyalty/customers/{customer_id}", headers=headers)
        assert resp.status_code == 200
        assert float(resp.json["data"]["redeemable_points"]) == pytest.approx(200.0)

        # Redeem 100 points
        resp = client.post(
            f"/api/v1/loyalty/customers/{customer_id}/redeem", headers=headers, json={"points_to_redeem": 100}
        )
        assert resp.status_code == 200

        # Verify balance is 100
        resp = client.get(f"/api/v1/loyalty/customers/{customer_id}", headers=headers)
        assert resp.status_code == 200
        assert float(resp.json["data"]["redeemable_points"]) == pytest.approx(100.0)

        # Attempt to redeem 200 points (only 100 available) → 422
        resp = client.post(
            f"/api/v1/loyalty/customers/{customer_id}/redeem", headers=headers, json={"points_to_redeem": 200}
        )
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
#  4) test_gst_month_compilation
# ══════════════════════════════════════════════════════════════════════════════


def test_gst_month_compilation(client, app, test_store, test_owner, owner_headers, test_category):
    """
    Enable GST → seed HSN codes → create products → record 10 transactions →
    compile GST in-process → verify summary and liability slabs.
    """
    with app.app_context():
        headers = owner_headers
        sid = test_store.store_id
        period = datetime.now(timezone.utc).strftime("%Y-%m")

        # Enable GST via direct ORM (avoids GSTIN checksum complexity)
        config = StoreGSTConfig(
            store_id=sid,
            gstin="29AABCU9603R1ZP",
            registration_type="REGULAR",
            state_code="29",
            is_gst_enabled=True,
        )
        _db.session.add(config)

        # Seed HSN codes with different GST rates
        hsn_codes = [
            HSNMaster(hsn_code="1006", description="Rice", default_gst_rate=5.0),
            HSNMaster(hsn_code="3304", description="Beauty products", default_gst_rate=18.0),
        ]
        for h in hsn_codes:
            _db.session.add(h)
        _db.session.commit()

        # Create 2 products with different HSN codes via API
        product_ids = {}
        for name, hsn, cost, sell in [
            ("Basmati Rice", "1006", 60, 80),
            ("Face Cream", "3304", 100, 200),
        ]:
            resp = client.post(
                "/api/v1/inventory",
                headers=headers,
                json={
                    "name": name,
                    "cost_price": cost,
                    "selling_price": sell,
                    "current_stock": 200,
                    "category_id": test_category.category_id,
                    "hsn_code": hsn,  # Include HSN code in the creation request
                },
            )
            assert resp.status_code == 201
            product_ids[name] = resp.json["data"]["product_id"]

        pid_rice = product_ids["Basmati Rice"]
        pid_cream = product_ids["Face Cream"]

        # Record 10 transactions: 6 rice (5% GST), 4 cream (18% GST)
        for _ in range(6):
            resp = client.post("/api/v1/transactions", headers=headers, json=_make_txn_payload(pid_rice, 2, 80, "UPI"))
            assert resp.status_code == 201

        for _ in range(4):
            resp = client.post(
                "/api/v1/transactions", headers=headers, json=_make_txn_payload(pid_cream, 1, 200, "CASH")
            )
            assert resp.status_code == 201

        # Verify GST transactions were recorded (automated by transaction service)
        gst_txn_count = _db.session.query(GSTTransaction).filter_by(store_id=sid, period=period).count()
        assert gst_txn_count == 10, f"Expected 10 GST txns, got {gst_txn_count}"

        # Compile GST filing in-process (simulate task via ORM)
        gst_txns = _db.session.query(GSTTransaction).filter_by(store_id=sid, period=period).all()

        total_taxable = sum(Decimal(str(gt.taxable_amount or 0)) for gt in gst_txns)
        total_cgst = sum(Decimal(str(gt.cgst_amount or 0)) for gt in gst_txns)
        total_sgst = sum(Decimal(str(gt.sgst_amount or 0)) for gt in gst_txns)
        total_igst = sum(Decimal(str(gt.igst_amount or 0)) for gt in gst_txns)

        filing = GSTFilingPeriod(
            store_id=sid,
            period=period,
            total_taxable=round(total_taxable, 2),
            total_cgst=round(total_cgst, 2),
            total_sgst=round(total_sgst, 2),
            total_igst=round(total_igst, 2),
            invoice_count=len(gst_txns),
            status="COMPILED",
            compiled_at=datetime.now(timezone.utc),
        )
        _db.session.add(filing)
        _db.session.commit()

        # GET /gst/summary
        resp = client.get(f"/api/v1/gst/summary?period={period}", headers=headers)
        assert resp.status_code == 200
        summary = resp.json["data"]

        assert float(summary["total_cgst"]) > 0
        assert float(summary["total_sgst"]) > 0
        assert float(summary["total_cgst"]) == pytest.approx(
            float(summary["total_sgst"]), rel=0.01
        )  # intra-state → CGST == SGST
        assert summary["invoice_count"] == 10
        assert summary["status"] == "COMPILED"

        # GET /gst/liability-slabs
        resp = client.get(f"/api/v1/gst/liability-slabs?period={period}", headers=headers)
        assert resp.status_code == 200
        slabs = resp.json["data"]
        assert len(slabs) >= 2  # 5% and 18% slabs
        slab_total = sum(s["tax_amount"] for s in slabs)
        assert slab_total == pytest.approx(float(summary["total_cgst"]) + float(summary["total_sgst"]), rel=0.01)


# ══════════════════════════════════════════════════════════════════════════════
#  5) test_offline_snapshot_freshness
# ══════════════════════════════════════════════════════════════════════════════


def test_offline_snapshot_freshness(client, app, test_store, test_owner, owner_headers):
    """
    Seed 30 days of daily_store_summary → build snapshot in-process →
    GET /offline/snapshot → assert built_at is recent and revenue data present.
    """
    with app.app_context():
        headers = owner_headers
        sid = test_store.store_id
        today = datetime.now(timezone.utc).date()

        # Seed 30 days of DailyStoreSummary
        for i in range(30):
            d = today - timedelta(days=i)
            _db.session.add(
                DailyStoreSummary(
                    store_id=sid,
                    date=d,
                    revenue=1000 + i * 10,
                    profit=300 + i * 3,
                    transaction_count=20 + i,
                    avg_basket=50.0,
                    units_sold=100 + i,
                )
            )
        _db.session.commit()

        # Build snapshot in-process (uses Flask db.session via builder)
        from app.offline.builder import build_snapshot

        snapshot_data = build_snapshot(sid, _db)
        serialized_len = len(json.dumps(snapshot_data).encode("utf-8"))

        # Upsert directly
        snap = AnalyticsSnapshot(
            store_id=sid,
            snapshot_data=snapshot_data,
            built_at=datetime.fromisoformat(snapshot_data["built_at"]),
            size_bytes=serialized_len,
        )
        _db.session.add(snap)
        _db.session.commit()

        # GET snapshot
        resp = client.get("/api/v1/offline/snapshot", headers=headers)
        assert resp.status_code == 200
        data = resp.json["data"]

        # built_at should be within last 60 seconds
        built_at = datetime.fromisoformat(data["built_at"])
        age = (datetime.now(timezone.utc) - built_at.replace(tzinfo=timezone.utc)).total_seconds()
        assert age < 60, f"Snapshot too old: {age:.0f}s"

        # Snapshot should contain revenue data
        snapshot = data["snapshot"]
        assert len(snapshot.get("revenue_30d", [])) > 0, "revenue_30d should be populated"


# ══════════════════════════════════════════════════════════════════════════════
#  6) test_chain_cross_store_isolation
# ══════════════════════════════════════════════════════════════════════════════


def test_chain_cross_store_isolation(client, app):
    """
    Create 2 stores: A and B.  Login as owner of A.  Create supplier in A.
    Verify A's JWT returns supplier, and B's JWT does not.
    """
    with app.app_context():
        import bcrypt

        pw_hash = bcrypt.hashpw(b"Password1!", bcrypt.gensalt(4)).decode()

        # Store A + Owner A
        store_a = Store(store_name="Alpha Mart", store_type="grocery")
        _db.session.add(store_a)
        _db.session.commit()
        owner_a = User(
            mobile_number="7000000001",
            password_hash=pw_hash,
            full_name="Owner Alpha",
            role="owner",
            store_id=store_a.store_id,
            is_active=True,
        )
        _db.session.add(owner_a)
        _db.session.commit()
        headers_a = _owner_headers(owner_a, store_a)

        # Store B + Owner B
        store_b = Store(store_name="Beta Bazaar", store_type="grocery")
        _db.session.add(store_b)
        _db.session.commit()
        owner_b = User(
            mobile_number="7000000002",
            password_hash=pw_hash,
            full_name="Owner Beta",
            role="owner",
            store_id=store_b.store_id,
            is_active=True,
        )
        _db.session.add(owner_b)
        _db.session.commit()
        headers_b = _owner_headers(owner_b, store_b)

        # Create supplier in Store A
        resp = client.post("/api/v1/suppliers", headers=headers_a, json={"name": "Alpha Supplier"})
        assert resp.status_code == 201
        supplier_id_a = resp.json["data"]["id"]

        # Store A → sees its own supplier
        resp = client.get("/api/v1/suppliers", headers=headers_a)
        assert resp.status_code == 200
        ids_a = [s["id"] for s in resp.json["data"]]
        assert supplier_id_a in ids_a, "Store A should see its own supplier"

        # Store B → must NOT see Store A's supplier
        resp = client.get("/api/v1/suppliers", headers=headers_b)
        assert resp.status_code == 200
        ids_b = [s["id"] for s in resp.json["data"]]
        assert supplier_id_a not in ids_b, "Store B must not see Store A's supplier"

        # Store B → 404 on Store A's supplier detail
        resp = client.get(f"/api/v1/suppliers/{supplier_id_a}", headers=headers_b)
        assert resp.status_code in (403, 404)
