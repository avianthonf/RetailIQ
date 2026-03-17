"""RetailIQ Vision — Shelf Scan stub."""

import logging

logger = logging.getLogger(__name__)


def process_shelf_scan(image_url: str) -> dict:
    """Analyse shelf image and detect products / gaps. Stub implementation."""
    logger.info("Shelf scan requested for: %s", image_url)
    return {
        "status": "stub",
        "message": "Vision model not yet integrated. Connect a vision API in this module.",
        "image_url": image_url,
        "detected_products": [],
        "out_of_stock_slots": [],
        "facing_counts": {},
    }
