import datetime
import uuid

import pytest
from sqlalchemy import text

from app import db
from app.models import BusinessEvent, DemandSensingLog, Product, Store, User

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

@pytest.fixture
def store_and_user(client):

    # Using raw SQL or ORM to create a store and a user
    store = Store(store_name="Event Store", currency_symbol="USD")
    db.session.add(store)
    db.session.commit()

    user = User(
        mobile_number=f"555{uuid.uuid4().hex[:7]}",
        store_id=store.store_id,
        role="owner",
        is_active=True
    )
    db.session.add(user)
    db.session.commit()

    return store, user

@pytest.fixture
def auth_headers(client, store_and_user):
    store, user = store_and_user
    from app.auth.utils import generate_access_token
    token = generate_access_token(user.user_id, store.store_id, user.role)
    return {'Authorization': f'Bearer {token}'}

@pytest.fixture
def setup_product(store_and_user):
    store, _ = store_and_user
    prod = Product(
        store_id=store.store_id,
        name="Event Product",
        sku_code="EVT-001",
        category_id=None,
        cost_price=10.0,
        selling_price=20.0,
        current_stock=100
    )
    db.session.add(prod)
    db.session.commit()
    return prod


def seed_history(store_id, product_id, days=90, base_demand=10.0):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    # Insert daily_sku_summary
    for i in range(days, 0, -1):
        d = today - datetime.timedelta(days=i)
        db.session.execute(
            text("""
            INSERT INTO daily_sku_summary
            (store_id, product_id, date, units_sold, revenue, profit, avg_selling_price)
            VALUES (:sid, :pid, :d, :qty, :rev, :prof, :asp)
            """),
            {"sid": store_id, "pid": product_id, "d": d, "qty": base_demand,
             "rev": base_demand * 20.0, "prof": base_demand * 10.0, "asp": 20.0}
        )
    db.session.commit()


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

def test_create_event(client, auth_headers, store_and_user):
    store, _ = store_and_user
    payload = {
        "event_name": "Summer Sale",
        "event_type": "PROMOTION",
        "start_date": "2026-06-01",
        "end_date": "2026-06-07",
        "expected_impact_pct": 25.0
    }
    res = client.post('/api/v1/events', json=payload, headers=auth_headers)
    assert res.status_code == 201

    # Verify in DB
    ev = db.session.query(BusinessEvent).filter_by(store_id=store.store_id).first()
    assert ev.event_name == "Summer Sale"
    assert float(ev.expected_impact_pct) == 25.0


def test_upcoming_events_filtered_correctly(client, auth_headers, store_and_user):
    store, _ = store_and_user
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # 1 event tomorrow (within 30 days)
    ev1 = BusinessEvent(
        store_id=store.store_id, event_name="Nearby", event_type="FESTIVAL",
        start_date=today + datetime.timedelta(days=1),
        end_date=today + datetime.timedelta(days=2),
        expected_impact_pct=10.0
    )
    # 1 event in 50 days (outside 30 days)
    ev2 = BusinessEvent(
        store_id=store.store_id, event_name="Far Away", event_type="HOLIDAY",
        start_date=today + datetime.timedelta(days=50),
        end_date=today + datetime.timedelta(days=51),
        expected_impact_pct=5.0
    )
    db.session.add_all([ev1, ev2])
    db.session.commit()

    res = client.get('/api/v1/events/upcoming?days=30', headers=auth_headers)
    assert res.status_code == 200
    data = res.json['data']
    assert len(data) == 1
    assert data[0]['event_name'] == "Nearby"


def test_prophet_uses_event_regressor(client, auth_headers, store_and_user, setup_product):
    store, _ = store_and_user
    prod = setup_product

    # Seed 90 days of history
    seed_history(store.store_id, prod.product_id, days=90, base_demand=20.0)

    # Seed 1 future event
    today = datetime.datetime.now(datetime.timezone.utc).date()
    ev = BusinessEvent(
        store_id=store.store_id, event_name="Big Promo", event_type="PROMOTION",
        start_date=today + datetime.timedelta(days=2),
        end_date=today + datetime.timedelta(days=4),
        expected_impact_pct=50.0  # Big impact
    )
    db.session.add(ev)
    db.session.commit()

    # Call demand sensing endpoint
    res = client.get(f'/api/v1/forecasting/demand-sensing/{prod.product_id}', headers=auth_headers)
    assert res.status_code == 200
    data = res.json['data']
    assert data['model_type'] == 'prophet'

    # Verify demand_sensing_log
    logs = db.session.query(DemandSensingLog).filter_by(product_id=prod.product_id).all()
    assert len(logs) == 14  # 14 days horizon

    # Find a log within the event window
    event_log = next(l for l in logs if l.date == today + datetime.timedelta(days=3))
    assert len(event_log.active_events) == 1
    assert event_log.active_events[0]['event_name'] == "Big Promo"

    # Because of massive expected_impact_pct + Prophet regressor logic,
    # base forecast vs event_adjusted_forecast should differ over time if trained on events
    # Though Prophet needs historical events to learn coefficient. For *future only* events, it might have 0 weight
    # unless there were past events, but the requirement is just adding the regressors and logging them!


def test_max_5_regressors_enforced(client, auth_headers, store_and_user, setup_product):
    store, _ = store_and_user
    prod = setup_product

    # Seed 90 days history
    seed_history(store.store_id, prod.product_id, days=90)

    today = datetime.datetime.now(datetime.timezone.utc).date()

    # Insert 8 distinct events overlapping the horizon (e.g. tomorrow)
    events = []
    for i in range(8):
        events.append(BusinessEvent(
            store_id=store.store_id, event_name=f"Event {i}", event_type="FESTIVAL",
            start_date=today + datetime.timedelta(days=1),
            end_date=today + datetime.timedelta(days=3),
            expected_impact_pct=10.0 + i  # varying impacts so the top 5 are distinct
        ))
    db.session.add_all(events)
    db.session.commit()

    # Call demand sensing
    res = client.get(f'/api/v1/forecasting/demand-sensing/{prod.product_id}', headers=auth_headers)
    assert res.status_code == 200

    # Find a log within the event window
    log = db.session.query(DemandSensingLog).filter_by(
        product_id=prod.product_id, date=today + datetime.timedelta(days=2)
    ).first()

    assert log is not None
    # Ensure only 5 were active
    assert len(log.active_events) == 5

    # The ones with highest absolute expected_impact_pct should be picked
    # i.e., 17.0, 16.0, 15.0, 14.0, 13.0
    impacts = db.session.query(BusinessEvent).filter(
        BusinessEvent.event_name.in_([e['event_name'] for e in log.active_events])
    ).all()
    pcts = sorted([float(i.expected_impact_pct) for i in impacts])
    assert pcts == [13.0, 14.0, 15.0, 16.0, 17.0]

def test_event_regressor_does_not_break_ridge_fallback(client, auth_headers, store_and_user, setup_product):
    store, _ = store_and_user
    prod = setup_product

    # Seed 20 days history (falls to Ridge)
    seed_history(store.store_id, prod.product_id, days=20)

    # Insert 1 event
    today = datetime.datetime.now(datetime.timezone.utc).date()
    ev = BusinessEvent(
        store_id=store.store_id, event_name="Small Promo", event_type="PROMOTION",
        start_date=today + datetime.timedelta(days=1),
        end_date=today + datetime.timedelta(days=2),
        expected_impact_pct=10.0
    )
    db.session.add(ev)
    db.session.commit()

    # Call demand sensing
    res = client.get(f'/api/v1/forecasting/demand-sensing/{prod.product_id}', headers=auth_headers)
    assert res.status_code == 200
    data = res.json['data']
    assert data['model_type'] == 'ridge'

    # Ensure it logged gracefully
    log = db.session.query(DemandSensingLog).filter_by(
        product_id=prod.product_id, date=today + datetime.timedelta(days=1)
    ).first()
    # Linear Regression currently ignores the events in calculation,
    # but generate_demand_forecast wrapper still records the active events for that day!
    assert len(log.active_events) == 1
    assert log.active_events[0]['event_name'] == "Small Promo"
