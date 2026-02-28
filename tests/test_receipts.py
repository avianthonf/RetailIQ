"""
tests/test_receipts.py — Comprehensive pytest tests for the Barcode &
Receipt Printing module.

Covers:
  1. test_barcode_lookup_found
  2. test_barcode_lookup_not_found
  3. test_barcode_register_duplicate_rejected
  4. test_receipt_template_upsert
  5. test_print_job_created
  6. test_print_job_poll
  7. test_build_receipt_payload_structure
"""
import uuid
import pytest
from datetime import datetime, timezone

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

# ── SQLite compat for Postgres-specific types ─────────────────────────────
@compiles(JSONB, "sqlite")
def _compile_jsonb(type_, compiler, **kw):
    return "JSON"

@compiles(PGUUID, "sqlite")
def _compile_uuid(type_, compiler, **kw):
    return "VARCHAR"
# ─────────────────────────────────────────────────────────────────────────

from app import db
from app.models import (
    Store, User, Category, Product,
    Barcode, ReceiptTemplate, PrintJob,
    Transaction, TransactionItem,
)
from app.auth.utils import generate_access_token
from app.receipts.formatter import build_receipt_payload


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def setup(app):
    """
    Seed a store, owner user, category, and a product.
    Returns a dict with all seeded objects.
    """
    store = Store(store_name="Receipt Test Store", store_type="grocery",
                  city="Mumbai", state="Maharashtra", gst_number="27AAAPL1234C1ZV")
    db.session.add(store)
    db.session.commit()

    owner = User(
        mobile_number="9800000001",
        full_name="Receipt Owner",
        role="owner",
        store_id=store.store_id,
        is_active=True,
    )
    db.session.add(owner)
    db.session.commit()

    cat = Category(store_id=store.store_id, name="Beverages", gst_rate=12.0)
    db.session.add(cat)
    db.session.commit()

    product = Product(
        store_id=store.store_id,
        category_id=cat.category_id,
        name="Cola 500ml",
        selling_price=40.0,
        cost_price=25.0,
        current_stock=120.0,
    )
    db.session.add(product)
    db.session.commit()

    token = generate_access_token(owner.user_id, store.store_id, "owner")
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "store": store,
        "owner": owner,
        "product": product,
        "headers": headers,
    }


@pytest.fixture
def seeded_barcode(setup):
    """Seed a barcode attached to setup's product."""
    barcode = Barcode(
        product_id=setup["product"].product_id,
        store_id=setup["store"].store_id,
        barcode_value="8901234567890",
        barcode_type="EAN13",
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(barcode)
    db.session.commit()
    return barcode


@pytest.fixture
def seeded_transaction(setup):
    """Seed a transaction with one line item for the setup product."""
    txn_id = uuid.uuid4()
    txn = Transaction(
        transaction_id=txn_id,
        store_id=setup["store"].store_id,
        payment_mode="CASH",
        created_at=datetime.now(timezone.utc),
        is_return=False,
    )
    db.session.add(txn)
    db.session.commit()

    item = TransactionItem(
        transaction_id=txn_id,
        product_id=setup["product"].product_id,
        quantity=3.0,
        selling_price=40.0,
        original_price=40.0,
        discount_amount=0.0,
        cost_price_at_time=25.0,
    )
    db.session.add(item)
    db.session.commit()

    return txn


# ===========================================================================
# Tests
# ===========================================================================

class TestBarcodeLookup:

    def test_barcode_lookup_found(self, client, setup, seeded_barcode):
        """Seeding a product + barcode should yield 200 with correct product fields."""
        resp = client.get(
            f"/api/v1/barcodes/lookup?value={seeded_barcode.barcode_value}",
            headers=setup["headers"],
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["barcode_value"] == seeded_barcode.barcode_value
        assert data["product_id"] == setup["product"].product_id
        assert data["product_name"] == setup["product"].name
        assert data["current_stock"] == float(setup["product"].current_stock)
        assert data["price"] == float(setup["product"].selling_price)

    def test_barcode_lookup_not_found(self, client, setup):
        """A barcode that doesn't exist should return 404."""
        resp = client.get(
            "/api/v1/barcodes/lookup?value=DOES-NOT-EXIST-999",
            headers=setup["headers"],
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"

    def test_barcode_lookup_missing_param(self, client, setup):
        """Omitting the 'value' query param should return 400."""
        resp = client.get("/api/v1/barcodes/lookup", headers=setup["headers"])
        assert resp.status_code == 400

    def test_barcode_lookup_requires_auth(self, client, setup, seeded_barcode):
        """Unauthenticated request should be rejected with 401."""
        resp = client.get(
            f"/api/v1/barcodes/lookup?value={seeded_barcode.barcode_value}"
        )
        assert resp.status_code == 401


class TestBarcodeRegister:

    def test_barcode_register_success(self, client, setup):
        """Register a valid barcode for a product - expect 201."""
        resp = client.post(
            "/api/v1/barcodes",
            json={
                "product_id": setup["product"].product_id,
                "barcode_value": "ABCD-1234",
                "barcode_type": "CODE128",
            },
            headers=setup["headers"],
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["barcode_value"] == "ABCD-1234"
        assert data["barcode_type"] == "CODE128"
        assert data["product_id"] == setup["product"].product_id

    def test_barcode_register_duplicate_rejected(self, client, setup, seeded_barcode):
        """Registering the same barcode_value twice should yield 409 on second attempt."""
        # First registration (same value as the fixture's seeded_barcode)
        resp1 = client.post(
            "/api/v1/barcodes",
            json={
                "product_id": setup["product"].product_id,
                "barcode_value": seeded_barcode.barcode_value,
                "barcode_type": "EAN13",
            },
            headers=setup["headers"],
        )
        assert resp1.status_code == 409
        body = resp1.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "CONFLICT"

    def test_barcode_register_invalid_value(self, client, setup):
        """Values with special chars or too short should fail validation (400)."""
        # Too short
        resp = client.post(
            "/api/v1/barcodes",
            json={"product_id": setup["product"].product_id, "barcode_value": "AB"},
            headers=setup["headers"],
        )
        assert resp.status_code == 400

        # Contains invalid character $
        resp2 = client.post(
            "/api/v1/barcodes",
            json={"product_id": setup["product"].product_id, "barcode_value": "ABCD$1234"},
            headers=setup["headers"],
        )
        assert resp2.status_code == 400

    def test_barcode_register_missing_product_id(self, client, setup):
        """Missing product_id should return 400."""
        resp = client.post(
            "/api/v1/barcodes",
            json={"barcode_value": "VALID-1234"},
            headers=setup["headers"],
        )
        assert resp.status_code == 400

    def test_barcode_register_wrong_store_product(self, client, setup):
        """Product from a different store should return 404."""
        other_store = Store(store_name="Other Store", store_type="grocery")
        db.session.add(other_store)
        db.session.commit()

        other_product = Product(
            store_id=other_store.store_id,
            name="Other Product",
            selling_price=10.0,
            cost_price=5.0,
            current_stock=10.0,
        )
        db.session.add(other_product)
        db.session.commit()

        resp = client.post(
            "/api/v1/barcodes",
            json={
                "product_id": other_product.product_id,
                "barcode_value": "VALID-5678",
            },
            headers=setup["headers"],
        )
        assert resp.status_code == 404


class TestBarcodeList:

    def test_list_barcodes_for_product(self, client, setup, seeded_barcode):
        """List barcodes for a known product should return the seeded barcode."""
        resp = client.get(
            f"/api/v1/barcodes?product_id={setup['product'].product_id}",
            headers=setup["headers"],
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["barcode_value"] == seeded_barcode.barcode_value

    def test_list_barcodes_missing_product_id(self, client, setup):
        """Missing product_id param should return 400."""
        resp = client.get("/api/v1/barcodes", headers=setup["headers"])
        assert resp.status_code == 400


class TestReceiptTemplate:

    def test_receipt_template_defaults(self, client, setup):
        """GET with no template set should return sensible defaults."""
        resp = client.get("/api/v1/receipts/template", headers=setup["headers"])
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["show_gstin"] is False
        assert data["paper_width_mm"] == 80
        assert data["id"] is None

    def test_receipt_template_upsert(self, client, setup):
        """PUT template, GET it back — all fields should match."""
        payload = {
            "header_text": "Welcome to Receipt Test Store",
            "footer_text": "No returns after 7 days",
            "show_gstin": True,
            "paper_width_mm": 58,
        }

        # First upsert (INSERT)
        put_resp = client.put(
            "/api/v1/receipts/template",
            json=payload,
            headers=setup["headers"],
        )
        assert put_resp.status_code == 200
        put_data = put_resp.get_json()["data"]
        assert put_data["header_text"] == payload["header_text"]
        assert put_data["footer_text"] == payload["footer_text"]
        assert put_data["show_gstin"] is True
        assert put_data["paper_width_mm"] == 58

        # GET back
        get_resp = client.get("/api/v1/receipts/template", headers=setup["headers"])
        assert get_resp.status_code == 200
        get_data = get_resp.get_json()["data"]
        assert get_data["header_text"] == payload["header_text"]
        assert get_data["footer_text"] == payload["footer_text"]
        assert get_data["show_gstin"] is True
        assert get_data["paper_width_mm"] == 58
        assert get_data["id"] is not None

        # Second upsert (UPDATE) — only change paper_width_mm
        put_resp2 = client.put(
            "/api/v1/receipts/template",
            json={"paper_width_mm": 80},
            headers=setup["headers"],
        )
        assert put_resp2.status_code == 200
        assert put_resp2.get_json()["data"]["paper_width_mm"] == 80
        # Other fields should remain unchanged
        assert put_resp2.get_json()["data"]["header_text"] == payload["header_text"]

    def test_receipt_template_requires_auth(self, client, setup):
        """Unauthenticated request should be rejected."""
        resp = client.get("/api/v1/receipts/template")
        assert resp.status_code == 401


class TestPrintJobs:

    def test_print_job_created(self, client, setup, seeded_transaction):
        """POST /receipts/print with valid transaction_id should return 201 + job_id."""
        resp = client.post(
            "/api/v1/receipts/print",
            json={
                "transaction_id": str(seeded_transaction.transaction_id),
                "printer_mac_address": "AA:BB:CC:DD:EE:FF",
            },
            headers=setup["headers"],
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert "job_id" in body["data"]
        assert isinstance(body["data"]["job_id"], int)

    def test_print_job_created_without_transaction(self, client, setup):
        """POST /receipts/print without a transaction_id should also return 201."""
        resp = client.post(
            "/api/v1/receipts/print",
            json={"printer_mac_address": "11:22:33:44:55:66"},
            headers=setup["headers"],
        )
        assert resp.status_code == 201
        assert "job_id" in resp.get_json()["data"]

    def test_print_job_poll(self, client, setup, seeded_transaction):
        """Create a job then GET its status — should return PENDING."""
        # Create the job
        create_resp = client.post(
            "/api/v1/receipts/print",
            json={"transaction_id": str(seeded_transaction.transaction_id)},
            headers=setup["headers"],
        )
        assert create_resp.status_code == 201
        job_id = create_resp.get_json()["data"]["job_id"]

        # Poll status
        poll_resp = client.get(
            f"/api/v1/receipts/print/{job_id}",
            headers=setup["headers"],
        )
        assert poll_resp.status_code == 200
        data = poll_resp.get_json()["data"]
        assert data["job_id"] == job_id
        assert data["status"] == "PENDING"
        assert data["transaction_id"] == str(seeded_transaction.transaction_id)

    def test_print_job_not_found(self, client, setup):
        """Polling a non-existent job_id should return 404."""
        resp = client.get("/api/v1/receipts/print/999999", headers=setup["headers"])
        assert resp.status_code == 404

    def test_print_job_invalid_transaction(self, client, setup):
        """POST with a transaction_id that doesn't belong to this store should return 404."""
        resp = client.post(
            "/api/v1/receipts/print",
            json={"transaction_id": str(uuid.uuid4())},
            headers=setup["headers"],
        )
        assert resp.status_code == 404

    def test_print_job_requires_auth(self, client, setup):
        """Unauthenticated request should be rejected."""
        resp = client.post("/api/v1/receipts/print", json={})
        assert resp.status_code == 401


class TestReceiptFormatter:

    def test_build_receipt_payload_structure(self, app, setup, seeded_transaction):
        """Unit test formatter.py directly — all required keys must be present."""
        with app.app_context():
            payload = build_receipt_payload(
                transaction_id=seeded_transaction.transaction_id,
                store_id=setup["store"].store_id,
                db_session=db.session,
            )

        # Check all required top-level keys
        required_keys = {
            "store_name",
            "store_address",
            "items",
            "subtotal",
            "discount_total",
            "tax_total",
            "grand_total",
            "payment_mode",
            "timestamp",
            "transaction_ref",
            "header_text",
            "footer_text",
        }
        for key in required_keys:
            assert key in payload, f"Missing key: {key}"

        # Check items structure
        assert isinstance(payload["items"], list)
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        for item_key in ("name", "qty", "unit_price", "line_total"):
            assert item_key in item, f"Missing item key: {item_key}"

        # Check numeric correctness (3 items @ 40.0 each, no discount)
        assert payload["subtotal"] == pytest.approx(120.0)
        assert payload["discount_total"] == pytest.approx(0.0)
        assert payload["grand_total"] == pytest.approx(120.0)
        assert payload["payment_mode"] == "CASH"
        assert payload["transaction_ref"] == str(seeded_transaction.transaction_id)
        assert payload["store_name"] == setup["store"].store_name

    def test_build_receipt_payload_with_template(self, app, setup, seeded_transaction):
        """Formatter should include header/footer from receipt template when set."""
        with app.app_context():
            template = ReceiptTemplate(
                store_id=setup["store"].store_id,
                header_text="Test Header",
                footer_text="Test Footer",
                show_gstin=True,
                paper_width_mm=80,
            )
            db.session.add(template)
            db.session.commit()

            payload = build_receipt_payload(
                transaction_id=seeded_transaction.transaction_id,
                store_id=setup["store"].store_id,
                db_session=db.session,
            )

        assert payload["header_text"] == "Test Header"
        assert payload["footer_text"] == "Test Footer"
        # GSTIN from store (gst_number="27AAAPL1234C1ZV") should be included
        assert "gstin" in payload
        assert payload["gstin"] == "27AAAPL1234C1ZV"

    def test_build_receipt_payload_invalid_transaction(self, app, setup):
        """build_receipt_payload should raise ValueError for unknown transaction."""
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                build_receipt_payload(
                    transaction_id=uuid.uuid4(),
                    store_id=setup["store"].store_id,
                    db_session=db.session,
                )
