from __future__ import annotations

import logging

from .config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False

try:
    import redis
    _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    # Test connection
    _redis_client.ping()
    _redis_available = True
    logger.info("Redis connection established")
except Exception as e:
    logger.warning(f"Redis not available: {e}. Rate limiting and refresh token rotation will be disabled.")
    _redis_available = False


def get_redis_client():
    """Get Redis client if available, otherwise return None."""
    if not _redis_available:
        return None
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available."""
    return _redis_available


