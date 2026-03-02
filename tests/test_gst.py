"""
Tests for GST: Schema, HSN Master, and GSTR-1 Generation (Prompt 7.B)
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import db
from app.gst.utils import validate_gstin
from app.models import (
    Category,
    GSTFilingPeriod,
    GSTTransaction,
    HSNMaster,
    Product,
    StoreGSTConfig,
    Transaction,
    TransactionItem,
)
from app.transactions.services import process_single_transaction

# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def mock_celery_task_session(monkeypatch):
    @contextmanager
    def mock_session(*args, **kwargs):
        yield db.session
        db.session.commit()
    monkeypatch.setattr('app.tasks.tasks.task_session', mock_session)


@pytest.fixture
def hsn_entry(app):
    """Seed a single HSN code for testing."""
    entry = HSNMaster(hsn_code='8517', description='Telephones, smartphones', default_gst_rate=18)
    db.session.add(entry)
    db.session.commit()
    return entry


@pytest.fixture
def hsn_biscuit(app):
    entry = HSNMaster(hsn_code='1905', description='Biscuits, cakes, pastry', default_gst_rate=12)
    db.session.add(entry)
    db.session.commit()
    return entry


@pytest.fixture
def gst_enabled_store(app, test_store):
    """Enable GST for the test store."""
    config = StoreGSTConfig(
        store_id=test_store.store_id,
        gstin='27AAPFU0939F1ZV',
        registration_type='REGULAR',
        state_code='27',
        is_gst_enabled=True
    )
    db.session.add(config)
    db.session.commit()
    return config


@pytest.fixture
def gst_product(app, test_store, test_category, hsn_entry):
    """Product linked to an HSN code (smartphones, 18% GST)."""
    product = Product(
        store_id=test_store.store_id,
        category_id=test_category.category_id,
        name='Smartphone X',
        selling_price=11800.0,
        cost_price=8000.0,
        current_stock=100.0,
        hsn_code='8517',
        gst_category='REGULAR'
    )
    db.session.add(product)
    db.session.commit()
    return product


# ── a. test_gstin_validator_valid ────────────────────────────────────

def test_gstin_validator_valid(app):
    # Known-good test GSTIN with correct checksum
    assert validate_gstin('27AAPFU0939F1ZV') is True


# ── b. test_gstin_validator_invalid_checksum ──────────────────────────

def test_gstin_validator_invalid_checksum(app):
    # Correct format but wrong checksum character (V -> X)
    assert validate_gstin('27AAPFU0939F1ZX') is False
    # Too short
    assert validate_gstin('27AAPFU0939F1Z') is False
    # Invalid state code
    assert validate_gstin('99AAPFU0939F1ZV') is False


# ── c. test_gst_transaction_created_on_sale ──────────────────────────

def test_gst_transaction_created_on_sale(app, test_store, gst_enabled_store, gst_product):
    txn_data = {
        'transaction_id': uuid.uuid4(),
        'timestamp': datetime.now(timezone.utc),
        'payment_mode': 'CASH',
        'line_items': [
            {'product_id': gst_product.product_id, 'quantity': 1, 'selling_price': 11800.0}
        ]
    }

    txn = process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    gst_row = db.session.query(GSTTransaction).filter_by(transaction_id=txn.transaction_id).first()
    assert gst_row is not None
    assert gst_row.store_id == test_store.store_id
    assert gst_row.period == datetime.now(timezone.utc).strftime('%Y-%m')
    assert gst_row.hsn_breakdown is not None
    assert '8517' in gst_row.hsn_breakdown


# ── d. test_intrastate_split ──────────────────────────────────────────

def test_intrastate_split(app, test_store, gst_enabled_store, gst_product):
    txn_data = {
        'transaction_id': uuid.uuid4(),
        'timestamp': datetime.now(timezone.utc),
        'payment_mode': 'CASH',
        'line_items': [
            {'product_id': gst_product.product_id, 'quantity': 1, 'selling_price': 11800.0}
        ]
    }

    txn = process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    gst_row = db.session.query(GSTTransaction).filter_by(transaction_id=txn.transaction_id).first()
    assert gst_row is not None

    # For 18% GST on 11800: taxable = 11800 / 1.18 = 10000, tax = 1800
    # CGST = SGST = 900 each
    total_gst = float(gst_row.total_gst)
    cgst = float(gst_row.cgst_amount)
    sgst = float(gst_row.sgst_amount)

    assert abs(cgst - sgst) < 0.01, f"CGST ({cgst}) should equal SGST ({sgst})"
    assert abs(total_gst - cgst - sgst) < 0.01
    assert abs(cgst - 900.0) < 0.01
    assert abs(sgst - 900.0) < 0.01
    assert float(gst_row.igst_amount) == 0


# ── e. test_hsn_search_returns_matches ────────────────────────────────

def test_hsn_search_returns_matches(app, client, owner_headers, hsn_entry, hsn_biscuit):
    # Search by code prefix
    resp = client.get('/api/v1/gst/hsn-search?q=85', headers=owner_headers)
    assert resp.status_code == 200
    data = resp.json['data']
    assert len(data) >= 1
    assert any(d['hsn_code'] == '8517' for d in data)

    # Search by description (ILIKE)
    resp = client.get('/api/v1/gst/hsn-search?q=biscuit', headers=owner_headers)
    assert resp.status_code == 200
    data = resp.json['data']
    assert len(data) >= 1
    assert any(d['hsn_code'] == '1905' for d in data)


# ── f. test_gst_liability_slab_breakdown ──────────────────────────────

def test_gst_liability_slab_breakdown(app, client, owner_headers, test_store, gst_enabled_store, gst_product, hsn_biscuit):
    # Create a second product at 12% rate
    biscuit = Product(
        store_id=test_store.store_id,
        name='Biscuit Pack',
        selling_price=112.0,
        cost_price=70.0,
        current_stock=100.0,
        hsn_code='1905',
        gst_category='REGULAR'
    )
    db.session.add(biscuit)
    db.session.commit()

    period = datetime.now(timezone.utc).strftime('%Y-%m')

    # Transaction with smartphone (18%) and biscuit (12%)
    txn_data = {
        'transaction_id': uuid.uuid4(),
        'timestamp': datetime.now(timezone.utc),
        'payment_mode': 'CASH',
        'line_items': [
            {'product_id': gst_product.product_id, 'quantity': 1, 'selling_price': 11800.0},
            {'product_id': biscuit.product_id, 'quantity': 1, 'selling_price': 112.0},
        ]
    }
    process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    resp = client.get(f'/api/v1/gst/liability-slabs?period={period}', headers=owner_headers)
    assert resp.status_code == 200
    slabs = resp.json['data']
    assert len(slabs) >= 2

    rates = [s['rate'] for s in slabs]
    assert 12.0 in rates
    assert 18.0 in rates


# ── g. test_monthly_compilation_task ──────────────────────────────────

def test_monthly_compilation_task(app, test_store, gst_enabled_store, gst_product, mock_celery_task_session):
    import json

    from app.tasks.tasks import compile_monthly_gst

    period = datetime.now(timezone.utc).strftime('%Y-%m')

    # Seed 5 transactions
    for _i in range(5):
        txn_data = {
            'transaction_id': uuid.uuid4(),
            'timestamp': datetime.now(timezone.utc),
            'payment_mode': 'CASH',
            'line_items': [
                {'product_id': gst_product.product_id, 'quantity': 1, 'selling_price': 11800.0}
            ]
        }
        process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    # Run compilation task
    compile_monthly_gst(test_store.store_id, period)

    # Assert filing period created
    db.session.expire_all()
    filing = db.session.query(GSTFilingPeriod).filter_by(store_id=test_store.store_id, period=period).first()
    assert filing is not None
    assert filing.invoice_count == 5
    assert filing.status == 'COMPILED'
    assert filing.compiled_at is not None

    # Verify totals: 5 x 11800 total, each has taxable=10000, cgst=900, sgst=900
    assert abs(float(filing.total_taxable) - 50000.0) < 1
    assert abs(float(filing.total_cgst) - 4500.0) < 1
    assert abs(float(filing.total_sgst) - 4500.0) < 1

    # Verify GSTR-1 JSON was written
    assert filing.gstr1_json_path is not None
    import os
    assert os.path.exists(filing.gstr1_json_path)
    with open(filing.gstr1_json_path) as f:
        gstr1 = json.load(f)
    assert gstr1['gstin'] == '27AAPFU0939F1ZV'
    assert len(gstr1['hsn']['data']) >= 1


# ── h. test_gst_disabled_store_no_gst_row ─────────────────────────────

def test_gst_disabled_store_no_gst_row(app, test_store, test_product):
    """Record transaction on a non-GST store, assert no gst_transactions row."""
    txn_data = {
        'transaction_id': uuid.uuid4(),
        'timestamp': datetime.now(timezone.utc),
        'payment_mode': 'CASH',
        'line_items': [
            {'product_id': test_product.product_id, 'quantity': 2, 'selling_price': 100.0}
        ]
    }

    txn = process_single_transaction(txn_data, test_store.store_id)
    db.session.commit()

    gst_row = db.session.query(GSTTransaction).filter_by(transaction_id=txn.transaction_id).first()
    assert gst_row is None
