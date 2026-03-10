"""
Simulated Commodity Price Index Connector
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from .base import BaseConnector


class CommodityIndexConnector(BaseConnector):
    """
    Simulates fetching commodity price indices (e.g. wheat, dairy, oil)
    that affect retail goods.
    """

    # Mapping of commodity types to categories (simulated IDs)
    COMMODITY_CATEGORIES = {
        "WHEAT_INDEX": 1,  # Assume 1 is staples/grocery
        "DAIRY_INDEX": 2,  # Assume 2 is dairy
        "FUEL_INDEX": None,  # Affects transport, no specific category
    }

    def fetch(self) -> list[dict[str, Any]]:
        """Simulate fetching from a commodity API."""
        now = datetime.now(timezone.utc)

        # Simulate realistic daily fluctuations with some mean reversion
        # Base values roughly 100
        raw_data = []
        for commodity in self.COMMODITY_CATEGORIES.keys():
            base = 100.0
            noise = random.gauss(0, 1.5)  # daily volatility
            trend = random.gauss(0.1, 0.5)  # slight upward drift

            current_value = base + trend + noise

            raw_data.append(
                {
                    "symbol": commodity,
                    "price": current_value,
                    "currency": "USD",
                    "timestamp": now.isoformat(),
                    "provider": "MockCommodityAPI",
                }
            )

        return raw_data

    def normalize(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for raw in raw_data:
            symbol = raw["symbol"]

            normalized.append(
                {
                    "signal_type": "PRICE",  # It's a price index signal
                    "category_id": self.COMMODITY_CATEGORIES.get(symbol),
                    "region_code": "GLOBAL",  # Commodities are global
                    "value": raw["price"],
                    "confidence": 0.95,  # High confidence for index data
                    "timestamp": datetime.fromisoformat(raw["timestamp"]),
                    "raw_payload": raw,
                }
            )

        return normalized

    def compute_quality_score(self, record: dict[str, Any]) -> float:
        # High quality for established index data
        return 0.98
