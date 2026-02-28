import pytest
import uuid
import sqlite3
from datetime import datetime, date, timedelta, timezone

sqlite3.register_adapter(uuid.UUID, lambda u: str(u))

from app import db as _db
from app.models import (
    Supplier, SupplierProduct, PurchaseOrder, PurchaseOrderItem,
    GoodsReceiptNote, Product, Alert, Store
)
from app.tasks.tasks import check_overdue_purchase_orders
from app.suppliers.analytics import compute_supplier_fill_rate

def _create_supplier(session, store_id, name="Test Supplier"):
    s = Supplier(store_id=store_id, name=name)
    session.add(s)
    session.commit()
    return s.id

def test_create_supplier(client, owner_headers, test_store):
    resp = client.post('/api/v1/suppliers', json={
        'name': 'New Supplier',
        'contact_name': 'Jane Doe'
    }, headers=owner_headers)
    assert resp.status_code == 201
    data = resp.get_json()['data']
    assert 'id' in data

def test_list_suppliers_scoped_to_store(app, client, owner_headers, test_store):
    with app.app_context():
        s_id1 = _create_supplier(_db.session, test_store.store_id, "Store 1 Supplier")
        
        # Create second store
        s2 = Store(store_name="Store 2")
        _db.session.add(s2)
        _db.session.commit()
        
        s_id2 = _create_supplier(_db.session, s2.store_id, "Store 2 Supplier")
        
    resp = client.get('/api/v1/suppliers', headers=owner_headers)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == "Store 1 Supplier"
    assert data[0]['id'] == str(s_id1)


def test_create_po_draft(app, client, owner_headers, test_store, test_product):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id)
        
    resp = client.post('/api/v1/purchase-orders', json={
        'supplier_id': str(sid),
        'items': [
            {'product_id': test_product.product_id, 'ordered_qty': 10, 'unit_price': 15.50}
        ]
    }, headers=owner_headers)
    assert resp.status_code == 201
    data = resp.get_json()['data']
    
    with app.app_context():
        po = _db.session.get(PurchaseOrder, uuid.UUID(data['id']))
        assert po.status == 'DRAFT'
        items = _db.session.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
        assert len(items) == 1
        assert items[0].ordered_qty == 10

def test_po_send_transition(app, client, owner_headers, test_store, test_product):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id)
        po = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='DRAFT')
        _db.session.add(po)
        _db.session.flush()
        poi = PurchaseOrderItem(po_id=po.id, product_id=test_product.product_id, ordered_qty=5, unit_price=10)
        _db.session.add(poi)
        _db.session.commit()
        po_id = str(po.id)
        
    resp = client.put(f'/api/v1/purchase-orders/{po_id}/send', headers=owner_headers)
    assert resp.status_code == 200
    
    with app.app_context():
        po = _db.session.get(PurchaseOrder, uuid.UUID(po_id))
        assert po.status == 'SENT'


def test_po_receive_updates_stock(app, client, owner_headers, test_store, test_product):
    with app.app_context():
        # setup product stock
        p = _db.session.get(Product, test_product.product_id)
        initial_stock = float(p.current_stock or 0.0)
        sid = _create_supplier(_db.session, test_store.store_id)
        po = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='SENT')
        _db.session.add(po)
        _db.session.flush()
        poi = PurchaseOrderItem(po_id=po.id, product_id=test_product.product_id, ordered_qty=10, unit_price=10)
        _db.session.add(poi)
        _db.session.commit()
        po_id = str(po.id)
        
    resp = client.post(f'/api/v1/purchase-orders/{po_id}/receive', json={
        'items': [{'product_id': test_product.product_id, 'received_qty': 5, 'unit_price': 10}]
    }, headers=owner_headers)
    assert resp.status_code == 200
    
    with app.app_context():
        p = _db.session.get(Product, test_product.product_id)
        assert float(p.current_stock) == initial_stock + 5.0
        
        # Verify GRN created
        grns = _db.session.query(GoodsReceiptNote).filter_by(po_id=uuid.UUID(po_id)).all()
        assert len(grns) == 1
        
        # PO should still be SENT because 5 < 10
        po = _db.session.get(PurchaseOrder, uuid.UUID(po_id))
        assert po.status == 'SENT'


def test_po_receive_is_atomic(app, client, owner_headers, test_store, test_product):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id)
        po = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='SENT')
        _db.session.add(po)
        _db.session.flush()
        poi = PurchaseOrderItem(po_id=po.id, product_id=test_product.product_id, ordered_qty=10, unit_price=10)
        _db.session.add(poi)
        _db.session.commit()
        po_id = str(po.id)
        
    # Send an invalid product_id to force the stock update to fail and test rollback
    resp = client.post(f'/api/v1/purchase-orders/{po_id}/receive', json={
        'items': [{'product_id': 999999, 'received_qty': 5, 'unit_price': 10}]
    }, headers=owner_headers)
    assert resp.status_code == 400
    
    with app.app_context():
        # GRN should not be created
        grns = _db.session.query(GoodsReceiptNote).filter_by(po_id=uuid.UUID(po_id)).all()
        assert len(grns) == 0
        # PO received_qty should remain 0
        poi = _db.session.query(PurchaseOrderItem).filter_by(po_id=uuid.UUID(po_id)).first()
        assert float(poi.received_qty or 0) == 0.0


def test_overdue_po_task_creates_alert(app, test_store):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id)
        today = date.today()
        po = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='SENT', expected_delivery_date=today - timedelta(days=2))
        _db.session.add(po)
        _db.session.commit()
        
        from unittest.mock import patch, MagicMock
        from contextlib import contextmanager

        @contextmanager
        def mock_task_session():
            yield _db.session
            
        with patch('app.tasks.tasks._RedisLock'), patch('app.tasks.tasks.task_session', new=mock_task_session):
            check_overdue_purchase_orders()
            
        alerts = _db.session.query(Alert).filter_by(
            store_id=test_store.store_id, alert_type='OVERDUE_PO'
        ).all()
        assert len(alerts) == 1
        assert 'overdue by 2 days' in alerts[0].message


def test_fill_rate_computation(app, test_store, test_product):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id)
        po = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='FULFILLED')
        _db.session.add(po)
        _db.session.flush()
        
        # ordered 10, received 8
        poi = PurchaseOrderItem(po_id=po.id, product_id=test_product.product_id, ordered_qty=10, received_qty=8, unit_price=10)
        _db.session.add(poi)
        
        po2 = PurchaseOrder(store_id=test_store.store_id, supplier_id=sid, status='FULFILLED')
        _db.session.add(po2)
        _db.session.flush()
        # ordered 10, received 10
        poi2 = PurchaseOrderItem(po_id=po2.id, product_id=test_product.product_id, ordered_qty=10, received_qty=10, unit_price=10)
        _db.session.add(poi2)
        
        _db.session.commit()
        
        rate = compute_supplier_fill_rate(sid, test_store.store_id, 90, _db)
        assert rate == 0.90 # (8+10) / (10+10)


def test_supplier_soft_delete(app, client, owner_headers, test_store):
    with app.app_context():
        sid = _create_supplier(_db.session, test_store.store_id, "Delete Me")
        
    resp = client.delete(f'/api/v1/suppliers/{sid}', headers=owner_headers)
    assert resp.status_code == 200
    
    with app.app_context():
        s = _db.session.get(Supplier, sid)
        assert s.is_active == False
        
    # should not be in list anymore
    resp2 = client.get('/api/v1/suppliers', headers=owner_headers)
    data = resp2.get_json()['data']
    assert len(data) == 0
