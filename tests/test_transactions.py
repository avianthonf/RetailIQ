import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles

from app import create_app, db
from app.auth.utils import generate_access_token
from app.models import Category, Product, Store, Transaction, TransactionItem, User


@compiles(JSONB, "sqlite")
def compile_jsonb(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid(type_, compiler, **kw):
    return "VARCHAR"


@pytest.fixture
def init_db(app):
    store = Store(store_name="Test Store")
    db.session.add(store)
    db.session.commit()

    owner = User(mobile_number="1234567890", role="owner", store_id=store.store_id, is_active=True)
    staff = User(mobile_number="0987654321", role="staff", store_id=store.store_id, is_active=True)
    db.session.add_all([owner, staff])

    cat = Category(store_id=store.store_id, name="Test Category")
    db.session.add(cat)
    db.session.commit()

    prod1 = Product(
        store_id=store.store_id,
        category_id=cat.category_id,
        name="Product 1",
        selling_price=10.0,
        current_stock=50.0,
        cost_price=5.0,
    )
    prod2 = Product(
        store_id=store.store_id,
        category_id=cat.category_id,
        name="Product 2",
        selling_price=20.0,
        current_stock=20.0,
        cost_price=10.0,
    )
    db.session.add_all([prod1, prod2])
    db.session.commit()

    return {"store": store, "owner": owner, "staff": staff, "prod1": prod1, "prod2": prod2}


@pytest.fixture
def auth_headers(app, init_db):
    owner_token = generate_access_token(init_db["owner"].user_id, init_db["store"].store_id, "owner")
    staff_token = generate_access_token(init_db["staff"].user_id, init_db["store"].store_id, "staff")
    return {"owner": {"Authorization": f"Bearer {owner_token}"}, "staff": {"Authorization": f"Bearer {staff_token}"}}


# --- TESTS ---


def test_single_sale(client, init_db, auth_headers):
    txn_id = str(uuid.uuid4())
    payload = {
        "transaction_id": txn_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": "CASH",
        "line_items": [{"product_id": init_db["prod1"].product_id, "quantity": 2.0, "selling_price": 10.0}],
    }

    resp = client.post("/api/v1/transactions", json=payload, headers=auth_headers["staff"])
    assert resp.status_code == 201

    prod1 = db.session.get(Product, init_db["prod1"].product_id)
    assert float(prod1.current_stock) == 48.0

    txn = db.session.get(Transaction, uuid.UUID(txn_id))
    assert txn is not None
    assert txn.payment_mode == "CASH"


def test_batch_idempotent(client, init_db, auth_headers):
    txn_id_1 = str(uuid.uuid4())
    txn_id_2 = str(uuid.uuid4())

    payload = {
        "transactions": [
            {
                "transaction_id": txn_id_1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payment_mode": "CARD",
                "line_items": [{"product_id": init_db["prod2"].product_id, "quantity": 1.0, "selling_price": 20.0}],
            },
            {
                "transaction_id": txn_id_2,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payment_mode": "UPI",
                "line_items": [{"product_id": init_db["prod1"].product_id, "quantity": 5.0, "selling_price": 10.0}],
            },
        ]
    }

    resp = client.post("/api/v1/transactions/batch", json=payload, headers=auth_headers["owner"])
    assert resp.status_code == 200
    assert resp.json["data"]["accepted"] == 2

    txn_id_3 = str(uuid.uuid4())
    payload["transactions"].append(
        {
            "transaction_id": txn_id_3,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payment_mode": "CASH",
            "line_items": [{"product_id": init_db["prod1"].product_id, "quantity": 2.0, "selling_price": 10.0}],
        }
    )

    resp2 = client.post("/api/v1/transactions/batch", json=payload, headers=auth_headers["owner"])
    assert resp2.status_code == 200
    assert resp2.json["data"]["accepted"] == 1
    assert resp2.json["data"]["errors"] == []

    prod2 = db.session.get(Product, init_db["prod2"].product_id)
    assert float(prod2.current_stock) == 19.0


def test_staff_date_restriction(client, init_db, auth_headers):
    old_txn = Transaction(
        transaction_id=uuid.uuid4(),
        store_id=init_db["store"].store_id,
        payment_mode="CASH",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        is_return=False,
    )
    db.session.add(old_txn)

    new_txn = Transaction(
        transaction_id=uuid.uuid4(),
        store_id=init_db["store"].store_id,
        payment_mode="UPI",
        created_at=datetime.now(timezone.utc),
        is_return=False,
    )
    db.session.add(new_txn)
    db.session.commit()

    resp = client.get("/api/v1/transactions", headers=auth_headers["owner"])
    assert len(resp.json["data"]) == 2

    resp_staff = client.get("/api/v1/transactions", headers=auth_headers["staff"])
    assert len(resp_staff.json["data"]) == 1
    assert resp_staff.json["data"][0]["payment_mode"] == "UPI"


def test_batch_transaction_partial_failure(app, client, init_db, auth_headers):
    """
    Verify that if one transaction in a batch fails (e.g., product not found),
    other valid transactions in the same batch still succeed (begin_nested isolation).
    """
    txn_id_valid = str(uuid.uuid4())
    txn_id_invalid = str(uuid.uuid4())
    
    payload = {
        "transactions": [
            {
                "transaction_id": txn_id_valid,
                "payment_mode": "CASH",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "line_items": [{"product_id": str(init_db["prod1"].product_id), "quantity": 1, "selling_price": 10.0}]
            },
            {
                "transaction_id": txn_id_invalid,
                "payment_mode": "CASH",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "line_items": [{"product_id": 999999, "quantity": 1, "selling_price": 10.0}] # Invalid product
            }
        ]
    }
    
    resp = client.post("/api/v1/transactions/batch", json=payload, headers=auth_headers["staff"])
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    
    assert data["accepted"] == 1
    assert data["rejected"] == 1
    assert len(data["errors"]) == 1
    assert data["errors"][0]["transaction_id"] == txn_id_invalid
    
    # Verify the valid one was actually committed
    with app.app_context():
        txn = db.session.get(Transaction, uuid.UUID(txn_id_valid))
        assert txn is not None


def test_return_transaction(client, init_db, auth_headers):
    txn_id = str(uuid.uuid4())
    payload = {
        "transaction_id": txn_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": "CASH",
        "line_items": [{"product_id": init_db["prod1"].product_id, "quantity": 10.0, "selling_price": 10.0}],
    }
    client.post("/api/v1/transactions", json=payload, headers=auth_headers["staff"])
    prod1 = db.session.get(Product, init_db["prod1"].product_id)
    assert float(prod1.current_stock) == 40.0

    return_payload = {"items": [{"product_id": init_db["prod1"].product_id, "quantity_returned": 2.0}]}
    resp = client.post(f"/api/v1/transactions/{txn_id}/return", json=return_payload, headers=auth_headers["staff"])
    assert resp.status_code == 403

    resp_owner = client.post(
        f"/api/v1/transactions/{txn_id}/return", json=return_payload, headers=auth_headers["owner"]
    )
    assert resp_owner.status_code == 201

    prod1 = db.session.get(Product, init_db["prod1"].product_id)
    assert float(prod1.current_stock) == 42.0
