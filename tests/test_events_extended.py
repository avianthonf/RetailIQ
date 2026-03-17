import datetime
import uuid

import pytest

from app import db
from app.auth.utils import generate_access_token
from app.models import BusinessEvent, Store, User


@pytest.fixture
def event_setup(app, test_store, test_owner):
    # Create some events
    events = []
    for i in range(3):
        ev = BusinessEvent(
            store_id=test_store.store_id,
            event_name=f"Event {i}",
            event_type="PROMOTION",
            start_date=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
            end_date=datetime.date(2026, 1, 5) + datetime.timedelta(days=i),
            expected_impact_pct=10.0 * (i + 1),
        )
        db.session.add(ev)
        events.append(ev)
    db.session.commit()
    return events


def test_create_event_validation_error(client, owner_headers):
    resp = client.post("/api/v1/events", json={"invalid": "data"}, headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json["error"]["code"] == "VALIDATION_ERROR"


def test_create_event_exception(client, owner_headers, monkeypatch, app):
    # Disable exception propagation for this test to see 500
    app.config["PROPAGATE_EXCEPTIONS"] = False
    from app.events import routes

    def mock_error(*args, **kwargs):
        raise Exception("Database error")

    monkeypatch.setattr(db.session, "commit", mock_error)

    payload = {
        "event_name": "Test",
        "event_type": "PROMOTION",
        "start_date": "2026-01-01",
        "end_date": "2026-01-05",
        "expected_impact_pct": 10.0,
    }
    resp = client.post("/api/v1/events", json=payload, headers=owner_headers)
    assert resp.status_code == 500
    app.config["PROPAGATE_EXCEPTIONS"] = True


def test_get_events_filters(client, owner_headers, event_setup):
    # Test filtering by date with 'from' and 'to'
    resp = client.get("/api/v1/events?from=2026-01-01&to=2026-01-10", headers=owner_headers)
    assert resp.status_code == 200
    assert len(resp.json["data"]) >= 3


def test_update_event_success(client, owner_headers, event_setup):
    ev = event_setup[0]
    payload = {"event_name": "Updated Event"}
    resp = client.put(f"/api/v1/events/{ev.id}", json=payload, headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["status"] == "UPDATED"


def test_get_events_invalid_dates(client, owner_headers):
    resp = client.get("/api/v1/events?from=invalid", headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json["error"]["code"] == "INVALID_DATE"

    resp = client.get("/api/v1/events?to=invalid", headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json["error"]["code"] == "INVALID_DATE"


def test_create_event_error_cases(client, owner_headers):
    # Invalid date format
    payload = {"event_name": "T", "event_type": "PROMOTION", "start_date": "invalid", "end_date": "2026-01-01"}
    resp = client.post("/api/v1/events", json=payload, headers=owner_headers)
    assert resp.status_code == 422
    assert resp.json["error"]["code"] == "INVALID_DATE"

    # start_date > end_date
    payload["start_date"] = "2026-01-05"
    resp = client.post("/api/v1/events", json=payload, headers=owner_headers)
    assert resp.status_code == 422
    assert "start_date must be <= end_date" in resp.json["error"]["message"]

    # Invalid event_type
    payload["start_date"] = "2026-01-01"
    payload["event_type"] = "INVALID"
    resp = client.post("/api/v1/events", json=payload, headers=owner_headers)
    assert resp.status_code == 422
    assert "Invalid event_type" in resp.json["error"]["message"]


def test_update_event_partial_and_errors(client, owner_headers, event_setup):
    ev = event_setup[0]

    # Invalid event_type
    resp = client.put(f"/api/v1/events/{ev.id}", json={"event_type": "INVALID"}, headers=owner_headers)
    assert resp.status_code == 422

    # Partial updates (dates, impact, recurring, recurrence_rule, event_type)
    payload = {
        "event_type": "FESTIVAL",
        "start_date": "2026-02-01",
        "end_date": "2026-02-05",
        "expected_impact_pct": 15.0,
        "is_recurring": True,
        "recurrence_rule": "FREQ=YEARLY",
    }
    resp = client.put(f"/api/v1/events/{ev.id}", json=payload, headers=owner_headers)
    assert resp.status_code == 200
    db.session.refresh(ev)
    assert ev.event_type == "FESTIVAL"

    # start_date > end_date in update
    resp = client.put(
        f"/api/v1/events/{ev.id}", json={"start_date": "2026-03-01", "end_date": "2026-02-01"}, headers=owner_headers
    )
    assert resp.status_code == 422


def test_demand_sensing_error_paths(client, owner_headers, monkeypatch):
    # Product not found
    resp = client.get("/api/v1/forecasting/demand-sensing/9999", headers=owner_headers)
    assert resp.status_code == 404

    # Forecast error (Exception) — monkeypatch the engine module directly
    from app.forecasting import engine as fc_engine

    def mock_error(*args, **kwargs):
        raise Exception("Forecast failed")

    monkeypatch.setattr(fc_engine, "generate_demand_forecast", mock_error)

    # Need a real product ID to pass the first check
    from app.models import Product

    # Create a product to ensure it exists
    store = db.session.query(Store).first()
    prod = Product(
        store_id=store.store_id,
        name="Sense Product",
        sku_code="SNS-001",
        cost_price=10.0,
        selling_price=20.0,
        current_stock=100,
    )
    db.session.add(prod)
    db.session.commit()

    resp = client.get(f"/api/v1/forecasting/demand-sensing/{prod.product_id}", headers=owner_headers)
    assert resp.status_code == 500
    assert resp.json["error"]["code"] == "FORECAST_ERROR"


def test_delete_event_success(client, owner_headers, event_setup):
    ev = event_setup[0]
    resp = client.delete(f"/api/v1/events/{ev.id}", headers=owner_headers)
    assert resp.status_code == 200

    # Verify deleted
    assert db.session.get(BusinessEvent, ev.id) is None


def test_delete_event_not_found(client, owner_headers):
    resp = client.delete(f"/api/v1/events/{uuid.uuid4()}", headers=owner_headers)
    assert resp.status_code == 404


def test_upcoming_events_invalid_days(client, owner_headers):
    resp = client.get("/api/v1/events/upcoming?days=abc", headers=owner_headers)
    assert resp.status_code == 422
    # The route returns 400 if int(days) fails
