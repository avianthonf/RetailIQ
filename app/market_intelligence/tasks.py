"""
Celery tasks for real-time market intelligence gathering and processing.
"""

import logging
from datetime import datetime, timezone

from app import celery_app as celery
from app import db
from app.models import DataSource, IntelligenceReport, Store

from .connectors.commodity import CommodityIndexConnector
from .connectors.competitor import CompetitorPricingConnector
from .connectors.weather import WeatherConnector
from .engine import IntelligenceEngine
from .websocket import broadcast_alert_fired, broadcast_signal_update

logger = logging.getLogger(__name__)


@celery.task
def ingest_market_data():
    """Run all active connectors to ingest new market signals."""
    logger.info("Starting scheduled market data ingestion")

    # In a real system, we'd query DataSource from DB.
    # For now, we instantiate our mock connectors.
    connectors = [
        CommodityIndexConnector(source_id=1),
        WeatherConnector(source_id=2),
        CompetitorPricingConnector(source_id=3),
    ]

    total_signals = 0
    for connector in connectors:
        try:
            signal_ids = connector.ingest(db.session)
            total_signals += len(signal_ids)

            # Broadcast updates via WebSocket
            if signal_ids:
                from app.models import MarketSignal

                signals = db.session.query(MarketSignal).filter(MarketSignal.id.in_(signal_ids)).all()
                for signal in signals:
                    broadcast_signal_update(
                        {
                            "id": signal.id,
                            "signal_type": signal.signal_type,
                            "category_id": signal.category_id,
                            "value": float(signal.value),
                            "timestamp": signal.timestamp.isoformat(),
                        }
                    )

        except Exception as e:
            logger.error(f"Error running connector {connector.__class__.__name__}: {e}")

    db.session.commit()
    logger.info(f"Ingestion complete. Added {total_signals} new signals.")

    # Chain the next task
    if total_signals > 0:
        compute_price_indices.delay()


@celery.task
def compute_price_indices():
    """Recompute indices for all categories."""
    logger.info("Computing price indices...")
    # Typically would iterate over all active category IDs.
    # For now we use our simulated categories (1 and 2).

    for cat_id in [1, 2]:
        try:
            IntelligenceEngine.compute_price_index(cat_id)
        except Exception as e:
            logger.error(f"Error computing index for category {cat_id}: {e}")

    # After computing indices, run anomaly detection
    generate_alerts.delay()


@celery.task
def generate_alerts():
    """Detect anomalies and generate alerts for merchants."""
    logger.info("Running market anomaly detection...")

    # Ideally, we iterate over active merchants. Let's just run for merchant 1 to simulate.
    try:
        alerts_created = IntelligenceEngine.generate_alerts(merchant_id=1)

        if alerts_created > 0:
            logger.info(f"Generated {alerts_created} new market alerts.")
            # We would normally query the new alerts and broadcast them via WS.

    except Exception as e:
        logger.error(f"Error generating market alerts: {e}")


@celery.task
def generate_intelligence_report(report_id: str):
    """
    Async generate a deep-dive intelligence report.
    """
    logger.info(f"Generating market intelligence report {report_id}...")
    try:
        report = db.session.get(IntelligenceReport, report_id)
        if not report:
            return

        report.status = "PROCESSING"
        db.session.commit()

        # Simulate heavy processing (aggregating data, running ML models, PDF gen)
        # In reality, this would query engine.py and construct a document
        import time

        time.sleep(2)  # Simulate work

        report.status = "COMPLETED"
        report.report_url = f"https://storage.retailiq.com/reports/{report_id}.pdf"
        report.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info(f"Report {report_id} completed successfully.")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Report {report_id} failed: {e}")
        report = db.session.get(IntelligenceReport, report_id)
        if report:
            report.status = "FAILED"
            db.session.commit()
