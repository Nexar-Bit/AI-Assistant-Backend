from __future__ import annotations

import logging
import os

from .config import settings

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False
_redis_initialized = False


def _initialize_redis():
    """Initialize Redis connection if configured."""
    global _redis_client, _redis_available, _redis_initialized
    
    if _redis_initialized:
        return
    
    _redis_initialized = True
    
    # Check if Redis is explicitly disabled or not configured
    redis_url = os.getenv("REDIS_URL") or settings.REDIS_URL
    
    # Skip Redis if URL is empty, None, or explicitly disabled
    if not redis_url or redis_url.lower() in ("none", "disabled", ""):
        logger.info("Redis is not configured. Rate limiting and refresh token rotation will be disabled.")
        _redis_available = False
        return
    
    # In production (Render), if Redis URL is the default Docker Compose value and not explicitly set,
    # assume Redis is not available
    if redis_url == "redis://redis:6379/0" and os.getenv("ENVIRONMENT", "development").lower() in ("production", "staging"):
        if not os.getenv("REDIS_URL"):  # Only if not explicitly set
            logger.info("Redis not configured (default Docker URL detected in production). Rate limiting and refresh token rotation will be disabled.")
            _redis_available = False
            return
    
    try:
        import redis
        _redis_client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,  # Fast timeout
            socket_timeout=2,
            retry_on_timeout=False,
        )
        # Test connection with short timeout
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connection established successfully")
    except ImportError:
        logger.info("Redis package not available. Rate limiting and refresh token rotation will be disabled.")
        _redis_available = False
    except Exception as e:
        # Only log as info if it's a connection error (expected in many deployments)
        if "Name or service not known" in str(e) or "Connection refused" in str(e):
            logger.info(f"Redis not available: {e}. Rate limiting and refresh token rotation will be disabled.")
        else:
            logger.warning(f"Redis connection error: {e}. Rate limiting and refresh token rotation will be disabled.")
        _redis_available = False
        _redis_client = None


# Initialize on module import
_initialize_redis()


def get_redis_client():
    """Get Redis client if available, otherwise return None."""
    if not _redis_available:
        return None
    return _redis_client


def is_redis_available() -> bool:
    """Check if Redis is available."""
    return _redis_available


