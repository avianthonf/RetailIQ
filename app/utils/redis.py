import logging
import os

import redis

logger = logging.getLogger(__name__)


def get_redis_client():
    """
    Get a Redis client based on environment configuration.
    Falls back to a fake Redis client if fakeredis is available (for tests).
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Check if we are in testing mode
    if os.environ.get("FLASK_ENV") == "testing" or os.environ.get("TESTING") == "true":
        try:
            from fakeredis import FakeStrictRedis

            return FakeStrictRedis()
        except ImportError:
            logger.warning("fakeredis not installed, using real redis even in tests")

    try:
        return redis.from_url(redis_url, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {redis_url}: {e}")
        # Return a fake client if real one fails to avoid crashing
        try:
            from fakeredis import FakeStrictRedis

            return FakeStrictRedis()
        except ImportError:
            return None
