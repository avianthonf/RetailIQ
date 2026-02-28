from flask import Blueprint, request, jsonify
from app import db
from app.auth.decorators import require_auth
from app.nlp.router import resolve_intent
from app.nlp.templates import TEMPLATES, format_percentage, format_currency, format_unit
from sqlalchemy import text

nlp_bp = Blueprint('nlp', __name__)

@nlp_bp.route('/', methods=['POST'])
@require_auth
def handle_query():
    from flask import g
    store_id = g.current_user['store_id']
    query = request.json.get("query_text", "")
    
    intent = resolve_intent(query)
    tmpl = TEMPLATES.get(intent, TEMPLATES["default"])
    
    detail = ""
    action = tmpl.get("action", "")
    headline = tmpl.get("headline", "")
    supporting_metrics = {}
    
    if intent == "forecast":
        row = db.session.execute(text("""
            SELECT SUM(forecast_value) as fc, MAX(regime) as reg
            FROM forecast_cache
            WHERE store_id = :sid AND forecast_date >= CURRENT_DATE AND forecast_date < CURRENT_DATE + 7
        """), {"sid": store_id}).fetchone()
        fc = float(row.fc or 0.0) if row and row.fc else 0.0
        reg = (row.reg or "Stable") if row else "Stable"
        detail = tmpl["detail_template"].format(forecast=format_unit(fc), regime=reg)
        action = tmpl["action"].format(lead_time="standard")
        supporting_metrics = {"forecast_7d": fc, "regime": reg}
        
    elif intent == "inventory":
        # Fetch most critical inventory item
        row = db.session.execute(text("""
            SELECT p.product_id, p.name, p.current_stock, p.reorder_level,
                   (p.reorder_level - p.current_stock) as deficit
            FROM products p
            WHERE p.store_id = :sid AND p.is_active = TRUE
                  AND p.current_stock <= p.reorder_level
            ORDER BY deficit DESC
            LIMIT 1
        """), {"sid": store_id}).fetchone()
        if row:
            detail = tmpl["detail_template"].format(
                stock=format_unit(float(row.current_stock or 0)),
                reorder=format_unit(float(row.reorder_level or 0)),
                deficit=format_unit(float(row.deficit or 0))
            )
            supporting_metrics = {
                "product_id": row.product_id,
                "product_name": row.name,
                "current_stock": float(row.current_stock or 0),
                "reorder_level": float(row.reorder_level or 0)
            }
        else:
            detail = "All products are above their reorder levels."
            action = "No restocking action required."
        
    elif intent == "revenue":
        # Cache CURRENT_DATE once instead of subquerying per row
        current_date = db.session.execute(text("SELECT CURRENT_DATE")).scalar()
        
        store_hist = db.session.execute(text("""
            SELECT date, revenue FROM daily_store_summary
            WHERE store_id = :sid AND date >= CURRENT_DATE - 8 AND date <= CURRENT_DATE
        """), {"sid": store_id}).fetchall()
        
        today_rev = 0.0
        past_7 = []
        for r in store_hist:
            if r.date == current_date:
                today_rev = float(r.revenue or 0.0)
            else:
                past_7.append(float(r.revenue or 0.0))
        
        ma_7d = sum(past_7) / 7.0 if len(past_7) == 7 else (sum(past_7) / max(1, len(past_7)) if past_7 else 0.0)
            
        delta = ((today_rev - ma_7d) / ma_7d * 100) if ma_7d > 0 else 0.0
        
        detail = tmpl["detail_template"].format(revenue=format_currency(today_rev), ma_7d=format_currency(ma_7d))
        action = tmpl.get("action_template", "").format(delta_pct=format_percentage(delta))
        supporting_metrics = {"today_revenue": today_rev, "ma_7d": round(ma_7d, 2), "delta_pct": round(delta, 1)}
        
    elif intent == "profit":
        # Aggregate margin data across active products
        rows = db.session.execute(text("""
            SELECT AVG(CASE WHEN selling_price > 0 
                        THEN (selling_price - cost_price) / selling_price * 100 
                        ELSE 0 END) as avg_margin,
                   COUNT(*) as product_count
            FROM products
            WHERE store_id = :sid AND is_active = TRUE AND cost_price IS NOT NULL AND selling_price IS NOT NULL
        """), {"sid": store_id}).fetchone()
        avg_margin = float(rows.avg_margin or 0.0) if rows else 0.0
        detail = tmpl["detail_template"].format(margin=format_percentage(avg_margin))
        supporting_metrics = {"avg_margin_pct": round(avg_margin, 1), "product_count": int(rows.product_count or 0) if rows else 0}
        
    elif intent == "top_products":
        # Top 5 by revenue last 30 days
        rows = db.session.execute(text("""
            SELECT d.product_id, p.name, SUM(d.revenue) as total_rev, SUM(d.units_sold) as total_units
            FROM daily_sku_summary d
            JOIN products p ON p.product_id = d.product_id
            WHERE d.store_id = :sid AND d.date >= CURRENT_DATE - 30
            GROUP BY d.product_id, p.name
            ORDER BY total_rev DESC, d.product_id ASC
            LIMIT 5
        """), {"sid": store_id}).fetchall()
        
        if rows:
            top_list = [{"product_id": r.product_id, "name": r.name, 
                         "revenue": float(r.total_rev or 0), "units": float(r.total_units or 0)} for r in rows]
            detail = tmpl["detail_template"].format(
                value=", ".join(f"{r['name']} ({format_currency(r['revenue'])})" for r in top_list)
            )
            supporting_metrics = {"top_products": top_list}
        else:
            detail = "No sales data available for the last 30 days."

    elif intent == "loyalty_summary":
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc)
        start_date = f"{today.year}-{today.month:02d}-01"
        
        row = db.session.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM customer_loyalty_accounts WHERE store_id = :sid) as enrolled,
                (SELECT COALESCE(SUM(points), 0) FROM loyalty_transactions lt
                 JOIN customer_loyalty_accounts c ON c.id = lt.account_id
                 WHERE c.store_id = :sid AND lt.type = 'EARN' AND lt.created_at >= :start_date) as issued,
                (SELECT COALESCE(SUM(points), 0) FROM loyalty_transactions lt
                 JOIN customer_loyalty_accounts c ON c.id = lt.account_id
                 WHERE c.store_id = :sid AND lt.type = 'REDEEM' AND lt.created_at >= :start_date) as redeemed
        """), {"sid": store_id, "start_date": start_date}).fetchone()
        
        enrolled = int(row.enrolled) if row else 0
        issued = float(row.issued) if row else 0
        redeemed = abs(float(row.redeemed)) if row else 0
        
        detail = tmpl["detail_template"].format(enrolled=enrolled, issued=format_unit(issued, 'point'), redeemed=format_unit(redeemed, 'point'))
        supporting_metrics = {"enrolled_customers": enrolled, "points_issued": issued, "points_redeemed": redeemed}
        
    elif intent == "credit_overdue":
        row = db.session.execute(text("""
            SELECT COUNT(*) as overdue_count, COALESCE(SUM(balance), 0) as total_overdue
            FROM credit_ledger
            WHERE store_id = :sid AND balance > 0 AND updated_at < CURRENT_DATE - 30
        """), {"sid": store_id}).fetchone()
        
        count = int(row.overdue_count) if row else 0
        total_overdue = float(row.total_overdue) if row else 0
        
        detail = tmpl["detail_template"].format(count=count, total_overdue=format_currency(total_overdue))
        supporting_metrics = {"overdue_customers": count, "total_overdue_amount": total_overdue}
            
    else:
        detail = tmpl["detail_template"].format(value="system baseline", stock="0", reorder="0", deficit="0", margin="0")

    return jsonify({
        "status": "success",
        "data": {
            "intent": intent,
            "headline": headline,
            "detail": detail,
            "action": action,
            "supporting_metrics": supporting_metrics
        }
    }), 200
