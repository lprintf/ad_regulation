"""
Data source service for insights.

Handles fetching insights data from different sources:
- MongoDB (historical data)
- Redis (recent cache)
- Facebook Ads API (realtime)
"""

from datetime import date
from typing import Any


class DataSourceService:
    """Service for fetching insights data from various sources."""

    @staticmethod
    async def fetch_from_mongodb(
        account_id: str,
        since: date,
        until: date,
        object_filter: tuple[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch insights from MongoDB.

        TODO: Extract from insights_service.py MongoDB query logic
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    async def fetch_from_redis(
        account_id: str,
        since: date,
        until: date,
    ) -> list[dict[str, Any]]:
        """
        Fetch insights from Redis cache.

        TODO: Extract from insights_service.py:_get_insights_from_redis_range()
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    async def fetch_from_facebook_api(
        account_id: str,
        since: str,
        until: str,
        level: str,
        time_increment: int | None,
        breakdowns: str | None,
        fields: list[str],
    ) -> list[dict[str, Any]]:
        """
        Fetch insights from Facebook Ads API (realtime).

        TODO: Extract from insights_service.py Facebook API calls
        """
        raise NotImplementedError("To be migrated from insights_service.py")
