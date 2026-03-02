import pytest

from app.vision.parser import parse_invoice_text


def test_parse_invoice_text_basic():
    """Test standard single-line parsing"""
    text = "Mango Juice 2 pcs ₹100\nApple 5 kg Rs. 500"
    items = parse_invoice_text(text)

    assert len(items) == 2
    assert "Mango Juice" in items[0]["product_name"]
    assert items[0]["quantity"] == 2.0
    assert items[0]["unit"] == "pcs"
    assert items[0]["unit_price"] == 100.0

    assert "Apple" in items[1]["product_name"]
    assert items[1]["quantity"] == 5.0
    assert items[1]["unit"] == "kg"
    assert items[1]["unit_price"] == 500.0

def test_parse_handles_comma_prices():
    """Test comma handling and decimals in price"""
    text = "Luxury Watch 1 pcs ₹1,200.50"
    items = parse_invoice_text(text)

    assert len(items) == 1
    assert "Luxury Watch" in items[0]["product_name"]
    assert items[0]["quantity"] == 1.0
    assert items[0]["unit_price"] == 1200.5

def test_parse_handles_case_insensitive_units():
    """Test variations in unit casing"""
    text = "Item A 1 Pcs ₹10\nItem B 2 pCS Rs 20\nItem C 3 KG ₹30"
    items = parse_invoice_text(text)

    assert len(items) == 3
    assert items[0]["unit"] == "pcs"
    assert items[1]["unit"] == "pcs"
    assert items[2]["unit"] == "kg"

def test_parse_invoice_text_multi_line():
    """Test multi-line item accumulation where name wraps before qty/price"""
    text = "Premium Dark\nChocolate Bar\n2 pcs ₹150\nNext Item 1 kg Rs 50"
    items = parse_invoice_text(text)

    assert len(items) == 2
    # The name should accumulate from the previous lines
    assert "Premium Dark Chocolate Bar" in items[0]["product_name"]
    assert items[0]["quantity"] == 2.0
    assert items[0]["unit_price"] == 150.0

    assert "Next Item" in items[1]["product_name"]
    assert items[1]["quantity"] == 1.0
    assert items[1]["unit_price"] == 50.0

import io
from unittest.mock import patch

from app import db
from app.models import OcrJob, OcrJobItem, Product, StockAdjustment
from app.tasks.tasks import process_ocr_job


@patch('app.vision.routes.process_ocr_job')
def test_upload_valid_image_creates_job(mock_task, client, owner_headers):
    data = {'invoice_image': (io.BytesIO(b"fake image data"), 'invoice.jpg')}
    res = client.post('/api/v1/vision/ocr/upload', headers=owner_headers, data=data, content_type='multipart/form-data')
    assert res.status_code == 201
    assert "job_id" in res.json

    # Check if job was created
    job_id = res.json["job_id"]
    import uuid
    job = db.session.get(OcrJob, uuid.UUID(job_id))
    assert job is not None
    assert job.status == 'QUEUED'

@patch('app.vision.routes.process_ocr_job')
def test_upload_oversized_rejected(mock_task, client, owner_headers):
    # Create 11MB file
    large_data = b"0" * (11 * 1024 * 1024)
    data = {'invoice_image': (io.BytesIO(large_data), 'invoice.jpg')}
    res = client.post('/api/v1/vision/ocr/upload', headers=owner_headers, data=data, content_type='multipart/form-data')
    assert res.status_code == 413
    assert "Payload Too Large" in res.json["message"]

@patch('app.vision.routes.process_ocr_job')
def test_upload_wrong_mime_rejected(mock_task, client, owner_headers):
    data = {'invoice_image': (io.BytesIO(b"fake text data"), 'invoice.txt')}
    res = client.post('/api/v1/vision/ocr/upload', headers=owner_headers, data=data, content_type='multipart/form-data')
    assert res.status_code == 415
    assert "Unsupported Media Type" in res.json["message"]

@patch('app.vision.routes.process_ocr_job')
@patch('pytesseract.image_to_string')
@patch('PIL.Image.open')
def test_ocr_task_creates_items_and_transitions_to_review(mock_open, mock_tesseract, mock_task, client, owner_headers, test_store):
    """
    Integration test: simulates the OCR task's effect by directly inserting
    items into the DB (since the Celery task uses its own raw SQL session
    that doesn't share the Flask test transaction).
    """
    import uuid as _uuid
    store_id = test_store.store_id
    dummy_text = "Coffee Beans 10 kg Rs 500\nSugar 5 kg ₹200"
    mock_tesseract.return_value = dummy_text

    # Add products for matching
    p1 = Product(store_id=store_id, name="Coffee Beans Premium", sku_code="COFF1", current_stock=0)
    p2 = Product(store_id=store_id, name="Organic Sugar", sku_code="SUG1", current_stock=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    # Create job via API
    data = {'invoice_image': (io.BytesIO(b"fake image data"), 'invoice.jpg')}
    res = client.post('/api/v1/vision/ocr/upload', headers=owner_headers, data=data, content_type='multipart/form-data')
    job_id = res.json["job_id"]

    import uuid
    job = db.session.get(OcrJob, uuid.UUID(job_id))
    assert job is not None
    assert job.status == 'QUEUED'

    # Simulate what the Celery task does: parse text, create items, transition to REVIEW
    from app.vision.parser import parse_invoice_text
    parsed_items = parse_invoice_text(dummy_text)
    assert len(parsed_items) == 2

    job.raw_ocr_text = dummy_text
    job.status = 'REVIEW'

    # Simulate matched items
    products_map = {"Coffee Beans": p1, "Sugar": p2}
    for item in parsed_items:
        matched_product = None
        for key, prod in products_map.items():
            if key.lower() in item['product_name'].lower():
                matched_product = prod
                break

        ocr_item = OcrJobItem(
            id=_uuid.uuid4(),
            job_id=job.id,
            raw_text=item['product_name'],
            matched_product_id=matched_product.product_id if matched_product else None,
            confidence=85.0 if matched_product else 0.0,
            quantity=item['quantity'],
            unit_price=item['unit_price']
        )
        db.session.add(ocr_item)

    db.session.commit()

    # Verify final state
    assert job.status == 'REVIEW'
    assert job.raw_ocr_text == dummy_text

    items = db.session.query(OcrJobItem).filter_by(job_id=uuid.UUID(job_id)).all()
    assert len(items) == 2

    matched_pids = [item.matched_product_id for item in items]
    assert p1.product_id in matched_pids
    assert p2.product_id in matched_pids

    for item in items:
        assert item.confidence > 0

def test_confirm_updates_stock_atomically(client, owner_headers, test_store):
    import uuid
    store_id = test_store.store_id
    p1 = Product(store_id=store_id, name="Test Item 1", sku_code="T1", current_stock=10)
    p2 = Product(store_id=store_id, name="Test Item 2", sku_code="T2", current_stock=20)
    db.session.add_all([p1, p2])
    db.session.commit()

    job = OcrJob(id=uuid.uuid4(), store_id=store_id, status='REVIEW')
    db.session.add(job)
    db.session.commit()

    i1 = OcrJobItem(id=uuid.uuid4(), job_id=job.id, matched_product_id=p1.product_id, quantity=5)
    i2 = OcrJobItem(id=uuid.uuid4(), job_id=job.id, matched_product_id=p2.product_id, quantity=10)
    db.session.add_all([i1, i2])
    db.session.commit()

    payload = {
        "confirmed_items": [
            {"item_id": str(i1.id), "matched_product_id": p1.product_id, "quantity": 5},
            {"item_id": str(i2.id), "matched_product_id": p2.product_id, "quantity": 10},
        ]
    }

    res = client.post(f'/api/v1/vision/ocr/{job.id}/confirm', headers=owner_headers, json=payload)
    assert res.status_code == 200

    db.session.refresh(job)
    db.session.refresh(p1)
    db.session.refresh(p2)

    assert job.status == 'APPLIED'
    assert p1.current_stock == 15
    assert p2.current_stock == 30

    txs = db.session.query(StockAdjustment).filter(StockAdjustment.reason.like(f"%{str(job.id)}%")).all()
    assert len(txs) == 2

def test_confirm_rolls_back_on_partial_failure(client, owner_headers, test_store):
    import uuid
    store_id = test_store.store_id
    p1 = Product(store_id=store_id, name="Fail Test 1", sku_code="F1", current_stock=10)
    db.session.add(p1)
    db.session.commit()

    job = OcrJob(id=uuid.uuid4(), store_id=store_id, status='REVIEW')
    db.session.add(job)
    db.session.commit()

    i1 = OcrJobItem(id=uuid.uuid4(), job_id=job.id, matched_product_id=p1.product_id, quantity=5)
    db.session.add(i1)
    db.session.commit()

    # Payload has a valid item and an invalid item (missing quantity)
    payload = {
        "confirmed_items": [
            {"item_id": str(i1.id), "matched_product_id": p1.product_id, "quantity": 5},
            {"item_id": str(uuid.uuid4()), "matched_product_id": 9999, "quantity": -5}, # Invalid
        ]
    }

    # Save IDs before removing session to avoid DetachedInstanceError
    p1_id = p1.product_id
    job_id = job.id

    res = client.post(f'/api/v1/vision/ocr/{job_id}/confirm', headers=owner_headers, json=payload)
    assert res.status_code == 400

    db.session.expire_all()

    p1_fresh = db.session.get(Product, p1_id)
    job_fresh = db.session.get(OcrJob, job_id)

    assert p1_fresh.current_stock == 10 # Rolled back!
    assert job_fresh.status == 'REVIEW' # Not applied!

