"""
RetailIQ Market Intelligence Routes
=====================================
Standard Flask blueprint (replaces the flask-restx Namespace version).
"""

from datetime import datetime, timedelta, timezone

from flask import current_app, g, request
from sqlalchemy import desc, func, select

from .. import db
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import Category, DataSource, IntelligenceReport, MarketAlert, MarketSignal, PriceIndex, Product
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


@market_intelligence_bp.route("/competitors")
@require_auth
@require_role("owner")
def list_competitors():
    try:
        region = request.args.get("region")
        stmt = (
            select(
                MarketSignal.source_id,
                MarketSignal.region_code,
                func.count(MarketSignal.id).label("signal_count"),
                func.avg(MarketSignal.value).label("average_price"),
            )
            .group_by(MarketSignal.source_id, MarketSignal.region_code)
            .order_by(desc(func.count(MarketSignal.id)))
        )
        if region:
            stmt = stmt.where(MarketSignal.region_code == region)

        rows = db.session.execute(stmt).all()
        overall_average = db.session.query(func.avg(MarketSignal.value)).scalar() or 0
        competitors = []
        for row in rows:
            source = db.session.get(DataSource, row.source_id) if row.source_id else None
            avg_price = float(row.average_price or 0)
            if overall_average and avg_price > float(overall_average) * 1.1:
                strategy = "PREMIUM"
            elif overall_average and avg_price < float(overall_average) * 0.9:
                strategy = "VALUE"
            else:
                strategy = "COMPETITIVE"

            competitors.append(
                {
                    "competitor_id": str(row.source_id or row.region_code or "unknown"),
                    "name": source.name if source else f"Competitor {row.source_id or row.region_code or 'Unknown'}",
                    "region": row.region_code or "GLOBAL",
                    "total_products": int(row.signal_count or 0),
                    "average_pricing": avg_price,
                    "pricing_strategy": strategy,
                    "market_share": round(min((int(row.signal_count or 0) / max(len(rows), 1)) * 100, 100), 2),
                    "strengths": ["Strong price visibility", "Active regional presence"],
                    "weaknesses": ["Limited signal coverage"] if int(row.signal_count or 0) < 3 else [],
                    "last_analyzed": datetime.now(timezone.utc).isoformat(),
                    "price_comparison": [],
                }
            )
        return format_response(True, data=competitors)
    except Exception as exc:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(exc)}, status_code=500)


@market_intelligence_bp.route("/competitors/<competitor_id>")
@require_auth
@require_role("owner")
def get_competitor(competitor_id):
    try:
        source = db.session.get(DataSource, int(competitor_id)) if competitor_id.isdigit() else None
        signals = (
            db.session.query(MarketSignal)
            .filter(MarketSignal.source_id == (source.id if source else None))
            .order_by(MarketSignal.timestamp.desc())
            .limit(20)
            .all()
        )
        if not signals and source is None:
            return format_response(
                success=False,
                error={"code": "NOT_FOUND", "message": "Competitor not found"},
                status_code=404,
            )

        avg_price = sum(float(signal.value or 0) for signal in signals) / len(signals) if signals else 0
        payload = {
            "competitor_id": competitor_id,
            "name": source.name if source else f"Competitor {competitor_id}",
            "region": signals[0].region_code if signals else "GLOBAL",
            "total_products": len(signals),
            "average_pricing": avg_price,
            "pricing_strategy": "COMPETITIVE",
            "market_share": 0,
            "strengths": ["Recent market activity"],
            "weaknesses": [],
            "last_analyzed": datetime.now(timezone.utc).isoformat(),
            "price_comparison": [
                {
                    "category": str(signal.category_id or "unknown"),
                    "competitor_price": float(signal.value or 0),
                    "our_price": float(signal.value or 0),
                    "difference": 0.0,
                }
                for signal in signals[:5]
            ],
        }
        return format_response(True, data=payload)
    except Exception as exc:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(exc)}, status_code=500)


@market_intelligence_bp.route("/forecasts")
@require_auth
@require_role("owner")
def demand_forecasts():
    try:
        store_id = g.current_user["store_id"]
        product_id = request.args.get("product_id", type=int)
        query = db.session.query(Product).filter_by(store_id=store_id)
        if product_id:
            query = query.filter_by(product_id=product_id)
        products = query.limit(25).all()

        forecasts = []
        for product in products:
            relevant_signals = (
                db.session.query(MarketSignal)
                .filter(MarketSignal.category_id == product.category_id)
                .order_by(MarketSignal.timestamp.desc())
                .limit(10)
                .all()
            )
            current_demand = max(float(product.current_stock or 0), 0)
            signal_bias = (
                sum(float(signal.value or 0) for signal in relevant_signals) / len(relevant_signals)
                if relevant_signals
                else 0
            )
            forecast_demand = max(current_demand + signal_bias, 0)
            forecasts.append(
                {
                    "product_id": str(product.product_id),
                    "product_name": product.name,
                    "sku": product.sku_code or str(product.product_id),
                    "current_demand": round(current_demand, 2),
                    "forecast_demand": round(forecast_demand, 2),
                    "forecast_period": request.args.get("to_period") or "next_30_days",
                    "confidence_score": 0.75 if relevant_signals else 0.5,
                    "factors": [
                        {
                            "factor": "market_signals",
                            "impact": round(signal_bias, 2),
                            "description": "Derived from recent category-level market signals.",
                        }
                    ],
                    "recommendations": [
                        "Increase buffer stock"
                        if forecast_demand > current_demand
                        else "Current inventory looks sufficient"
                    ],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return format_response(True, data=forecasts)
    except Exception as exc:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(exc)}, status_code=500)


@market_intelligence_bp.route("/forecasts/generate", methods=["POST"])
@require_auth
@require_role("owner")
def generate_demand_forecast():
    try:
        body = request.json or {}
        product_id = body.get("product_id")
        if not product_id:
            return format_response(
                success=False,
                error={"code": "BAD_REQUEST", "message": "product_id required"},
                status_code=400,
            )

        store_id = g.current_user["store_id"]
        product = db.session.query(Product).filter_by(store_id=store_id, product_id=product_id).first()
        if not product:
            return format_response(
                success=False,
                error={"code": "NOT_FOUND", "message": "Product not found"},
                status_code=404,
            )

        relevant_signals = (
            db.session.query(MarketSignal)
            .filter(MarketSignal.category_id == product.category_id)
            .order_by(MarketSignal.timestamp.desc())
            .limit(10)
            .all()
        )
        current_demand = max(float(product.current_stock or 0), 0)
        signal_bias = (
            sum(float(signal.value or 0) for signal in relevant_signals) / len(relevant_signals)
            if relevant_signals
            else 0
        )
        forecast = {
            "product_id": str(product.product_id),
            "product_name": product.name,
            "sku": product.sku_code or str(product.product_id),
            "current_demand": round(current_demand, 2),
            "forecast_demand": round(max(current_demand + signal_bias, 0), 2),
            "forecast_period": body.get("forecast_period") or "next_30_days",
            "confidence_score": 0.75 if relevant_signals else 0.5,
            "factors": [
                {
                    "factor": "market_signals",
                    "impact": round(signal_bias, 2),
                    "description": "Derived from recent category-level market signals.",
                }
            ],
            "recommendations": [
                "Increase buffer stock"
                if current_demand + signal_bias > current_demand
                else "Current inventory looks sufficient"
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return format_response(True, data=forecast)
    except Exception as exc:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(exc)}, status_code=500)


@market_intelligence_bp.route("/recommendations")
@require_auth
@require_role("owner")
def get_recommendations():
    try:
        store_id = g.current_user["store_id"]
        alerts = (
            db.session.query(MarketAlert)
            .filter_by(merchant_id=store_id)
            .order_by(MarketAlert.created_at.desc())
            .limit(10)
            .all()
        )
        indices = db.session.query(PriceIndex).order_by(PriceIndex.computed_at.desc()).limit(10).all()

        recommendations = []
        for alert in alerts:
            rec_type = "STOCK" if "STOCK" in (alert.alert_type or "") else "PRICING"
            recommendations.append(
                {
                    "id": f"alert-{alert.id}",
                    "type": rec_type,
                    "priority": "HIGH" if alert.severity in {"HIGH", "CRITICAL"} else "MEDIUM",
                    "title": alert.alert_type.replace("_", " ").title(),
                    "description": alert.message,
                    "expected_impact": alert.recommended_action or "Protect store performance.",
                    "effort_required": "MEDIUM",
                    "due_date": alert.created_at.isoformat() if alert.created_at else None,
                    "status": "PENDING" if not alert.acknowledged else "COMPLETED",
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                }
            )

        for index in indices[: max(0, 10 - len(recommendations))]:
            recommendations.append(
                {
                    "id": f"index-{index.id}",
                    "type": "PRICING",
                    "priority": "LOW",
                    "title": f"Review pricing for category {index.category_id}",
                    "description": f"Latest market index in {index.region_code or 'default region'} is {float(index.index_value or 0):.2f}.",
                    "expected_impact": "Keep pricing aligned with the latest market movement.",
                    "effort_required": "LOW",
                    "due_date": index.computed_at.isoformat() if index.computed_at else None,
                    "status": "PENDING",
                    "created_at": index.computed_at.isoformat() if index.computed_at else None,
                }
            )

        return format_response(True, data=recommendations)
    except Exception as exc:
        return format_response(success=False, error={"code": "INTERNAL_ERROR", "message": str(exc)}, status_code=500)
