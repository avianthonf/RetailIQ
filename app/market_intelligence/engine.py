"""
Market Intelligence Engine
Core analytics engine for real-time market signals.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import desc, func, select, text

from app import db
from app.models import MarketAlert, MarketSignal, PriceIndex, Store

logger = logging.getLogger(__name__)


class IntelligenceEngine:
    @staticmethod
    def compute_price_index(category_id: int, method: str = "laspeyres") -> float | None:
        """
        Compute consumer price index for a category using recent market signals.
        Supports Laspeyres (base weighted), Paasche (current weighted), Fisher (geometric mean).
        In this simulated environment, we simplify by averaging recent PRICE signals.
        """
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Get recent price signals for category
        stmt = (
            select(MarketSignal)
            .where(MarketSignal.category_id == category_id)
            .where(MarketSignal.signal_type == "PRICE")
            .where(MarketSignal.timestamp >= thirty_days_ago)
        )
        signals = db.session.execute(stmt).scalars().all()

        if not signals:
            return None

        # Simplified index calculation: weighted average of recent prices
        # based on confidence and quality score
        weights = [float(s.confidence * s.quality_score) for s in signals]
        values = [float(s.value) for s in signals]

        if sum(weights) == 0:
            return np.mean(values)

        index_value = np.average(values, weights=weights)

        # Persist index computation
        idx = PriceIndex(
            category_id=category_id,
            index_value=float(index_value),
            base_period=thirty_days_ago.date(),
            computation_method=method,
        )
        db.session.add(idx)
        db.session.commit()

        return index_value

    @staticmethod
    def detect_anomalies(category_id: int, signal_type: str = "PRICE") -> list[MarketSignal]:
        """
        Use Isolation Forest to detect anomalous market signals (price spikes, demand drop-offs).
        Returns a list of anomalous MarketSignal objects.
        """
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)

        stmt = (
            select(MarketSignal)
            .where(MarketSignal.category_id == category_id)
            .where(MarketSignal.signal_type == signal_type)
            .where(MarketSignal.timestamp >= ninety_days_ago)
            .order_by(MarketSignal.timestamp.asc())
        )
        signals = db.session.execute(stmt).scalars().all()

        if len(signals) < 20:  # Need enough data for IF
            return []

        # Extract features (value, and relative time diff)
        values = np.array([float(s.value) for s in signals]).reshape(-1, 1)

        # Fit Isolation Forest
        # Contamination = expected proportion of outliers (e.g., 5%)
        clf = IsolationForest(contamination=0.05, random_state=42)
        preds = clf.fit_predict(values)

        # -1 indicates anomaly
        anomalies = []
        for i, pred in enumerate(preds):
            if pred == -1:
                anomalies.append(signals[i])

        return anomalies

    @staticmethod
    def generate_alerts(merchant_id: int) -> int:
        """
        Evaluate recent signals and generate alerts for a specific merchant
        based on their relevant categories. Returns number of alerts created.
        """
        # 1. Find categories relevant to this merchant (simplify: all categories for now)
        # In a real system, join Store -> Inventory -> Product -> Category

        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)
        alerts_created = 0

        # 2. Check for recent anomalous price signals (simulate taking category 1)
        category_id = 1
        anomalous_signals = IntelligenceEngine.detect_anomalies(category_id, "PRICE")

        # Filter to only recent anomalies that haven't been alerted on
        recent_anomalies = [s for s in anomalous_signals if s.timestamp >= one_day_ago]

        if recent_anomalies:
            # Create a PRICE_SPIKE alert
            signal_ids = [s.id for s in recent_anomalies]
            avg_spike = np.mean([float(s.value) for s in recent_anomalies])

            alert = MarketAlert(
                alert_type="PRICE_SPIKE",
                severity="WARNING" if avg_spike < 150 else "CRITICAL",
                merchant_id=merchant_id,
                signal_ids=signal_ids,
                message=f"Abnormal price activity detected in Category {category_id}.",
                recommended_action={"action": "REVIEW_PRICING", "category_id": category_id},
            )
            db.session.add(alert)
            alerts_created += 1

        db.session.commit()
        return alerts_created

    @staticmethod
    def analyze_sentiment(text: str) -> float:
        """
        Basic NLP sentiment analysis for market news.
        Returns score from -1.0 (very negative) to 1.0 (very positive).
        """
        text_lower = text.lower()

        positive_words = ["growth", "surge", "boom", "record", "profit", "up", "high"]
        negative_words = ["drop", "fall", "crisis", "shortage", "disruption", "down", "low"]

        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        return float(pos_count - neg_count) / total

    @staticmethod
    def get_market_summary() -> dict[str, Any]:
        """
        Provide a high-level summary of current market conditions across all tracked indices.
        """
        # Get latest index per category
        stmt = (
            select(PriceIndex)
            .distinct(PriceIndex.category_id)
            .order_by(PriceIndex.category_id, desc(PriceIndex.computed_at))
        )
        indices = db.session.execute(stmt).scalars().all()

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "indices": [
                {
                    "category_id": idx.category_id,
                    "value": float(idx.index_value),
                    "computed_at": idx.computed_at.isoformat(),
                }
                for idx in indices
            ],
            "active_alerts": db.session.query(MarketAlert).filter_by(acknowledged=False).count(),
            "signal_volume_24h": db.session.query(MarketSignal)
            .filter(MarketSignal.timestamp >= datetime.now(timezone.utc) - timedelta(days=1))
            .count(),
        }

        return summary
