"""
Simulated Weather & Event Data Connector
"""

import random
from datetime import datetime, timezone
from typing import Any, Dict, List

from .base import BaseConnector


class WeatherConnector(BaseConnector):
    """
    Simulates fetching weather data and converting extreme weather events
    into demand/supply signals for retail categories.
    """

    # Map weather conditions to affected retail categories and impact direction
    WEATHER_IMPACTS = {
        "HEAT_WAVE": {
            "categories": [3, 4],  # E.g., beverages, summer clothing
            "signal_type": "DEMAND",
            "effect": "SURGE",
        },
        "SNOWSTORM": {
            "categories": [1, 5],  # E.g., staples/grocery, winter gear
            "signal_type": "DEMAND",
            "effect": "SURGE",
        },
        "FLOODING": {
            "categories": [6],  # E.g., hardware/repair
            "signal_type": "SUPPLY",
            "effect": "DISRUPTION",  # affects supply chains
        },
    }

    def fetch(self) -> list[dict[str, Any]]:
        """Simulate fetching from a weather API (e.g., NOAA, OpenWeather)."""
        now = datetime.now(timezone.utc)

        # 10% chance of a significant weather event
        if random.random() > 0.1:
            return []

        event_type = random.choice(list(self.WEATHER_IMPACTS.keys()))
        region = random.choice(["US-EAST", "US-WEST", "EU-CENTRAL", "ASIA-SOUTH"])
        severity = random.choice(["MODERATE", "SEVERE", "EXTREME"])

        return [
            {
                "event": event_type,
                "region": region,
                "severity": severity,
                "timestamp": now.isoformat(),
                "provider": "MockWeatherAPI",
            }
        ]

    def normalize(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for raw in raw_data:
            event = raw["event"]
            impact = self.WEATHER_IMPACTS.get(event)

            if not impact:
                continue

            severity_multiplier = {"MODERATE": 1.2, "SEVERE": 1.5, "EXTREME": 2.0}.get(raw["severity"], 1.0)

            # Generate a signal for each affected category
            for cat_id in impact["categories"]:
                # For anomaly detection, we use 'value' to represent the magnitude
                # of the demand/supply shock (baseline 1.0)
                value = severity_multiplier if impact["effect"] == "SURGE" else (1.0 / severity_multiplier)

                normalized.append(
                    {
                        "signal_type": impact["signal_type"],  # DEMAND or SUPPLY
                        "category_id": cat_id,
                        "region_code": raw["region"],
                        "value": value,
                        "confidence": 0.85,  # Weather forecasts have some uncertainty
                        "timestamp": datetime.fromisoformat(raw["timestamp"]),
                        "raw_payload": raw,
                    }
                )

        return normalized

    def compute_quality_score(self, record: dict[str, Any]) -> float:
        # Weather data quality depends on the source, assume good for now
        return 0.90
