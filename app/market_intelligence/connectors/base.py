"""
Base connector framework for market intelligence data acquisition.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import MarketSignal

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """
    Abstract base class for all market data connectors.
    """

    def __init__(self, source_id: int):
        self.source_id = source_id

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Fetch raw data from the external source."""
        pass

    @abstractmethod
    def normalize(self, raw_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Normalize raw data into standardized MarketSignal dictionaries.
        Required output format per record:
        {
            'signal_type': str,  # PRICE, DEMAND, SUPPLY, SENTIMENT, EVENT
            'category_id': int | None,
            'region_code': str | None,
            'value': float,
            'confidence': float,
            'timestamp': datetime,
            'raw_payload': dict
        }
        """
        pass

    def compute_quality_score(self, record: dict[str, Any]) -> float:
        """
        Compute a quality score (0.0 to 1.0) for a normalized record.
        Override to implement custom scoring logic based on source reliability,
        data completeness, etc.
        """
        # Default simple scoring
        score = 1.0

        # Penalty for missing category or region
        if not record.get("category_id"):
            score -= 0.2
        if not record.get("region_code"):
            score -= 0.1

        # Confidence is a multiplier if provided
        confidence = record.get("confidence", 1.0)
        score *= min(1.0, max(0.1, confidence))

        return max(0.0, score)

    def ingest(self, session) -> list[int]:
        """
        Fetch, normalize, score, and persist signals to the database.
        Returns a list of created MarketSignal IDs.
        """
        try:
            raw_data = self.fetch()
            if not raw_data:
                return []

            normalized_data = self.normalize(raw_data)

            created_ids = []
            for record in normalized_data:
                quality_score = self.compute_quality_score(record)

                signal = MarketSignal(
                    signal_type=record["signal_type"],
                    source_id=self.source_id,
                    category_id=record.get("category_id"),
                    region_code=record.get("region_code"),
                    value=record["value"],
                    confidence=record.get("confidence", 1.0),
                    quality_score=quality_score,
                    timestamp=record.get("timestamp", datetime.now(timezone.utc)),
                    raw_payload=record.get("raw_payload", {}),
                )
                session.add(signal)

            session.flush()  # To get IDs before commit

            # Note: caller is responsible for commit()
            return [s.id for s in session.new if isinstance(s, MarketSignal)]

        except Exception as e:
            logger.error(f"Ingestion failed for source {self.source_id}: {str(e)}")
            raise
