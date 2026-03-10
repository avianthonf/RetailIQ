import re
from typing import Any, Dict

# Ordered by precedence
# forecast > inventory > revenue > profit > default
INTENT_PATTERNS = [
    ("forecast", r"(?i)(forecast|predict|future|demand|expected|project)"),
    ("inventory", r"(?i)(stock|inventory|reorder|empty|replenish|available)"),
    ("revenue", r"(?i)(revenue|sales|income|money)"),
    ("profit", r"(?i)(profit|margin|cost)"),
    ("top_products", r"(?i)(top|best|pareto|80/20)"),
    ("loyalty_summary", r"(?i)(loyalty|points|redeem|rewards|earn)"),
    ("credit_overdue", r"(?i)(credit|overdue|repayment|debt|ledger)"),
    ("market_intelligence", r"(?i)(market|competitor|commodity|weather|anomaly|sentiment)"),
]


def resolve_intent(query: str) -> str:
    """Return the highest precedence intent that matches the query."""
    if not query or len(query) > 200:
        return "default"

    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, query):
            return intent

    return "default"
