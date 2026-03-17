"""
RetailIQ Market Intelligence Routes
=====================================
Standard Flask blueprint (replaces the flask-restx Namespace version).
"""

from datetime import datetime, timedelta, timezone

from flask import current_app, g, request
from sqlalchemy import desc, select

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import DataSource, IntelligenceReport, MarketAlert, MarketSignal, PriceIndex
from . import market_intelligence_bp
from .engine import IntelligenceEngine


@market_intelligence_bp.route("/")
@market_intelligence_bp.route("/summary")
@require_auth
@require_role("owner")
def market_summary():
    try:
        summary = IntelligenceEngine.get_market_summary(session=db.session)
        return format_response(data=summary)
    except Exception as e:
        current_app.logger.error("market_summary error: %s", e)
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)


@market_intelligence_bp.route("/signals")
@require_auth
@require_role("owner")
def list_signals():
    try:
        category_id = request.args.get("category_id", type=int)
        signal_type = request.args.get("signal_type", type=str)
        limit = min(request.args.get("limit", default=50, type=int), 100)

        stmt = select(MarketSignal).order_by(desc(MarketSignal.timestamp)).limit(limit)
        if category_id:
            stmt = stmt.where(MarketSignal.category_id == category_id)
        if signal_type:
            stmt = stmt.where(MarketSignal.signal_type == signal_type)

        signals = db.session.execute(stmt).scalars().all()
        data = [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "source_id": s.source_id,
                "category_id": s.category_id,
                "region_code": s.region_code,
                "value": float(s.value) if s.value is not None else None,
                "confidence": float(s.confidence) if s.confidence is not None else None,
                "quality_score": float(s.quality_score) if s.quality_score is not None else None,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in signals
        ]
        return format_response(data=data)
    except Exception as e:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)


@market_intelligence_bp.route("/indices")
@require_auth
@require_role("owner")
def list_indices():
    try:
        category_id = request.args.get("category_id", type=int)
        days = request.args.get("days", default=30, type=int)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = select(PriceIndex).where(PriceIndex.computed_at >= start_date)
        if category_id:
            stmt = stmt.where(PriceIndex.category_id == category_id)
        stmt = stmt.order_by(PriceIndex.computed_at.asc())
        indices = db.session.execute(stmt).scalars().all()

        data = [
            {
                "id": idx.id,
                "category_id": idx.category_id,
                "region_code": idx.region_code,
                "index_value": float(idx.index_value) if idx.index_value is not None else None,
                "computation_method": idx.computation_method,
                "computed_at": idx.computed_at.isoformat(),
            }
            for idx in indices
        ]
        return format_response(data=data)
    except Exception as e:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)


@market_intelligence_bp.route("/indices/compute", methods=["POST"])
@require_auth
@require_role("owner")
def compute_index():
    try:
        category_id = request.args.get("category_id", type=int) or (request.json or {}).get("category_id")
        if not category_id:
            return format_response(
                success=False, error={"code": "BAD_REQUEST", "message": "category_id required"}, status_code=400
            )
        index_value = IntelligenceEngine.compute_price_index(category_id, session=db.session)
        if index_value is None:
            return format_response(
                success=False, error={"code": "NO_DATA", "message": "Insufficient signals"}, status_code=404
            )
        return format_response(data={"category_id": category_id, "new_index": index_value})
    except Exception as e:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)


@market_intelligence_bp.route("/alerts")
@require_auth
@require_role("owner")
def list_alerts():
    merchant_id = g.current_user["store_id"]
    try:
        unack_only = request.args.get("unacknowledged_only", "true").lower() == "true"
        stmt = select(MarketAlert).where(MarketAlert.merchant_id == merchant_id)
        if unack_only:
            stmt = stmt.where(MarketAlert.acknowledged.is_(False))
        stmt = stmt.order_by(desc(MarketAlert.created_at)).limit(50)
        alerts = db.session.execute(stmt).scalars().all()
        data = [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "recommended_action": a.recommended_action,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
        return format_response(data=data)
    except Exception as e:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)


@market_intelligence_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
@require_auth
@require_role("owner")
def acknowledge_alert(alert_id):
    merchant_id = g.current_user["store_id"]
    try:
        alert = db.session.get(MarketAlert, alert_id)
        if not alert or alert.merchant_id != merchant_id:
            return format_response(
                success=False, error={"code": "NOT_FOUND", "message": "Alert not found"}, status_code=404
            )
        alert.acknowledged = True
        db.session.commit()
        return format_response(data={"id": alert.id, "acknowledged": True})
    except Exception as e:
        db.session.rollback()
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(e)}, status_code=500)
