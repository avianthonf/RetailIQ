"""
RetailIQ Decisions Engine
===========================
Rule-based decision engine for actionable recommendations.
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def build_context(session, store_id: int) -> list[dict]:
    """Build decision context from live DB data."""
    contexts = []
    try:
        from sqlalchemy import text

        # Low stock alerts
        rows = session.execute(
            text("""
            SELECT product_id, name, current_stock, reorder_level, selling_price
            FROM products
            WHERE store_id = :sid AND is_active = TRUE
              AND current_stock <= reorder_level
            LIMIT 50
            """),
            {"sid": store_id},
        ).fetchall()

        for r in rows:
            contexts.append(
                {
                    "type": "LOW_STOCK",
                    "product_id": r.product_id,
                    "product_name": r.name,
                    "current_stock": float(r.current_stock or 0),
                    "reorder_level": float(r.reorder_level or 0),
                    "selling_price": float(r.selling_price or 0),
                }
            )

        # Margin warnings (cost > 90% of selling price)
        margin_rows = session.execute(
            text("""
            SELECT product_id, name, cost_price, selling_price
            FROM products
            WHERE store_id = :sid AND is_active = TRUE
              AND cost_price IS NOT NULL AND selling_price IS NOT NULL
              AND selling_price > 0
              AND cost_price / selling_price > 0.9
            LIMIT 20
            """),
            {"sid": store_id},
        ).fetchall()

        for r in margin_rows:
            contexts.append(
                {
                    "type": "MARGIN_WARNING",
                    "product_id": r.product_id,
                    "product_name": r.name,
                    "cost_price": float(r.cost_price),
                    "selling_price": float(r.selling_price),
                    "margin_pct": round((1 - float(r.cost_price) / float(r.selling_price)) * 100, 2),
                }
            )

    except Exception as exc:
        logger.warning("build_context error: %s", exc)

    return contexts


def evaluate_rules(contexts: list[dict]) -> list[dict]:
    """Evaluate rules against contexts and return actionable recommendations."""
    actions = []

    for ctx in contexts:
        if ctx["type"] == "LOW_STOCK":
            deficit = max(0, ctx["reorder_level"] - ctx["current_stock"])
            actions.append(
                {
                    "id": f"low_stock_{ctx['product_id']}",
                    "type": "REORDER",
                    "priority": "HIGH" if ctx["current_stock"] <= 0 else "MEDIUM",
                    "product_id": ctx["product_id"],
                    "product_name": ctx["product_name"],
                    "title": f"Reorder {ctx['product_name']}",
                    "message": (
                        f"Stock is at {ctx['current_stock']} units "
                        f"(reorder level: {ctx['reorder_level']}). "
                        f"Suggested order qty: {deficit:.0f} units."
                    ),
                    "suggested_qty": deficit,
                    "available_actions": ["Acknowledge"],
                }
            )

        elif ctx["type"] == "MARGIN_WARNING":
            actions.append(
                {
                    "id": f"margin_{ctx['product_id']}",
                    "type": "PRICE_ADJUSTMENT",
                    "priority": "MEDIUM",
                    "product_id": ctx["product_id"],
                    "product_name": ctx["product_name"],
                    "title": f"Low margin on {ctx['product_name']}",
                    "message": (
                        f"Margin is only {ctx['margin_pct']}%. "
                        f"Cost: {ctx['cost_price']}, Selling: {ctx['selling_price']}."
                    ),
                    "available_actions": ["Acknowledge"],
                }
            )

    return actions


def _dedup_and_sort(rules: list[dict]) -> list[dict]:
    """Deduplicate rules by (rule_name, product_id) keeping highest confidence,
    then sort by time_sensitive (desc), priority (desc), confidence (desc)."""
    best = {}
    for r in rules:
        key = (r["rule_name"], r.get("product_id"))
        if key not in best or r["confidence"] > best[key]["confidence"]:
            best[key] = r

    deduped = list(best.values())
    deduped.sort(
        key=lambda x: (x.get("time_sensitive", False), x.get("priority", 0), x.get("confidence", 0)),
        reverse=True,
    )
    return deduped
