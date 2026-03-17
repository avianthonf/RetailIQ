"""RetailIQ NLP Assistant stub."""

import logging

logger = logging.getLogger(__name__)


def handle_assistant_query(query_text: str, store_id: int) -> str:
    """Handle natural language query about store data. Stub."""
    logger.info("NLP query from store %s: %s", store_id, query_text)
    return (
        "NLP assistant not yet integrated. "
        "Connect an LLM (e.g. OpenAI, Anthropic Claude) to this module to answer queries like: "
        f'"{query_text}"'
    )
