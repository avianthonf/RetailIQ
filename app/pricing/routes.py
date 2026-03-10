"""
Pricing API Routes
==================
All endpoints require JWT auth. Store-scoped via g.current_user['store_id'].
"""

from datetime import datetime, timezone

from flask import g, request
from sqlalchemy import text

from app import db
from app.auth.decorators import require_auth
from app.auth.utils import format_response
from app.models import PricingRule, PricingSuggestion, Product, ProductPriceHistory

from . import pricing_bp

# ── helpers ──────────────────────────────────────────────────────────────────


def _store_id() -> int:
    return int(g.current_user["store_id"])


def _user_id() -> int:
    return int(g.current_user["user_id"])


# ── 1. List PENDING suggestions ───────────────────────────────────────────────


@pricing_bp.route("/suggestions", methods=["GET"])
@require_auth
def list_suggestions():
    store_id = _store_id()
    rows = db.session.execute(
        text("""
            SELECT
                ps.id,
                ps.product_id,
                p.name          AS product_name,
                ps.current_price,
                ps.suggested_price,
                ps.price_change_pct,
                ps.reason,
                ps.confidence,
                ps.status,
                ps.created_at,
                -- margin impact: (suggested - cost) / suggested vs current margin
                p.cost_price,
                CASE WHEN ps.suggested_price > 0
                     THEN (ps.suggested_price - p.cost_price) / ps.suggested_price * 100
                     ELSE NULL END AS suggested_margin_pct,
                CASE WHEN ps.current_price > 0
                     THEN (ps.current_price - p.cost_price) / ps.current_price * 100
                     ELSE NULL END AS current_margin_pct
            FROM pricing_suggestions ps
            JOIN products p ON p.product_id = ps.product_id
            WHERE ps.store_id = :sid
              AND ps.status   = 'PENDING'
            ORDER BY ps.created_at DESC
        """),
        {"sid": store_id},
    ).fetchall()

    data = [
        {
            "id": r.id,
            "product_id": r.product_id,
            "product_name": r.product_name,
            "current_price": float(r.current_price) if r.current_price else None,
            "suggested_price": float(r.suggested_price) if r.suggested_price else None,
            "price_change_pct": float(r.price_change_pct) if r.price_change_pct else None,
            "reason": r.reason,
            "confidence": r.confidence,
            "status": r.status,
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else r.created_at,
            "current_margin_pct": round(float(r.current_margin_pct), 2) if r.current_margin_pct else None,
            "suggested_margin_pct": round(float(r.suggested_margin_pct), 2) if r.suggested_margin_pct else None,
        }
        for r in rows
    ]
    return format_response(True, data=data), 200


# ── 2. Apply a suggestion ─────────────────────────────────────────────────────


@pricing_bp.route("/suggestions/<int:suggestion_id>/apply", methods=["POST"])
@require_auth
def apply_suggestion(suggestion_id: int):
    store_id = _store_id()
    user_id = _user_id()

    suggestion = db.session.query(PricingSuggestion).filter_by(id=suggestion_id, store_id=store_id).first()

    if not suggestion:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Suggestion not found"}), 404

    if suggestion.status != "PENDING":
        return format_response(
            False,
            error={
                "code": "ALREADY_ACTIONED",
                "message": f"Suggestion already {suggestion.status}",
            },
        ), 409

    product = db.session.query(Product).filter_by(product_id=suggestion.product_id, store_id=store_id).first()
    if not product:
        return format_response(False, error={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"}), 404

    old_price = float(product.selling_price) if product.selling_price else None

    # Update product price
    product.selling_price = suggestion.suggested_price

    # Record in product_price_history
    history_row = ProductPriceHistory(
        product_id=product.product_id,
        store_id=store_id,
        old_price=old_price,
        new_price=float(suggestion.suggested_price),
        # legacy compat
        selling_price=float(suggestion.suggested_price),
        cost_price=float(product.cost_price) if product.cost_price else None,
        reason=f"pricing_suggestion:{suggestion_id}",
        changed_at=datetime.now(timezone.utc),
        changed_by=user_id,
    )
    db.session.add(history_row)

    # Mark suggestion APPLIED
    suggestion.status = "APPLIED"
    suggestion.actioned_at = datetime.now(timezone.utc)

    db.session.commit()

    return format_response(
        True,
        data={
            "suggestion_id": suggestion_id,
            "product_id": product.product_id,
            "old_price": old_price,
            "new_price": float(suggestion.suggested_price),
            "status": "APPLIED",
        },
    ), 200


# ── 3. Dismiss a suggestion ───────────────────────────────────────────────────


@pricing_bp.route("/suggestions/<int:suggestion_id>/dismiss", methods=["POST"])
@require_auth
def dismiss_suggestion(suggestion_id: int):
    store_id = _store_id()

    suggestion = db.session.query(PricingSuggestion).filter_by(id=suggestion_id, store_id=store_id).first()

    if not suggestion:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Suggestion not found"}), 404

    if suggestion.status != "PENDING":
        return format_response(
            False,
            error={
                "code": "ALREADY_ACTIONED",
                "message": f"Suggestion already {suggestion.status}",
            },
        ), 409

    suggestion.status = "DISMISSED"
    suggestion.actioned_at = datetime.now(timezone.utc)
    db.session.commit()

    return format_response(True, data={"suggestion_id": suggestion_id, "status": "DISMISSED"}), 200


# ── 4. Price history for a product ────────────────────────────────────────────


@pricing_bp.route("/history", methods=["GET"])
@require_auth
def price_history():
    _store_id()
    product_id = request.args.get("product_id", type=int)

    if not product_id:
        return format_response(False, error={"code": "MISSING_PARAM", "message": "product_id is required"}), 400

    rows = (
        db.session.query(ProductPriceHistory)
        .filter_by(product_id=product_id)
        .order_by(ProductPriceHistory.changed_at.desc())
        .limit(100)
        .all()
    )

    data = [
        {
            "id": r.id,
            "product_id": r.product_id,
            "store_id": r.store_id,
            "old_price": float(r.old_price) if r.old_price else None,
            "new_price": float(r.new_price) if r.new_price else None,
            "reason": r.reason,
            "changed_at": r.changed_at.isoformat() if hasattr(r.changed_at, "isoformat") else r.changed_at,
            "changed_by": r.changed_by,
        }
        for r in rows
    ]
    return format_response(True, data=data), 200


# ── 5. Pricing rules (GET + PUT) ──────────────────────────────────────────────


@pricing_bp.route("/rules", methods=["GET"])
@require_auth
def get_pricing_rules():
    store_id = _store_id()
    rules = db.session.query(PricingRule).filter_by(store_id=store_id).all()

    data = [
        {
            "id": r.id,
            "store_id": r.store_id,
            "rule_type": r.rule_type,
            "parameters": r.parameters,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else r.created_at,
        }
        for r in rules
    ]
    return format_response(True, data=data), 200


@pricing_bp.route("/rules", methods=["PUT"])
@require_auth
def upsert_pricing_rules():
    store_id = _store_id()
    payload = request.json or {}

    rule_type = payload.get("rule_type")
    parameters = payload.get("parameters", {})
    is_active = payload.get("is_active", True)

    if not rule_type:
        return format_response(False, error={"code": "MISSING_FIELD", "message": "rule_type is required"}), 400

    existing = db.session.query(PricingRule).filter_by(store_id=store_id, rule_type=rule_type).first()

    if existing:
        existing.parameters = parameters
        existing.is_active = is_active
        rule = existing
    else:
        rule = PricingRule(
            store_id=store_id,
            rule_type=rule_type,
            parameters=parameters,
            is_active=is_active,
        )
        db.session.add(rule)

    db.session.commit()

    return format_response(
        True,
        data={
            "id": rule.id,
            "store_id": rule.store_id,
            "rule_type": rule.rule_type,
            "parameters": rule.parameters,
            "is_active": rule.is_active,
        },
    ), 200
