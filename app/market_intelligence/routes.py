"""
REST API endpoints for real-time market intelligence.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from flask import current_app, jsonify, request
from flask_restx import Namespace, Resource, fields
from sqlalchemy import desc, select

from app import db
from app.auth.decorators import require_auth, require_role
from app.auth.utils import format_response
from app.models import DataSource, IntelligenceReport, MarketAlert, MarketSignal, PriceIndex

from .engine import IntelligenceEngine

api = Namespace("market_intelligence", description="Real-Time Market Intelligence API", path="/")

# Define response models for documentation
market_signal_model = api.model(
    "MarketSignal",
    {
        "id": fields.Integer(readOnly=True, description="Signal ID"),
        "signal_type": fields.String(required=True, description="Type (PRICE, DEMAND, SUPPLY, EVENT, SENTIMENT)"),
        "source_id": fields.Integer(description="Source ID"),
        "category_id": fields.Integer(description="Category ID"),
        "region_code": fields.String(description="Region code (e.g., US)"),
        "value": fields.Float(required=True, description="Signal value"),
        "confidence": fields.Float(description="Confidence score (0-1)"),
        "quality_score": fields.Float(description="Overall quality score (0-1)"),
        "timestamp": fields.DateTime(description="Signal timestamp"),
    },
)


@api.route("/summary")
class MarketSummaryResource(Resource):
    @require_auth
    @require_role("owner", "manager")
    def get(self):
        """Get high-level market summary"""
        try:
            summary = IntelligenceEngine.get_market_summary()
            return format_response(True, data=summary)
        except Exception as e:
            current_app.logger.error(f"Error fetching market summary: {e}")
            return format_response(
                False, error={"code": "INTERNAL_ERROR", "message": "Failed to generate market summary"}
            ), 500


@api.route("/signals")
class MarketSignalListResource(Resource):
    @require_auth
    @require_role("owner", "manager", "staff")
    @api.doc(
        params={
            "category_id": "Filter by category",
            "signal_type": "Filter by type (PRICE, DEMAND, etc.)",
            "limit": "Number of signals (max 100)",
        }
    )
    def get(self):
        """Retrieve recent market signals"""
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

            return format_response(True, data=data)
        except Exception as e:
            current_app.logger.error(f"Error fetching market signals: {e}")
            return format_response(False, error={"code": "INTERNAL_ERROR", "message": "Failed to fetch signals"}), 500


@api.route("/indices")
class PriceIndexResource(Resource):
    @require_auth
    @require_role("owner", "manager")
    @api.doc(params={"category_id": "Filter by category", "days": "Days of history to retrieve (default 30)"})
    def get(self):
        """Retrieve price indices time-series"""
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

            return format_response(True, data=data)
        except Exception as e:
            current_app.logger.error(f"Error fetching price indices: {e}")
            return format_response(False, error={"code": "INTERNAL_ERROR", "message": "Failed to fetch indices"}), 500


@api.route("/indices/compute")
class ComputeIndexResource(Resource):
    @require_auth
    @require_role("owner", "manager")
    @api.doc(params={"category_id": "Category to compute index for"})
    def post(self):
        """Trigger ad-hoc price index recomputation"""
        try:
            category_id = request.args.get("category_id", type=int)
            if not category_id:
                return format_response(False, error={"code": "BAD_REQUEST", "message": "category_id required"}), 400

            index_value = IntelligenceEngine.compute_price_index(category_id)

            if index_value is None:
                return format_response(
                    False, error={"code": "NO_DATA", "message": "Insufficient signals to compute index"}
                ), 404

            return format_response(True, data={"category_id": category_id, "new_index": index_value})
        except Exception as e:
            current_app.logger.error(f"Error computing index: {e}")
            return format_response(False, error={"code": "INTERNAL_ERROR", "message": "Failed to compute index"}), 500


@api.route("/alerts")
class MarketAlertListResource(Resource):
    @require_auth
    @require_role("owner", "manager")
    @api.doc(params={"unacknowledged_only": "boolean"})
    def get(self):
        """Get market alerts for the current merchant"""
        from flask import g

        merchant_id = g.current_user["store_id"]

        try:
            unack_only = request.args.get("unacknowledged_only", "true").lower() == "true"

            stmt = select(MarketAlert).where(MarketAlert.merchant_id == merchant_id)
            if unack_only:
                stmt = stmt.where(MarketAlert.acknowledged == False)

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

            return format_response(True, data=data)
        except Exception as e:
            current_app.logger.error(f"Error fetching alerts: {e}")
            return format_response(False, error={"code": "INTERNAL_ERROR", "message": "Failed to fetch alerts"}), 500


@api.route("/alerts/<int:alert_id>/acknowledge")
class MarketAlertAckResource(Resource):
    @require_auth
    @require_role("owner", "manager")
    def post(self, alert_id):
        """Acknowledge a market alert"""
        from flask import g

        merchant_id = g.current_user["store_id"]

        try:
            alert = db.session.get(MarketAlert, alert_id)
            if not alert or alert.merchant_id != merchant_id:
                return format_response(False, error={"code": "NOT_FOUND", "message": "Alert not found"}), 404

            alert.acknowledged = True
            db.session.commit()

            return format_response(True, data={"id": alert.id, "acknowledged": True})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error acknowledging alert: {e}")
            return format_response(
                False, error={"code": "INTERNAL_ERROR", "message": "Failed to acknowledge alert"}
            ), 500
