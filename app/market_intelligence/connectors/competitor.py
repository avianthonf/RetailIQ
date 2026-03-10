"""
Simulated Competitor Pricing Connector
"""

import random
from datetime import datetime, timezone
from typing import Any, Dict, List

from .base import BaseConnector


class CompetitorPricingConnector(BaseConnector):
    """
    Simulates scraping or API ingestion of competitor prices for key SKUs.
    """

    # Mock target SKUs to track
    TRACKED_SKUS = [
        {"sku": "SKU-001", "category_id": 1, "base_price": 10.99},
        {"sku": "SKU-002", "category_id": 1, "base_price": 5.49},
        {"sku": "SKU-003", "category_id": 2, "base_price": 24.99},
    ]

    def fetch(self) -> list[dict[str, Any]]:
        """Simulate fetching from a scraper or pricing API."""
        now = datetime.now(timezone.utc)
        competitors = ["MegaMart", "ValueStore", "OnlineGiant"]

        raw_data = []

        # Simulate price changes for some SKUs
        for tracked in self.TRACKED_SKUS:
            # 30% chance a competitor changed price today
            if random.random() < 0.3:
                competitor = random.choice(competitors)
                # Price change between -15% and +10%
                change_pct = random.uniform(-0.15, 0.10)
                new_price = round(tracked["base_price"] * (1 + change_pct), 2)

                raw_data.append(
                    {
                        "sku": tracked["sku"],
                        "category_id": tracked["category_id"],
                        "competitor": competitor,
                        "price": new_price,
                        "currency": "USD",
                        "timestamp": now.isoformat(),
                        "provider": "MockCompetitorScraper",
                    }
                )

        return raw_data

    def normalize(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for raw in raw_data:
            normalized.append(
                {
                    "signal_type": "PRICE",
                    "category_id": raw["category_id"],
                    "region_code": "LOCAL",  # Competitor pricing is often local/regional
                    "value": raw["price"],
                    "confidence": 0.80,  # Scraper data can occasionally be wrong
                    "timestamp": datetime.fromisoformat(raw["timestamp"]),
                    "raw_payload": raw,
                }
            )

        return normalized

    def compute_quality_score(self, record: dict[str, Any]) -> float:
        # Scraper data quality
        return 0.85
