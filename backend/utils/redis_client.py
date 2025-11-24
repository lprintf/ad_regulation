"""
Redis client management.
Provides connection pooling and utility functions for Redis operations.
"""

import json
import logging
from datetime import date, datetime
from typing import Any


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles date and datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

import redis.asyncio as aioredis
from redis.asyncio import Redis, ConnectionPool

from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

logger = logging.getLogger(__name__)

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


async def init_redis() -> Redis:
    """
    Initialize Redis connection pool and client.

    Returns:
        Redis client instance
    """
    global _redis_pool, _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        _redis_pool = ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True,  # Auto decode bytes to str
            max_connections=50,
        )
        _redis_client = Redis(connection_pool=_redis_pool)

        # Test connection
        await _redis_client.ping()
        logger.info(f"Redis connected: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

        return _redis_client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def close_redis() -> None:
    """Close Redis connection and cleanup resources."""
    global _redis_pool, _redis_client

    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis client closed")
        _redis_client = None

    if _redis_pool:
        await _redis_pool.aclose()
        logger.info("Redis connection pool closed")
        _redis_pool = None


def get_redis() -> Redis:
    """
    Get the current Redis client instance.

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If Redis is not initialized
    """
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client


# ===== Insights Cache Utilities =====

INSIGHTS_CACHE_PREFIX = "insights:realtime"
INSIGHTS_CACHE_TTL_SECONDS = 60 * 60 * 24 * 4  # 4 days


def build_insights_cache_key(account_id: str, date_str: str) -> str:
    """
    Build Redis key for insights cache.

    Args:
        account_id: Ad account ID (with or without act_ prefix)
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Redis key string

    Example:
        >>> build_insights_cache_key("act_123", "2025-11-24")
        'insights:realtime:act_123:2025-11-24'
    """
    normalized_account = account_id if account_id.startswith("act_") else f"act_{account_id}"
    return f"{INSIGHTS_CACHE_PREFIX}:{normalized_account}:{date_str}"


async def cache_insights_for_date(
    account_id: str,
    date_str: str,
    insights_data: list[dict[str, Any]],
) -> int:
    """
    Cache insights data for a specific account and date in Redis.

    Args:
        account_id: Ad account ID
        date_str: Date string in YYYY-MM-DD format
        insights_data: List of insight records (ad-level)

    Returns:
        Number of ad records cached

    Example:
        >>> await cache_insights_for_date("act_123", "2025-11-24", [
        ...     {"ad_id": "123", "spend": 100.5, "impressions": 1000},
        ...     {"ad_id": "456", "spend": 50.2, "impressions": 500}
        ... ])
        2
    """
    if not insights_data:
        return 0

    redis_client = get_redis()
    cache_key = build_insights_cache_key(account_id, date_str)

    # Use pipeline for atomic operations
    async with redis_client.pipeline() as pipe:
        # Clear existing data for this date
        await pipe.delete(cache_key)

        # Store each ad's data as a hash field
        for insight in insights_data:
            ad_id = insight.get("ad_id")
            if not ad_id:
                continue

            # Transform to match _document_to_insight format:
            # - Add 'date' field from 'date_start'
            # - Wrap metrics into 'metrics' dict
            # - Keep IDs and account info at top level
            transformed = {}
            metrics = {}

            for key, value in insight.items():
                if key in ("account_id", "campaign_id", "adset_id", "ad_id", "date_start"):
                    transformed[key] = value
                else:
                    # All other fields are metrics
                    metrics[key] = value

            # Add 'date' field (convert date_start to string if needed)
            if "date_start" in transformed:
                date_value = transformed["date_start"]
                if isinstance(date_value, str):
                    transformed["date"] = date_value
                elif hasattr(date_value, 'strftime'):  # date or datetime
                    transformed["date"] = date_value.strftime("%Y-%m-%d")
                else:
                    transformed["date"] = str(date_value)

            # Add metrics dict
            transformed["metrics"] = metrics

            # Serialize transformed data to JSON
            field_value = json.dumps(transformed, cls=DateTimeEncoder, ensure_ascii=False)
            await pipe.hset(cache_key, str(ad_id), field_value)

        # Set expiration
        await pipe.expire(cache_key, INSIGHTS_CACHE_TTL_SECONDS)

        # Execute all commands
        await pipe.execute()

    logger.debug(f"Cached {len(insights_data)} insights for {account_id} on {date_str}")
    return len(insights_data)


async def get_insights_from_cache(
    account_id: str,
    date_str: str,
) -> list[dict[str, Any]]:
    """
    Retrieve cached insights data for a specific account and date.

    Args:
        account_id: Ad account ID
        date_str: Date string in YYYY-MM-DD format

    Returns:
        List of insight records (empty list if no cache exists)

    Example:
        >>> await get_insights_from_cache("act_123", "2025-11-24")
        [{"ad_id": "123", "spend": 100.5, ...}, {"ad_id": "456", "spend": 50.2, ...}]
    """
    redis_client = get_redis()
    cache_key = build_insights_cache_key(account_id, date_str)

    # Get all fields from hash
    cached_data = await redis_client.hgetall(cache_key)

    if not cached_data:
        return []

    # Deserialize JSON values
    insights = []
    for ad_id, json_str in cached_data.items():
        try:
            insight = json.loads(json_str)
            insights.append(insight)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode cached insight for ad {ad_id}: {e}")
            continue

    logger.debug(f"Retrieved {len(insights)} cached insights for {account_id} on {date_str}")
    return insights


async def clear_insights_cache(account_id: str, date_str: str | None = None) -> int:
    """
    Clear cached insights data for an account.

    Args:
        account_id: Ad account ID
        date_str: Optional date string. If None, clears all dates for the account.

    Returns:
        Number of keys deleted

    Example:
        >>> await clear_insights_cache("act_123", "2025-11-24")
        1
        >>> await clear_insights_cache("act_123")  # Clear all dates
        3
    """
    redis_client = get_redis()

    if date_str:
        # Clear specific date
        cache_key = build_insights_cache_key(account_id, date_str)
        deleted = await redis_client.delete(cache_key)
        logger.info(f"Cleared insights cache for {account_id} on {date_str}: {deleted} keys")
        return deleted
    else:
        # Clear all dates for this account using pattern scan
        normalized_account = account_id if account_id.startswith("act_") else f"act_{account_id}"
        pattern = f"{INSIGHTS_CACHE_PREFIX}:{normalized_account}:*"

        keys_to_delete = []
        async for key in redis_client.scan_iter(match=pattern, count=100):
            keys_to_delete.append(key)

        if keys_to_delete:
            deleted = await redis_client.delete(*keys_to_delete)
            logger.info(f"Cleared {deleted} insights cache keys for {account_id}")
            return deleted

        return 0
