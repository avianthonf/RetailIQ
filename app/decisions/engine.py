from typing import List, Dict, Any
from app.decisions.rules import RULES

def build_context(session, store_id: int) -> List[Dict[str, Any]]:
    # Fetch all data zero-filled for the last 30 days
    # To keep DB trips minimum, we construct the context per product locally
    from sqlalchemy import text
    from datetime import date
    from app.decisions.helpers import get_zero_filled_history
    
    today = date.today()
    contexts = []

    # 1. Product state
    products = session.execute(text("""
        SELECT product_id, current_stock, reorder_level, lead_time_days, cost_price, selling_price
        FROM products WHERE store_id = :sid AND is_active = TRUE
    """), {"sid": store_id}).fetchall()
    
    prod_map = {p.product_id: p for p in products}
    
    # 2. Daily SKU History
    sku_hist = session.execute(text("""
        SELECT product_id, date, units_sold
        FROM daily_sku_summary
        WHERE store_id = :sid AND date >= CURRENT_DATE - 30
    """), {"sid": store_id}).fetchall()
    
    hist_map = {}
    for r in sku_hist:
        hist_map.setdefault(r.product_id, []).append({"date": r.date, "units_sold": float(r.units_sold or 0.0)})
        
    # 3. Forecast Cache
    forecasts = session.execute(text("""
        SELECT product_id, SUM(forecast_value) as forecast_7d, MAX(regime) as regime
        FROM forecast_cache
        WHERE store_id = :sid AND forecast_date >= CURRENT_DATE AND forecast_date < CURRENT_DATE + 7
        GROUP BY product_id
    """), {"sid": store_id}).fetchall()
    
    fc_map = {f.product_id: {"forecast_7d": float(f.forecast_7d or 0.0), "regime": f.regime} for f in forecasts}
    fc_map[None] = {"forecast_7d": 0.0, "regime": "Stable"} # Fallback if no forecast available
    
    # 4. Top 20% Pareto Rank (deterministic)
    top_20_rows = session.execute(text("""
        SELECT product_id, SUM(revenue) as rev
        FROM daily_sku_summary
        WHERE store_id = :sid AND date >= CURRENT_DATE - 90
        GROUP BY product_id
        ORDER BY rev DESC, product_id ASC
    """), {"sid": store_id}).fetchall()
    
    n_top = max(1, round(len(top_20_rows) * 0.20))
    top_20_ids = {r.product_id for r in top_20_rows[:n_top]}
    
    # 5. Store level Revenue context
    store_hist = session.execute(text("""
        SELECT date, revenue FROM daily_store_summary
        WHERE store_id = :sid AND date >= CURRENT_DATE - 8 AND date < CURRENT_DATE
    """), {"sid": store_id}).fetchall()
    ma_7d = sum(float(r.revenue or 0.0) for r in store_hist) / 7.0 if len(store_hist) == 7 else 0.0
    store_today = session.execute(text("""
        SELECT revenue FROM daily_store_summary WHERE store_id = :sid AND date = CURRENT_DATE
    """), {"sid": store_id}).fetchone()
    today_rev = float(store_today.revenue or 0.0) if store_today else 0.0

    # Build individual context dicts
    for pid, p in prod_map.items():
        cost = float(p.cost_price or 0.0)
        sell = float(p.selling_price or 0.0)
        margin_pct = ((sell - cost) / sell * 100.0) if sell > 0 else 0.0
        
        ctx = {
            "product_id": pid,
            "current_stock": float(p.current_stock or 0.0),
            "reorder_level": float(p.reorder_level or 0.0),
            "lead_time_days": int(p.lead_time_days or 0),
            "margin_pct": margin_pct,
            "in_top_20_pct": pid in top_20_ids,
            "store_revenue_today": today_rev,
            "store_revenue_7d_ma": ma_7d,
            "units_sold_30d": get_zero_filled_history(hist_map.get(pid, []), today, 30, "units_sold"),
            "forecast_demand_7d": fc_map.get(pid, fc_map[None]).get("forecast_7d", 0.0),
            "regime": fc_map.get(pid, fc_map[None]).get("regime", "Stable")
        }
        contexts.append(ctx)
        
    return contexts

def _dedup_and_sort(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Deduplicate by (rule_name, product_id), keeping highest confidence
    seen = {}
    for act in actions:
        key = (act["rule_name"], act["product_id"])
        if key not in seen or act["confidence"] > seen[key]["confidence"]:
            seen[key] = act
            
    unique_actions = list(seen.values())
    
    # Sort by time_sensitive DESC, priority DESC, confidence DESC
    unique_actions.sort(
        key=lambda x: (x.get("time_sensitive", False), x.get("priority", 0), x.get("confidence", 0.0)),
        reverse=True
    )
    return unique_actions

def evaluate_rules(contexts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_actions = []
    for ctx in contexts:
        for rule_func in RULES:
            try:
                res = rule_func(ctx)
                if res is not None:
                    # Validate contract
                    required = {"rule_name", "action", "rationale", "confidence", "priority", "time_sensitive", "numerical_reasoning"}
                    if required.issubset(res.keys()):
                        all_actions.append(res)
            except Exception:
                # Rules must degrade gracefully and not throw exceptions to the main loop
                pass
                
    return _dedup_and_sort(all_actions)
