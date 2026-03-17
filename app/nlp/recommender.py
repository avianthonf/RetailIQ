"""RetailIQ NLP Recommender stub."""

import logging

logger = logging.getLogger(__name__)


def get_ai_recommendations(user_id, store_id: int) -> list:
    """Return AI-powered product recommendations. Stub."""
    logger.info("Recommendations requested for user %s store %s", user_id, store_id)
    return []
