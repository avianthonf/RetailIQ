"""RetailIQ Marketplace Logistics — tracking stub."""

import logging

logger = logging.getLogger(__name__)


def get_tracking_events(tracking_number: str) -> list[dict]:
    """Fetch shipment tracking events. Stub returns empty list."""
    logger.info("Tracking lookup for %s (stub)", tracking_number)
    return []
