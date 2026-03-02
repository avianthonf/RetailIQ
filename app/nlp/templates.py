# Deterministic NLP formatting templates
# No generative text is allowed to maintain 100% deterministic output.
import math

TEMPLATES = {
    "forecast": {
        "headline": "Demand Context",
        "detail_template": "Projected demand of {forecast} units over the next 7 days (Regime: {regime}).",
        "action": "Consider setting safety stock based on {lead_time} days lead time."
    },
    "inventory": {
        "headline": "Stock Alert",
        "detail_template": "Current stock is {stock} units. Reorder level at {reorder}. Deficit: {deficit} units.",
        "action": "Restock immediately."
    },
    "revenue": {
        "headline": "Revenue Update",
        "detail_template": "Today's store-wide revenue is {revenue}. The 7-day average is {ma_7d}.",
        "action_template": "Variance from average: {delta_pct}%."
    },
    "profit": {
        "headline": "Profitability Alert",
        "detail_template": "SKU margin is running at {margin}%.",
        "action": "Assess pricing structure against cost basis."
    },
    "top_products": {
        "headline": "Top Performers",
        "detail_template": "Leading SKUs by revenue (last 30 days): {value}.",
        "action": "Consider increasing stock levels for top revenue contributors."
    },
    "loyalty_summary": {
        "headline": "Loyalty Program Summary",
        "detail_template": "You have {enrolled} enrolled customers. {issued} points issued and {redeemed} points redeemed this month.",
        "action": "Promote loyalty program at checkout."
    },
    "credit_overdue": {
        "headline": "Overdue Credit",
        "detail_template": "There are {count} customers with overdue credit exceeding 30 days. Total outstanding: {total_overdue}.",
        "action": "Send reminders to overdue customers."
    },
    "default": {
        "headline": "Retail Intelligence",
        "detail_template": "Analyzing historical data bounds. Current observed value: {value}.",
        "action": "No specific anomalies detected."
    },
    "supplier_reliability": {
        "headline": "Supplier Reliability",
        "detail_template": "Your most reliable supplier is {name} with a {fill_rate}% fill rate and {lead_time} day average lead time.",
        "action": "Maintain relationship."
    },
    "overdue_po": {
        "headline": "Overdue Orders",
        "detail_template": "You have {n} overdue purchase orders. Oldest is {days} days late from {supplier_name}.",
        "action": "Follow up with suppliers."
    }
}

def format_percentage(val: float) -> str:
    """Format % to 1 decimal. Suppress <2%."""
    rounded = round(val, 1)
    if abs(rounded) < 2.0 and rounded != 0.0:
        return "Stable (<2% change)"
    return f"{rounded}%"

def format_currency(val: float) -> str:
    """Format INR currency with thousands separator."""
    s = f"{val:,.2f}"
    parts = s.split('.')
    integer_part = parts[0]
    decimal_part = parts[1]

    integer_part = integer_part.replace(',', '')
    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        formatted = ""
        while len(remaining) > 2:
            formatted = "," + remaining[-2:] + formatted
            remaining = remaining[:-2]
        if remaining:
            formatted = remaining + formatted
        integer_part = formatted + "," + last_three
    return f"₹{integer_part}.{decimal_part}"

def format_unit(val: float, item_name: str = "unit") -> str:
    val_int = math.ceil(abs(val))
    if val_int == 1:
        return f"{val_int} {item_name}"
    return f"{val_int} {item_name}s"
