import logging
import uuid
from datetime import datetime, timezone, timedelta, date

from flask import request, g, jsonify
from sqlalchemy import func
from . import staff_performance_bp
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import StaffSession, StaffDailyTarget, Transaction, TransactionItem, User
from .. import db

logger = logging.getLogger(__name__)

@staff_performance_bp.route('/sessions/start', methods=['POST'])
@require_auth
def start_session():
    """Start a new session; auto-close any existing OPEN session for this user."""
    store_id = g.current_user['store_id']
    user_id = g.current_user['user_id']

    # Close any existing open session
    existing_sessions = db.session.query(StaffSession).filter(
        StaffSession.store_id == store_id,
        StaffSession.user_id == user_id,
        StaffSession.status == 'OPEN'
    ).all()

    now = datetime.now(timezone.utc)
    for session in existing_sessions:
        session.status = 'CLOSED'
        session.ended_at = now

    if existing_sessions:
        db.session.flush()

    # Get today's target revenue if set
    today = now.date()
    target = db.session.query(StaffDailyTarget).filter(
        StaffDailyTarget.store_id == store_id,
        StaffDailyTarget.user_id == user_id,
        StaffDailyTarget.target_date == today
    ).first()

    target_revenue = float(target.revenue_target) if target and target.revenue_target is not None else None

    new_session = StaffSession(
        store_id=store_id,
        user_id=user_id,
        started_at=now,
        status='OPEN',
        target_revenue=target_revenue
    )

    db.session.add(new_session)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to start session: {e}")
        return format_response(False, error={"message": "Database error"}), 500

    return format_response(True, data={"session_id": str(new_session.id)}), 201


@staff_performance_bp.route('/sessions/end', methods=['POST'])
@require_auth
def end_session():
    """End the current OPEN session."""
    store_id = g.current_user['store_id']
    user_id = g.current_user['user_id']

    session = db.session.query(StaffSession).filter(
        StaffSession.store_id == store_id,
        StaffSession.user_id == user_id,
        StaffSession.status == 'OPEN'
    ).first()

    if not session:
        return format_response(False, error={"message": "No open session found"}), 404

    session.status = 'CLOSED'
    session.ended_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to end session: {e}")
        return format_response(False, error={"message": "Database error"}), 500

    return format_response(True, data={"message": "Session ended successfully"}), 200


@staff_performance_bp.route('/sessions/current', methods=['GET'])
@require_auth
def get_current_session():
    """Get the current OPEN session for the requesting user."""
    store_id = g.current_user['store_id']
    user_id = g.current_user['user_id']

    session = db.session.query(StaffSession).filter(
        StaffSession.store_id == store_id,
        StaffSession.user_id == user_id,
        StaffSession.status == 'OPEN'
    ).first()

    if session:
        return format_response(True, data={
            "active": True,
            "session_id": str(session.id),
            "started_at": session.started_at.isoformat(),
            "target_revenue": float(session.target_revenue) if session.target_revenue else None
        }), 200
    else:
        return format_response(True, data={"active": False}), 200


@staff_performance_bp.route('/performance', methods=['GET'])
@require_auth
@require_role('owner')
def get_all_staff_performance():
    """OWNER ONLY: Returns list of all staff performance for today."""
    store_id = g.current_user['store_id']
    today = datetime.now(timezone.utc).date()

    # Get all staff
    staff_members = db.session.query(User).filter(
        User.store_id == store_id,
        User.role == 'staff',
        User.is_active == True
    ).all()

    # Get their sessions for today to link transactions
    # Note: A staff might have multiple sessions today, or no session but made transactions.
    # We will scope transactions by checking created_by or joining with session ID.
    # Wait, the prompt says "Modify app/transactions/routes.py POST handler... query for their OPEN session and attach session_id". This means we can aggregate transactions by session_id, and link session_id to user_id.

    # 1. Get today's sessions for the store
    todays_sessions = db.session.query(StaffSession).filter(
        StaffSession.store_id == store_id,
        func.date(StaffSession.started_at) == today
    ).subquery()

    # 2. Get Targets
    targets = db.session.query(StaffDailyTarget).filter(
        StaffDailyTarget.store_id == store_id,
        StaffDailyTarget.target_date == today
    ).all()
    target_map = {t.user_id: t for t in targets}

    # 3. Aggregate transactions by user for today
    # We join Transactions -> StaffSession (via session_id) -> User
    # But wait, transaction doesn't have created_by, it only has session_id now.
    txn_agg = db.session.query(
        StaffSession.user_id,
        func.count(Transaction.transaction_id.distinct()).label('txn_count'),
        func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).label('total_revenue'),
        func.sum(TransactionItem.discount_amount).label('total_discount'),
        func.sum(TransactionItem.quantity * TransactionItem.selling_price).label('gross_revenue')
    ).select_from(Transaction).join(
        StaffSession, Transaction.session_id == StaffSession.id
    ).join(
        TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id
    ).filter(
        Transaction.store_id == store_id,
        func.date(Transaction.created_at) == today,
        Transaction.is_return == False
    ).group_by(StaffSession.user_id).all()

    agg_map = {row.user_id: row for row in txn_agg}

    result = []
    for staff in staff_members:
        stats = agg_map.get(staff.user_id)
        target = target_map.get(staff.user_id)

        today_revenue = float(stats.total_revenue) if stats and stats.total_revenue else 0.0
        today_txn_count = int(stats.txn_count) if stats else 0
        today_discount = float(stats.total_discount) if stats and stats.total_discount else 0.0
        gross_rev = float(stats.gross_revenue) if stats and stats.gross_revenue else 0.0
        
        avg_discount_pct = (today_discount / gross_rev * 100) if gross_rev > 0 else 0.0
        
        target_revenue = float(target.revenue_target) if target and target.revenue_target else None
        target_pct_achieved = (today_revenue / target_revenue * 100) if target_revenue and target_revenue > 0 else None

        result.append({
            "user_id": staff.user_id,
            "name": staff.full_name or staff.mobile_number,
            "today_revenue": round(today_revenue, 2),
            "today_transaction_count": today_txn_count,
            "today_discount_total": round(today_discount, 2),
            "avg_discount_pct": round(avg_discount_pct, 2),
            "target_revenue": target_revenue,
            "target_pct_achieved": round(target_pct_achieved, 2) if target_pct_achieved is not None else None
        })

    return format_response(True, data=result), 200

@staff_performance_bp.route('/performance/<int:user_id>', methods=['GET'])
@require_auth
@require_role('owner')
def get_staff_performance_detail(user_id):
    """OWNER ONLY: Returns historical 30-day performance for a specific user."""
    store_id = g.current_user['store_id']
    
    # Verify staff belongs to store
    staff = db.session.query(User).filter(
        User.user_id == user_id,
        User.store_id == store_id,
        User.role == 'staff'
    ).first()

    if not staff:
        return format_response(False, error={"message": "Staff not found"}), 404

    thirty_days_ago = datetime.now(timezone.utc).date() - timedelta(days=30)

    # We need daily grouping. 
    daily_stats = db.session.query(
        func.date(Transaction.created_at).label('txn_date'),
        func.count(Transaction.transaction_id.distinct()).label('txn_count'),
        func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).label('total_revenue')
    ).select_from(Transaction).join(
        StaffSession, Transaction.session_id == StaffSession.id
    ).join(
        TransactionItem, Transaction.transaction_id == TransactionItem.transaction_id
    ).filter(
        Transaction.store_id == store_id,
        StaffSession.user_id == user_id,
        func.date(Transaction.created_at) >= thirty_days_ago,
        Transaction.is_return == False
    ).group_by(func.date(Transaction.created_at)).order_by(func.date(Transaction.created_at).desc()).all()

    targets = db.session.query(StaffDailyTarget).filter(
        StaffDailyTarget.store_id == store_id,
        StaffDailyTarget.user_id == user_id,
        StaffDailyTarget.target_date >= thirty_days_ago
    ).all()
    target_map = {t.target_date: t for t in targets}

    history = []
    for stat in daily_stats:
        t_date = stat.txn_date
        # Handle t_date type, depending on DB driver might be string or native date
        if isinstance(t_date, str):
            t_date = datetime.strptime(t_date, '%Y-%m-%d').date()

        target = target_map.get(t_date)
        target_revenue = float(target.revenue_target) if target and target.revenue_target else None
        rev = float(stat.total_revenue) if stat.total_revenue else 0.0

        history.append({
            "date": t_date.isoformat(),
            "revenue": round(rev, 2),
            "transaction_count": int(stat.txn_count),
            "target_revenue": target_revenue,
            "target_pct_achieved": round((rev / target_revenue * 100), 2) if target_revenue and target_revenue > 0 else None
        })

    return format_response(True, data={
        "user_id": user_id,
        "name": staff.full_name or staff.mobile_number,
        "history": history
    }), 200

@staff_performance_bp.route('/targets', methods=['PUT'])
@require_auth
@require_role('owner')
def upsert_staff_target():
    """OWNER ONLY: Upserts a staff daily target."""
    store_id = g.current_user['store_id']
    data = request.json

    user_id = data.get('user_id')
    target_date_str = data.get('target_date')
    revenue_target = data.get('revenue_target')
    txn_count_target = data.get('transaction_count_target')

    if not all([user_id, target_date_str]):
        return format_response(False, error={"message": "Missing user_id or target_date"}), 400

    try:
        t_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        return format_response(False, error={"message": "Invalid date format, use YYYY-MM-DD"}), 400

    # verify user
    staff = db.session.query(User).filter(User.user_id == user_id, User.store_id == store_id).first()
    if not staff:
        return format_response(False, error={"message": "User not found in this store"}), 404

    target = db.session.query(StaffDailyTarget).filter(
        StaffDailyTarget.store_id == store_id,
        StaffDailyTarget.user_id == user_id,
        StaffDailyTarget.target_date == t_date
    ).first()

    if not target:
        target = StaffDailyTarget(
            store_id=store_id,
            user_id=user_id,
            target_date=t_date
        )
        db.session.add(target)

    if revenue_target is not None:
        target.revenue_target = revenue_target
    if txn_count_target is not None:
        target.transaction_count_target = txn_count_target

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to upsert target: {e}")
        return format_response(False, error={"message": "Database error"}), 500

    return format_response(True, data={"message": "Target updated successfully"}), 200
