from functools import wraps
import uuid as _uuid
from flask import request, jsonify, g
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import func
from app import db
from app.auth.utils import format_response
from app.auth.decorators import require_auth
from app.models import Store, StoreGroup, StoreGroupMembership, ChainDailyAggregate, InterStoreTransferSuggestion, Alert, DailyStoreSummary
from marshmallow import ValidationError
from app.chain.schemas import CreateStoreGroupSchema, AddStoreToGroupSchema, ConfirmTransferSchema
from . import chain_bp

def require_chain_owner(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.current_user.get('chain_role') != 'CHAIN_OWNER':
            return format_response(False, error={"code": "FORBIDDEN", "message": "Requires CHAIN_OWNER role"}), 403
        return f(*args, **kwargs)
    return decorated

@chain_bp.route('/groups', methods=['POST'])
@require_auth
def create_group():
    try:
        data = CreateStoreGroupSchema().load(request.json)
    except Exception as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": str(err)}), 400

    user_id = g.current_user['user_id']
    
    # Check if user already owns a group
    existing = db.session.query(StoreGroup).filter_by(owner_user_id=user_id).first()
    if existing:
        return format_response(False, error={"code": "CONFLICT", "message": "User already owns a store group"}), 409

    group = StoreGroup(name=data['name'], owner_user_id=user_id)
    db.session.add(group)
    db.session.commit()

    return format_response(True, data={"group_id": str(group.id), "name": group.name}), 201


@chain_bp.route('/groups/<uuid:group_id>/stores', methods=['POST'])
@require_auth
@require_chain_owner
def add_store_to_group(group_id):
    if g.current_user.get('chain_group_id') != str(group_id):
        return format_response(False, error={"code": "FORBIDDEN", "message": "Not owner of this group"}), 403

    try:
        data = AddStoreToGroupSchema().load(request.json)
    except Exception as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": str(err)}), 400

    store_id = data['store_id']
    manager_id = data.get('manager_user_id')

    # Check store exists
    store = db.session.query(Store).filter_by(store_id=store_id).first()
    if not store:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Store not found"}), 404

    # Check not already in a group
    existing_membership = db.session.query(StoreGroupMembership).filter_by(store_id=store_id).first()
    if existing_membership:
        return format_response(False, error={"code": "CONFLICT", "message": "Store is already in a group"}), 409

    membership = StoreGroupMembership(group_id=group_id, store_id=store_id, manager_user_id=manager_id)
    db.session.add(membership)
    db.session.commit()

    return format_response(True, data={"membership_id": str(membership.id)}), 201


@chain_bp.route('/dashboard', methods=['GET'])
@require_auth
@require_chain_owner
def chain_dashboard():
    group_id = _uuid.UUID(g.current_user['chain_group_id'])
    today = date.today()

    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    store_ids = [m.store_id for m in memberships]

    if not store_ids:
        return format_response(True, data={"total_revenue_today": 0, "best_store": None, "worst_store": None, "total_open_alerts": 0, "per_store_today": [], "transfer_suggestions": []})

    # Get today's aggregations
    aggs = db.session.query(ChainDailyAggregate).filter(
        ChainDailyAggregate.group_id == group_id,
        ChainDailyAggregate.date == today
    ).all()

    total_rev = float(sum((agg.revenue or 0) for agg in aggs))
    
    per_store = []
    for store_id in store_ids:
        store = db.session.query(Store).filter_by(store_id=store_id).first()
        agg = next((a for a in aggs if a.store_id == store_id), None)
        alert_count = db.session.query(Alert).filter_by(store_id=store_id, resolved_at=None).count()
        
        per_store.append({
            "store_id": store_id,
            "name": store.store_name if store else f"Store {store_id}",
            "revenue": float(agg.revenue) if agg and agg.revenue else 0.0,
            "transaction_count": agg.transaction_count if agg and agg.transaction_count else 0,
            "alert_count": alert_count
        })

    best_store = max(per_store, key=lambda x: x['revenue']) if per_store else None
    worst_store = min(per_store, key=lambda x: x['revenue']) if per_store else None
    total_alerts = sum(s['alert_count'] for s in per_store)

    suggestions = db.session.query(InterStoreTransferSuggestion).filter_by(group_id=group_id, status='PENDING').all()
    transfers = [{
        "id": str(s.id),
        "from_store": s.from_store_id,
        "to_store": s.to_store_id,
        "product": s.product_id,
        "qty": float(s.suggested_qty) if s.suggested_qty else 0.0,
        "reason": s.reason
    } for s in suggestions]

    return format_response(True, data={
        "total_revenue_today": total_rev,
        "best_store": best_store,
        "worst_store": worst_store,
        "total_open_alerts": total_alerts,
        "per_store_today": per_store,
        "transfer_suggestions": transfers
    })


@chain_bp.route('/compare', methods=['GET'])
@require_auth
@require_chain_owner
def evaluate_chain_comparison():
    group_id = _uuid.UUID(g.current_user['chain_group_id'])
    period = request.args.get('period', 'today')
    
    end_date = date.today()
    if period == 'week':
        start_date = end_date - timedelta(days=7)
    elif period == 'month':
        start_date = end_date - timedelta(days=30)
    else:
        start_date = end_date

    memberships = db.session.query(StoreGroupMembership).filter_by(group_id=group_id).all()
    store_ids = [m.store_id for m in memberships]

    if not store_ids:
        return format_response(True, data=[])

    # Aggregate over the period
    results = db.session.query(
        ChainDailyAggregate.store_id,
        func.sum(ChainDailyAggregate.revenue).label('total_rev'),
        func.sum(ChainDailyAggregate.profit).label('total_prof')
    ).filter(
        ChainDailyAggregate.group_id == group_id,
        ChainDailyAggregate.date >= start_date,
        ChainDailyAggregate.date <= end_date
    ).group_by(ChainDailyAggregate.store_id).all()

    avg_rev = float(sum((r.total_rev or 0) for r in results)) / len(store_ids) if results else 0.0

    comparison = []
    for store_id in store_ids:
        res = next((r for r in results if r.store_id == store_id), None)
        rev = float(res.total_rev) if res and res.total_rev else 0.0
        
        if avg_rev == 0:
            rel = 'near'
        elif rev > avg_rev * 1.05:
            rel = 'above'
        elif rev < avg_rev * 0.95:
            rel = 'below'
        else:
            rel = 'near'

        comparison.append({
            "store_id": store_id,
            "revenue": rev,
            "profit": float(res.total_prof) if res and res.total_prof else 0.0,
            "relative_to_avg": rel
        })

    return format_response(True, data=comparison)


@chain_bp.route('/transfers', methods=['GET'])
@require_auth
@require_chain_owner
def get_transfers():
    group_id = _uuid.UUID(g.current_user['chain_group_id'])
    suggestions = db.session.query(InterStoreTransferSuggestion).filter_by(group_id=group_id).all()
    transfers = [{
        "id": str(s.id),
        "from_store": s.from_store_id,
        "to_store": s.to_store_id,
        "product": s.product_id,
        "qty": float(s.suggested_qty) if s.suggested_qty else 0.0,
        "reason": s.reason,
        "status": s.status
    } for s in suggestions]
    
    return format_response(True, data=transfers)


@chain_bp.route('/transfers/<uuid:transfer_id>/confirm', methods=['POST'])
@require_auth
@require_chain_owner
def confirm_transfer(transfer_id):
    group_id = _uuid.UUID(g.current_user['chain_group_id'])
    
    suggestion = db.session.query(InterStoreTransferSuggestion).filter_by(id=transfer_id, group_id=group_id).first()
    if not suggestion:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Transfer suggestion not found"}), 404

    suggestion.status = 'ACTIONED'
    db.session.commit()

    return format_response(True, data={"message": "Transfer confirmed", "id": str(suggestion.id)})
