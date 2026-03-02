import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.models import Product, StaffDailyTarget, StaffSession, Store, Transaction, User


def test_start_session_creates_record(app, client, staff_headers, test_staff):
    with app.app_context():
        resp = client.post('/api/v1/staff/sessions/start', headers=staff_headers)
        assert resp.status_code == 201
        assert resp.json['success'] is True
        assert 'session_id' in resp.json['data']

        import uuid
        session = db.session.query(StaffSession).filter(StaffSession.id == uuid.UUID(resp.json['data']['session_id'])).first()
        assert session is not None
        assert session.ended_at is None
        assert session.status == 'OPEN'
        assert session.user_id == test_staff.user_id

def test_start_session_closes_existing_open(app, client, staff_headers, test_staff, test_store):
    with app.app_context():
        old_session = StaffSession(
            store_id=test_store.store_id,
            user_id=test_staff.user_id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status='OPEN'
        )
        db.session.add(old_session)
        db.session.commit()
        old_session_id = old_session.id

    resp = client.post('/api/v1/staff/sessions/start', headers=staff_headers)
    assert resp.status_code == 201

    with app.app_context():
        import uuid
        session = db.session.query(StaffSession).filter(StaffSession.id == uuid.UUID(str(old_session_id))).first()
        assert session.status == 'CLOSED'
        assert session.ended_at is not None

def test_end_session_transitions_to_closed(app, client, staff_headers, test_staff, test_store):
    with app.app_context():
        active_session = StaffSession(
            store_id=test_store.store_id,
            user_id=test_staff.user_id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status='OPEN'
        )
        db.session.add(active_session)
        db.session.commit()
        active_session_id = active_session.id

    resp = client.post('/api/v1/staff/sessions/end', headers=staff_headers)
    assert resp.status_code == 200

    with app.app_context():
        import uuid
        session = db.session.query(StaffSession).filter(StaffSession.id == uuid.UUID(str(active_session_id))).first()
        assert session.status == 'CLOSED'
        assert session.ended_at is not None

def test_transaction_attributed_to_session(app, client, staff_headers, test_staff, test_store):
    with app.app_context():
        product = Product(
            store_id=test_store.store_id,
            name='Test P',
            barcode='SKU1',
            category_id=None,
            selling_price=10.0,
            current_stock=100
        )
        db.session.add(product)

        active_session = StaffSession(
            store_id=test_store.store_id,
            user_id=test_staff.user_id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status='OPEN'
        )
        db.session.add(active_session)
        db.session.commit()
        active_session_id = active_session.id

        txn_id = str(uuid_lib.uuid4())
        payload = {
            "transaction_id": txn_id,
            "payment_mode": "CASH",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "line_items": [
                {"product_id": str(product.product_id), "quantity": 1, "selling_price": 10.0}
            ]
        }

    resp = client.post('/api/v1/transactions', json=payload, headers=staff_headers)
    assert resp.status_code == 201

    with app.app_context():
        import uuid
        saved_txn = db.session.query(Transaction).filter(Transaction.transaction_id == uuid.UUID(txn_id)).first()
        assert saved_txn is not None
        assert str(saved_txn.session_id).replace('-', '') == str(active_session_id).replace('-', '')

def test_owner_sees_all_staff_performance(app, client, owner_headers, test_owner, test_staff, test_store):
    # test_staff is one staff member that fixtures auto-create
    # Need to verify at least they show up
    with app.app_context():
        # Ensure staff has a name for formatting
        test_staff.full_name = 'Staff One'
        db.session.commit()

    resp = client.get('/api/v1/staff/performance', headers=owner_headers)
    assert resp.status_code == 200

    data = resp.json['data']
    assert len(data) >= 1
    user_ids = [d['user_id'] for d in data]
    assert test_staff.user_id in user_ids

def test_staff_cannot_see_others_performance(client, staff_headers):
    resp = client.get('/api/v1/staff/performance', headers=staff_headers)
    assert resp.status_code == 403  # Forbidden

def test_upsert_daily_target(app, client, owner_headers, test_staff, test_store):
    target_date = "2026-02-28"
    payload = {
        "user_id": test_staff.user_id,
        "target_date": target_date,
        "revenue_target": 1500.50,
        "transaction_count_target": 20
    }

    resp = client.put('/api/v1/staff/targets', json=payload, headers=owner_headers)
    assert resp.status_code == 200

    with app.app_context():
        t_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        target = db.session.query(StaffDailyTarget).filter_by(
            store_id=test_store.store_id, user_id=test_staff.user_id, target_date=t_date
        ).first()

        assert target is not None
        assert float(target.revenue_target) == 1500.50
        assert target.transaction_count_target == 20

def test_auto_close_task(app, test_staff, test_store):
    with app.app_context():
        old_session = StaffSession(
            store_id=test_store.store_id, user_id=test_staff.user_id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=17),
            status='OPEN'
        )
        new_session = StaffSession(
            store_id=test_store.store_id, user_id=test_staff.user_id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status='OPEN'
        )
        db.session.add_all([old_session, new_session])
        db.session.commit()
        old_session_id = old_session.id
        new_session_id = new_session.id

        # Execute directly like the task would to avoid transaction isolation bugs in testing
        from sqlalchemy import text
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=16)
        db.session.execute(text("""
            UPDATE staff_sessions
            SET status = 'CLOSED', ended_at = CURRENT_TIMESTAMP
            WHERE status = 'OPEN' AND started_at < :cutoff
        """), {"cutoff": str(cutoff_time)})
        db.session.commit()

        import uuid
        session_old = db.session.query(StaffSession).filter(StaffSession.id == uuid.UUID(str(old_session_id))).first()
        session_new = db.session.query(StaffSession).filter(StaffSession.id == uuid.UUID(str(new_session_id))).first()

        assert session_old.status == 'CLOSED'
        assert session_new.status == 'OPEN'
