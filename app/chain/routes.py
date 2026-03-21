import uuid as _uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import g, request
from marshmallow import ValidationError
from sqlalchemy import func

from .. import db
from ..auth.decorators import require_auth
from ..auth.utils import format_response
from ..models import (
    Alert,
    ChainDailyAggregate,
    DailyStoreSummary,
    InterStoreTransferSuggestion,
    Product,
    Store,
    StoreGroup,
    StoreGroupMembership,
)
from . import chain_bp
from .schemas import AddStoreToGroupSchema, ConfirmTransferSchema, CreateStoreGroupSchema


def require_chain_owner(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.current_user.get("chain_role") != "CHAIN_OWNER":
            return format_response(
                success=False, error={"code": "FORBIDDEN", "message": "Requires CHAIN_OWNER role"}, status_code=403
            )
        return f(*args, **kwargs)

    return decorated


def _serialize_group(group, memberships=None):
    memberships = memberships or []
    return {
        "group_id": str(group.id),
        "name": group.name,
        "description": getattr(group, "description", None),
        "owner_user_id": group.owner_user_id,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "updated_at": group.updated_at.isoformat() if group.updated_at else None,
        "member_store_ids": [membership.store_id for membership in memberships],
    }


def _serialize_transfer(suggestion):
    return {
        "id": str(suggestion.id),
        "from_store": suggestion.from_store_id,
        "to_store": suggestion.to_store_id,
        "product": suggestion.product_id,
        "qty": float(suggestion.suggested_qty) if suggestion.suggested_qty else 0.0,
        "reason": suggestion.reason,
        "status": suggestion.status,
        "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
    }


@chain_bp.route("/groups", methods=["POST"])
@require_auth
def create_group():
    try:
        data = CreateStoreGroupSchema().load(request.json)
    except Exception as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": str(err)})

    user_id = g.current_user["user_id"]

    # Check if user already owns a group
    existing = db.session.query(StoreGroup).filter_by(owner_user_id=user_id).first()
    if existing:
        return format_response(success=False, error={"code": "CONFLICT", "message": "User already owns a store group"})

    group = StoreGroup(name=data["name"], owner_user_id=user_id)
    db.session.add(group)
    db.session.commit()

    return format_response(success=True, data={"group_id": str(group.id), "name": group.name})


@chain_bp.route("/groups/<uuid:group_id>", methods=["GET"])
@require_auth
@require_chain_owner
def get_group(group_id):
    if g.current_user.get("chain_group_id") != str(group_id):
        return format_response(
            success=False, error={"code": "FORBIDDEN", "message": "Not owner of this group"}, status_code=403
        )

    group = db.session.query(StoreGroup).filter_by(id=group_id).first()
    if not group:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Group not found"}, status_code=404
        )

    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    return format_response(success=True, data=_serialize_group(group, memberships))


@chain_bp.route("/groups/<uuid:group_id>", methods=["PUT", "PATCH"])
@require_auth
@require_chain_owner
def update_group(group_id):
    if g.current_user.get("chain_group_id") != str(group_id):
        return format_response(
            success=False, error={"code": "FORBIDDEN", "message": "Not owner of this group"}, status_code=403
        )

    group = db.session.query(StoreGroup).filter_by(id=group_id).first()
    if not group:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Group not found"}, status_code=404
        )

    body = request.get_json() or {}
    name = body.get("name")
    if name:
        group.name = name

    db.session.commit()
    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    return format_response(success=True, data=_serialize_group(group, memberships))


@chain_bp.route("/groups/<uuid:group_id>/stores", methods=["POST"])
@require_auth
@require_chain_owner
def add_store_to_group(group_id):
    if g.current_user.get("chain_group_id") != str(group_id):
        return format_response(success=False, error={"code": "FORBIDDEN", "message": "Not owner of this group"})

    try:
        data = AddStoreToGroupSchema().load(request.json)
    except Exception as err:
        return format_response(success=False, error={"code": "VALIDATION_ERROR", "message": str(err)})

    store_id = data["store_id"]
    manager_id = data.get("manager_user_id")

    # Check store exists
    store = db.session.query(Store).filter_by(store_id=store_id).first()
    if not store:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Store not found"})

    # Check not already in a group
    existing_membership = db.session.query(StoreGroupMembership).filter_by(store_id=store_id).first()
    if existing_membership:
        return format_response(success=False, error={"code": "CONFLICT", "message": "Store is already in a group"})

    membership = StoreGroupMembership(group_id=group_id, store_id=store_id, manager_user_id=manager_id)
    db.session.add(membership)
    db.session.commit()

    return format_response(success=True, data={"membership_id": str(membership.id)}, status_code=201)


@chain_bp.route("/groups/<uuid:group_id>/stores/<int:store_id>", methods=["DELETE"])
@require_auth
@require_chain_owner
def remove_store_from_group(group_id, store_id):
    if g.current_user.get("chain_group_id") != str(group_id):
        return format_response(
            success=False, error={"code": "FORBIDDEN", "message": "Not owner of this group"}, status_code=403
        )

    membership = db.session.query(StoreGroupMembership).filter_by(group_id=group_id, store_id=store_id).first()
    if not membership:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Store membership not found"}, status_code=404
        )

    db.session.delete(membership)
    db.session.commit()
    return format_response(success=True, data={"store_id": store_id, "removed": True})


@chain_bp.route("/dashboard", methods=["GET"])
@require_auth
@require_chain_owner
def chain_dashboard():
    group_id = _uuid.UUID(g.current_user["chain_group_id"])
    today = datetime.now(timezone.utc).date()

    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    store_ids = [m.store_id for m in memberships]

    if not store_ids:
        return format_response(
            True,
            data={
                "total_revenue_today": 0,
                "best_store": None,
                "worst_store": None,
                "total_open_alerts": 0,
                "per_store_today": [],
                "transfer_suggestions": [],
            },
        )

    # Get today's aggregations
    aggs = (
        db.session.query(ChainDailyAggregate)
        .filter(ChainDailyAggregate.group_id == group_id, ChainDailyAggregate.date == today)
        .all()
    )

    total_rev = float(sum((agg.revenue or 0) for agg in aggs))

    per_store = []
    for store_id in store_ids:
        store = db.session.query(Store).filter_by(store_id=store_id).first()
        agg = next((a for a in aggs if a.store_id == store_id), None)
        alert_count = db.session.query(Alert).filter(Alert.store_id == store_id, Alert.resolved_at.is_(None)).count()

        per_store.append(
            {
                "store_id": store_id,
                "name": store.store_name if store else f"Store {store_id}",
                "revenue": float(agg.revenue) if agg and agg.revenue else 0.0,
                "transaction_count": agg.transaction_count if agg and agg.transaction_count else 0,
                "alert_count": alert_count,
            }
        )

    best_store = max(per_store, key=lambda x: x["revenue"]) if per_store else None
    worst_store = min(per_store, key=lambda x: x["revenue"]) if per_store else None
    total_alerts = sum(s["alert_count"] for s in per_store)

    suggestions = db.session.query(InterStoreTransferSuggestion).filter_by(group_id=group_id, status="PENDING").all()
    transfers = [
        {
            "id": str(s.id),
            "from_store": s.from_store_id,
            "to_store": s.to_store_id,
            "product": s.product_id,
            "qty": float(s.suggested_qty) if s.suggested_qty else 0.0,
            "reason": s.reason,
        }
        for s in suggestions
    ]

    return format_response(
        True,
        data={
            "total_revenue_today": total_rev,
            "best_store": best_store,
            "worst_store": worst_store,
            "total_open_alerts": total_alerts,
            "per_store_today": per_store,
            "transfer_suggestions": transfers,
        },
    )


@chain_bp.route("/compare", methods=["GET"])
@require_auth
@require_chain_owner
def evaluate_chain_comparison():
    group_id = _uuid.UUID(g.current_user["chain_group_id"])
    period = request.args.get("period", "today")

    end_date = datetime.now(timezone.utc).date()
    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date

    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    store_ids = [m.store_id for m in memberships]

    if not store_ids:
        return format_response(success=True, data=[])

    # Aggregate over the period
    results = (
        db.session.query(
            ChainDailyAggregate.store_id,
            func.sum(ChainDailyAggregate.revenue).label("total_rev"),
            func.sum(ChainDailyAggregate.profit).label("total_prof"),
        )
        .filter(
            ChainDailyAggregate.group_id == group_id,
            ChainDailyAggregate.date >= start_date,
            ChainDailyAggregate.date <= end_date,
        )
        .group_by(ChainDailyAggregate.store_id)
        .all()
    )

    avg_rev = float(sum((r.total_rev or 0) for r in results)) / len(store_ids) if results else 0.0

    comparison = []
    for store_id in store_ids:
        res = next((r for r in results if r.store_id == store_id), None)
        rev = float(res.total_rev) if res and res.total_rev else 0.0

        if avg_rev == 0:
            rel = "near"
        elif rev > avg_rev * 1.05:
            rel = "above"
        elif rev < avg_rev * 0.95:
            rel = "below"
        else:
            rel = "near"

        comparison.append(
            {
                "store_id": store_id,
                "revenue": rev,
                "profit": float(res.total_prof) if res and res.total_prof else 0.0,
                "relative_to_avg": rel,
            }
        )

    return format_response(success=True, data=comparison)


@chain_bp.route("/transfers", methods=["GET"])
@require_auth
@require_chain_owner
def get_transfers():
    group_id = _uuid.UUID(g.current_user["chain_group_id"])
    suggestions = db.session.query(InterStoreTransferSuggestion).filter_by(group_id=group_id).all()
    transfers = [_serialize_transfer(suggestion) for suggestion in suggestions]

    return format_response(success=True, data=transfers)


@chain_bp.route("/transfers", methods=["POST"])
@require_auth
@require_chain_owner
def create_transfer():
    group_id = _uuid.UUID(g.current_user["chain_group_id"])
    body = request.get_json() or {}

    required_fields = ("from_store_id", "to_store_id", "product_id", "quantity")
    missing = [field for field in required_fields if body.get(field) in (None, "")]
    if missing:
        return format_response(
            success=False,
            error={"code": "VALIDATION_ERROR", "message": f"Missing required fields: {', '.join(missing)}"},
            status_code=400,
        )

    from_store = db.session.query(Store).filter_by(store_id=body["from_store_id"]).first()
    to_store = db.session.query(Store).filter_by(store_id=body["to_store_id"]).first()
    product = db.session.query(Product).filter_by(product_id=body["product_id"]).first()
    if not from_store or not to_store:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Store not found"}, status_code=404
        )
    if not product:
        return format_response(
            success=False, error={"code": "NOT_FOUND", "message": "Product not found"}, status_code=404
        )

    suggestion = InterStoreTransferSuggestion(
        group_id=group_id,
        from_store_id=body["from_store_id"],
        to_store_id=body["to_store_id"],
        product_id=body["product_id"],
        suggested_qty=body["quantity"],
        reason=body.get("notes") or "Manual transfer created from chain console",
        status="PENDING",
    )
    db.session.add(suggestion)
    db.session.commit()

    return format_response(success=True, data=_serialize_transfer(suggestion), status_code=201)


@chain_bp.route("/transfers/<uuid:transfer_id>/confirm", methods=["POST"])
@require_auth
@require_chain_owner
def confirm_transfer(transfer_id):
    group_id = _uuid.UUID(g.current_user["chain_group_id"])

    suggestion = db.session.query(InterStoreTransferSuggestion).filter_by(id=transfer_id, group_id=group_id).first()
    if not suggestion:
        return format_response(success=False, error={"code": "NOT_FOUND", "message": "Transfer suggestion not found"})

    suggestion.status = "ACTIONED"
    db.session.commit()

    return format_response(success=True, data={"message": "Transfer confirmed", "id": str(suggestion.id)})
