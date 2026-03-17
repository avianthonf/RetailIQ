import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.auth.utils import generate_access_token
from app.models import Category, Product, StaffSession, Store, Transaction, TransactionItem, User


@pytest.fixture
def transactions_data(app, test_store, test_owner, test_staff, test_product):
    store_id = test_store.store_id
    owner_id = test_owner.user_id
    staff_id = test_staff.user_id

    # Create an open staff session
    session = StaffSession(store_id=store_id, user_id=staff_id, status="OPEN")
    db.session.add(session)
    db.session.commit()

    # Create some historical transactions
    for i in range(5):
        dt = datetime.now(timezone.utc) - timedelta(days=i)
        txn = Transaction(
            transaction_id=uuid.uuid4(),
            store_id=store_id,
            payment_mode="CASH" if i % 2 == 0 else "CARD",
            created_at=dt,
            total_amount=100.0 * (i + 1),
            is_return=False,
        )
        db.session.add(txn)
        db.session.flush()

        item = TransactionItem(
            transaction_id=txn.transaction_id,
            product_id=test_product.product_id,
            quantity=i + 1,
            selling_price=100.0,
            cost_price_at_time=50.0,
        )
        db.session.add(item)

    db.session.commit()
    return {"session_id": session.id}


def test_create_transaction_validation_error(client, owner_headers):
    resp = client.post("/api/v1/transactions/", json={"invalid": "data"}, headers=owner_headers)
    assert resp.status_code == 422


def test_create_transaction_staff_session(client, test_product, staff_headers, transactions_data):
    # Test that staff transaction associates with open session
    txn_id = str(uuid.uuid4())
    payload = {
        "transaction_id": txn_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": "CASH",
        "line_items": [{"product_id": test_product.product_id, "quantity": 1.0, "selling_price": 10.0}],
    }
    resp = client.post("/api/v1/transactions/", json=payload, headers=staff_headers)
    assert resp.status_code == 201

    txn = db.session.get(Transaction, uuid.UUID(txn_id))
    assert txn.session_id == transactions_data["session_id"]


def test_create_batch_validation_error(client, owner_headers):
    resp = client.post("/api/v1/transactions/batch/", json={"transactions": "not a list"}, headers=owner_headers)
    assert resp.status_code == 422


def test_get_transactions_filters(client, owner_headers, transactions_data):
    # Test filtering by payment_mode
    resp = client.get("/api/v1/transactions/?payment_mode=CARD", headers=owner_headers)
    assert resp.status_code == 200
    for txn in resp.json["data"]:
        assert txn["payment_mode"] == "CARD"

    # Test filtering by amount
    resp = client.get("/api/v1/transactions/?min_amount=250&max_amount=450", headers=owner_headers)
    assert resp.status_code == 200
    # The totals in our mock data are 100, 200, 300, 400, 500
    assert len(resp.json["data"]) == 2  # 300 and 400

    # Test date filtering
    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(f"/api/v1/transactions/?start_date={today}", headers=owner_headers)
    assert resp.status_code == 200
    assert len(resp.json["data"]) >= 1


def test_get_single_transaction_not_found(client, owner_headers):
    resp = client.get(f"/api/v1/transactions/{uuid.uuid4()}", headers=owner_headers)
    assert resp.status_code == 404
    assert resp.json["message"] == "Transaction not found"


def test_get_single_transaction_success(client, test_store, owner_headers, transactions_data):
    # Get the latest transaction we created in transactions_data
    txn = db.session.query(Transaction).filter_by(store_id=test_store.store_id).first()
    resp = client.get(f"/api/v1/transactions/{txn.transaction_id}", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["transaction_id"] == str(txn.transaction_id)
    assert len(resp.json["data"]["line_items"]) > 0


def test_return_transaction_validation_error(client, owner_headers, transactions_data):
    txn = db.session.query(Transaction).first()
    resp = client.post(f"/api/v1/transactions/{txn.transaction_id}/return", json={}, headers=owner_headers)
    assert resp.status_code == 422


def test_get_daily_summary_success(client, owner_headers, transactions_data):
    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(f"/api/v1/transactions/summary/daily?date={today}", headers=owner_headers)
    assert resp.status_code == 200
    assert "revenue_by_payment_mode" in resp.json["data"]
    assert "top_5_products" in resp.json["data"]
    assert resp.json["data"]["transaction_count"] >= 1


def test_get_daily_summary_invalid_date(client, owner_headers):
    resp = client.get("/api/v1/transactions/summary/daily?date=invalid-date", headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json["error"]["code"] == "INVALID_DATE"


def test_create_batch_staff_session(client, test_product, staff_headers, transactions_data):
    payload = {
        "transactions": [
            {
                "transaction_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payment_mode": "CASH",
                "line_items": [{"product_id": test_product.product_id, "quantity": 1.0, "selling_price": 10.0}],
            }
        ]
    }
    resp = client.post("/api/v1/transactions/batch/", json=payload, headers=staff_headers)
    assert resp.status_code == 200

    txn_id = uuid.UUID(payload["transactions"][0]["transaction_id"])
    txn = db.session.get(Transaction, txn_id)
    assert txn.session_id == transactions_data["session_id"]


def test_get_transactions_more_filters(client, owner_headers, transactions_data):
    # Test end_date and customer_id
    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(f"/api/v1/transactions/?end_date={today}&customer_id=99", headers=owner_headers)
    assert resp.status_code == 200


def test_return_summary_logic(client, test_store, owner_headers, transactions_data):
    # Create a return transaction to cover summary logic lines 280-281
    txn = db.session.query(Transaction).filter_by(store_id=test_store.store_id, is_return=False).first()
    item = db.session.query(TransactionItem).filter_by(transaction_id=txn.transaction_id).first()
    payload = {"items": [{"product_id": item.product_id, "quantity_returned": 1.0}]}
    client.post(f"/api/v1/transactions/{txn.transaction_id}/return", json=payload, headers=owner_headers)

    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(f"/api/v1/transactions/summary/daily?date={today}", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["returns_count"] >= 1


def test_create_transaction_error_paths(client, owner_headers, monkeypatch):
    # Mock services.process_single_transaction to raise ValueError with "Credit limit"
    from app.transactions import routes

    def mock_process_error(*args, **kwargs):
        raise ValueError("Credit limit exceeded")

    monkeypatch.setattr(routes, "process_single_transaction", mock_process_error)

    payload = {
        "transaction_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": "CASH",
        "line_items": [{"product_id": 1, "quantity": 1.0, "selling_price": 10.0}],
    }
    resp = client.post("/api/v1/transactions/", json=payload, headers=owner_headers)
    assert resp.status_code == 422
    assert "Credit limit" in resp.json["message"]

    # Test generic server error
    def mock_server_error(*args, **kwargs):
        raise Exception("Unexpected error")

    monkeypatch.setattr(routes, "process_single_transaction", mock_server_error)
    resp = client.post("/api/v1/transactions/", json=payload, headers=owner_headers)
    assert resp.status_code == 500


def test_return_transaction_error_paths(client, owner_headers, monkeypatch):
    from app.transactions import routes

    # Mock return_transaction_service to raise ValueError
    def mock_return_error(*args, **kwargs):
        raise ValueError("Invalid return")

    monkeypatch.setattr(routes, "process_return_transaction", mock_return_error)

    resp = client.post(f"/api/v1/transactions/{uuid.uuid4()}/return", json={"items": []}, headers=owner_headers)
    # Validation error comes first if items is empty, let's use valid items
    resp = client.post(
        f"/api/v1/transactions/{uuid.uuid4()}/return",
        json={"items": [{"product_id": 1, "quantity_returned": 1}]},
        headers=owner_headers,
    )
    assert resp.status_code == 422
    assert "Invalid return" in resp.json["message"]

    # Test generic server error
    def mock_server_error(*args, **kwargs):
        raise Exception("Fatal error")

    monkeypatch.setattr(routes, "process_return_transaction", mock_server_error)
    resp = client.post(
        f"/api/v1/transactions/{uuid.uuid4()}/return",
        json={"items": [{"product_id": 1, "quantity_returned": 1}]},
        headers=owner_headers,
    )
    assert resp.status_code == 500
