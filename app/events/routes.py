from datetime import date, datetime, timedelta, timezone

from flask import g, request
from sqlalchemy import and_, or_, text

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.events import events_bp
from app.forecasting.engine import generate_demand_forecast
from app.models import BusinessEvent, Product


@events_bp.route("/events", methods=["GET"])
@require_auth
def list_events():
    """List store business events, optionally filtered by ?from=YYYY-MM-DD & to=YYYY-MM-DD."""
    store_id = g.current_user.get("store_id")
    from_date_str = request.args.get("from")
    to_date_str = request.args.get("to")

    query = db.session.query(BusinessEvent).filter_by(store_id=store_id)

    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
            query = query.filter(BusinessEvent.end_date >= from_date)
        except ValueError:
            return format_response(error={"code": "INVALID_DATE", "message": "Invalid from date format"}), 422

    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
            query = query.filter(BusinessEvent.start_date <= to_date)
        except ValueError:
            return format_response(error={"code": "INVALID_DATE", "message": "Invalid to date format"}), 422

    events = query.order_by(BusinessEvent.start_date.asc()).all()

    data = [
        {
            "id": str(e.id),
            "event_name": e.event_name,
            "event_type": e.event_type,
            "start_date": e.start_date.isoformat() if e.start_date else None,
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "expected_impact_pct": float(e.expected_impact_pct) if e.expected_impact_pct is not None else None,
            "is_recurring": e.is_recurring,
            "recurrence_rule": e.recurrence_rule,
        }
        for e in events
    ]

    return format_response(data=data)


@events_bp.route("/events", methods=["POST"])
@require_auth
def create_event():
    """Create a new business event."""
    store_id = g.current_user.get("store_id")
    payload = request.get_json() or {}

    required_fields = ["event_name", "event_type", "start_date", "end_date"]
    if not all(k in payload for k in required_fields):
        return format_response(error={"code": "VALIDATION_ERROR", "message": "Missing required fields"}), 422

    try:
        start_date = datetime.strptime(payload["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(payload["end_date"], "%Y-%m-%d").date()
    except ValueError:
        return format_response(error={"code": "INVALID_DATE", "message": "Invalid date format, use YYYY-MM-DD"}), 422

    if start_date > end_date:
        return format_response(error={"code": "VALIDATION_ERROR", "message": "start_date must be <= end_date"}), 422

    event_type = payload["event_type"]
    if event_type not in {"HOLIDAY", "FESTIVAL", "PROMOTION", "SALE_DAY", "CLOSURE"}:
        return format_response(error={"code": "VALIDATION_ERROR", "message": "Invalid event_type"}), 422

    impact = payload.get("expected_impact_pct")
    if impact is not None:
        impact = float(impact)

    event = BusinessEvent(
        store_id=store_id,
        event_name=payload["event_name"],
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        expected_impact_pct=impact,
        is_recurring=payload.get("is_recurring", False),
        recurrence_rule=payload.get("recurrence_rule"),
    )

    db.session.add(event)
    db.session.commit()

    return format_response(data={"id": str(event.id), "status": "CREATED"}), 201


@events_bp.route("/events/<uuid:event_id>", methods=["PUT"])
@require_auth
def update_event(event_id):
    """Update an existing event."""
    store_id = g.current_user.get("store_id")
    event = db.session.query(BusinessEvent).filter_by(id=event_id, store_id=store_id).first()

    if not event:
        return format_response(error={"code": "NOT_FOUND", "message": "Event not found"}), 404

    payload = request.get_json() or {}

    if "event_name" in payload:
        event.event_name = payload["event_name"]
    if "event_type" in payload:
        if payload["event_type"] not in {"HOLIDAY", "FESTIVAL", "PROMOTION", "SALE_DAY", "CLOSURE"}:
            return format_response(error={"code": "VALIDATION_ERROR", "message": "Invalid event_type"}), 422
        event.event_type = payload["event_type"]
    if "start_date" in payload:
        event.start_date = datetime.strptime(payload["start_date"], "%Y-%m-%d").date()
    if "end_date" in payload:
        event.end_date = datetime.strptime(payload["end_date"], "%Y-%m-%d").date()
    if "expected_impact_pct" in payload:
        impact = payload["expected_impact_pct"]
        event.expected_impact_pct = float(impact) if impact is not None else None
    if "is_recurring" in payload:
        event.is_recurring = bool(payload["is_recurring"])
    if "recurrence_rule" in payload:
        event.recurrence_rule = payload["recurrence_rule"]

    if event.start_date > event.end_date:
        return format_response(error={"code": "VALIDATION_ERROR", "message": "start_date must be <= end_date"}), 422

    db.session.commit()
    return format_response(data={"id": str(event.id), "status": "UPDATED"})


@events_bp.route("/events/<uuid:event_id>", methods=["DELETE"])
@require_auth
def delete_event(event_id):
    """Delete an event."""
    store_id = g.current_user.get("store_id")
    event = db.session.query(BusinessEvent).filter_by(id=event_id, store_id=store_id).first()

    if not event:
        return format_response(error={"code": "NOT_FOUND", "message": "Event not found"}), 404

    db.session.delete(event)
    db.session.commit()

    return format_response(data={"status": "DELETED"})


@events_bp.route("/events/upcoming", methods=["GET"])
@require_auth
def upcoming_events():
    """List next X days of events."""
    store_id = g.current_user.get("store_id")
    days_str = request.args.get("days", "30")

    try:
        days = int(days_str)
    except ValueError:
        return format_response(error={"code": "VALIDATION_ERROR", "message": "days must be an integer"}), 422

    today = datetime.now(timezone.utc).date()
    horizon_date = today + timedelta(days=days)

    events = (
        db.session.query(BusinessEvent)
        .filter(
            BusinessEvent.store_id == store_id,
            BusinessEvent.end_date >= today,
            BusinessEvent.start_date <= horizon_date,
        )
        .order_by(BusinessEvent.start_date.asc())
        .all()
    )

    data = [
        {
            "id": str(e.id),
            "event_name": e.event_name,
            "event_type": e.event_type,
            "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat(),
            "expected_impact_pct": float(e.expected_impact_pct) if e.expected_impact_pct is not None else None,
        }
        for e in events
    ]

    return format_response(data=data)


@events_bp.route("/forecasting/demand-sensing/<int:product_id>", methods=["GET"])
@require_auth
def demand_sensing(product_id):
    """Returns base forecast, event_adjusted_forecast and active events for next 14 days."""
    store_id = g.current_user.get("store_id")

    # Verify product belongs to store
    prod = db.session.query(Product).filter_by(product_id=product_id, store_id=store_id).first()
    if not prod:
        return format_response(error={"code": "NOT_FOUND", "message": "Product not found"}), 404

    try:
        # Call forecasting engine (to be implemented in engine.py)
        result = generate_demand_forecast(store_id, product_id, db.session, horizon=14)
        return format_response(data=result)
    except Exception as e:
        return format_response(error={"code": "FORECAST_ERROR", "message": str(e)}), 500
