import math
import numpy as np

def safety_stock_reorder(ctx: dict) -> dict | None:
    current_stock = float(ctx.get('current_stock') or 0.0)
    reorder_level = float(ctx.get('reorder_level') or 0.0)
    
    if current_stock <= reorder_level:
        return {
            "rule_name": "safety_stock_reorder",
            "product_id": ctx.get("product_id"),
            "action": "Immediate Reorder",
            "rationale": f"Stock ({current_stock:g}) has hit or breached minimum safety level ({reorder_level:g}).",
            "confidence": 0.95,
            "priority": 5,
            "time_sensitive": True,
            "numerical_reasoning": {
                "inputs": {"current_stock": current_stock, "reorder_level": reorder_level},
                "formula": "current_stock <= reorder_level",
                "result": 1
            }
        }
    return None

def reorder_alert(ctx: dict) -> dict | None:
    regime = ctx.get("regime")
    if regime == "Volatile":
        return None # Suppressed due to extreme unreliability

    history = ctx.get("units_sold_30d", [])
    if len(history) < 14:
        return None # Suppressed due to insufficient history for stddev
    
    # Sample standard deviation (ddof=1)
    sigma = float(np.std(history, ddof=1)) if len(history) > 1 else 0.0
    
    # Lead time constraint
    lt = int(ctx.get("lead_time_days") or 0)
    if lt <= 0:
        lt = 1 # Prevent 0 lead time collapsing safety stock artificially

    safety_stock = 1.65 * sigma * math.sqrt(lt)
    forecast_7d = float(ctx.get("forecast_demand_7d") or 0.0)
    current_stock = float(ctx.get("current_stock") or 0.0)
    
    q = (forecast_7d + safety_stock) - current_stock
    
    if q > 0:
        return {
            "rule_name": "reorder_alert",
            "product_id": ctx.get("product_id"),
            "action": "Forecast Reorder",
            "rationale": f"Demand + Safety bounds exceed current inventory.",
            "confidence": 0.85 if len(history) >= 21 else 0.5,
            "priority": 4,
            "time_sensitive": True,
            "numerical_reasoning": {
                "inputs": {
                    "sigma": round(sigma, 2), "lead_time_days": lt, 
                    "forecast_7d": round(forecast_7d, 2), "current_stock": round(current_stock, 2)
                },
                "formula": "Q = (forecast_demand_7d + 1.65 * sigma * sqrt(lead_time_days)) - current_stock",
                "result": round(q, 2)
            }
        }
    return None

def slow_mover(ctx: dict) -> dict | None:
    history = ctx.get("units_sold_30d", [])
    current_stock = float(ctx.get("current_stock") or 0.0)
    
    if len(history) == 30 and sum(history) == 0.0 and current_stock > 0:
        return {
            "rule_name": "slow_mover",
            "product_id": ctx.get("product_id"),
            "action": "Discount / Liquidate",
            "rationale": f"0 units sold in the last 30 calendar days with {current_stock:g} units idle.",
            "confidence": 0.90,
            "priority": 2,
            "time_sensitive": False,
            "numerical_reasoning": {
                "inputs": {"sum_30d": sum(history), "current_stock": current_stock},
                "formula": "sum_30d == 0 and current_stock > 0",
                "result": 1
            }
        }
    return None

def revenue_drop(ctx: dict) -> dict | None:
    today_rev = float(ctx.get("store_revenue_today") or 0.0)
    ma_7d = float(ctx.get("store_revenue_7d_ma") or 0.0)
    
    if ma_7d > 0 and today_rev < 0.7 * ma_7d:
        return {
            "rule_name": "revenue_drop",
            "product_id": None, # Store level rule
            "action": "Contribution Analysis Required",
            "rationale": f"Today's revenue is anomalously low (<70% of 7-day trailing average).",
            "confidence": 0.80,
            "priority": 3,
            "time_sensitive": True,
            "numerical_reasoning": {
                "inputs": {"today_rev": today_rev, "ma_7d": ma_7d},
                "formula": "today_rev < 0.7 * ma_7d",
                "result": round(today_rev / ma_7d, 2)
            }
        }
    return None

def high_margin_opportunity(ctx: dict) -> dict | None:
    margin = float(ctx.get("margin_pct") or 0.0)
    in_top = bool(ctx.get("in_top_20_pct") or False)
    
    if margin > 30.0 and in_top:
        return {
            "rule_name": "high_margin_opportunity",
            "product_id": ctx.get("product_id"),
            "action": "Promote / Display",
            "rationale": f"High margin product (>30%) performing in top 20% tier.",
            "confidence": 0.75,
            "priority": 1,
            "time_sensitive": False,
            "numerical_reasoning": {
                "inputs": {"margin_pct": margin, "in_top_20": in_top},
                "formula": "margin_pct > 30 and in_top == True",
                "result": 1
            }
        }
    return None

# The registry matching the specification
RULES = [
    reorder_alert,
    safety_stock_reorder,
    slow_mover,
    revenue_drop,
    high_margin_opportunity
]
