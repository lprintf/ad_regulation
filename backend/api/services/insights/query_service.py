"""
Main query service for insights (Facade pattern).

This is the primary interface for insights queries, orchestrating
other services to provide high-level query operations.

During migration, this facade delegates to the original insights_service.py
to maintain backward compatibility. Methods will be migrated incrementally.
"""

from typing import Any

# TODO: Gradually replace these imports with new sub-services
from api.services.insights_service import InsightsService as _LegacyInsightsService


class QueryService:
    """
    Main facade for insights queries.

    This service orchestrates data fetching, transformation, aggregation,
    and provides high-level query methods for routers.

    Methods are currently delegated to legacy service during migration.
    """

    @staticmethod
    async def query_insights_realtime(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query insights by combining cached (DB) and realtime Facebook API data.

        TODO: Migrate to use new sub-services
        """
        return await _LegacyInsightsService.query_insights_realtime(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            fields=fields,
            object_level=object_level,
            object_ids=object_ids,
        )

    @staticmethod
    async def query_insights_from_last_gap(
        ad_account_id: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        cache_window_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch insights by automatically setting realtime window to
        (last_synced_until + 1 day) → requested until.

        TODO: Migrate to use new sub-services
        """
        return await _LegacyInsightsService.query_insights_from_last_gap(
            ad_account_id=ad_account_id,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            fields=fields,
            object_level=object_level,
            object_ids=object_ids,
            cache_window_hint=cache_window_hint,
        )

    @staticmethod
    async def query_insights_hybrid(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        cache_window_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Combine database data with realtime gap fill in a single response.

        TODO: Migrate to use new sub-services
        """
        return await _LegacyInsightsService.query_insights_hybrid(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            fields=fields,
            object_level=object_level,
            object_ids=object_ids,
            cache_window_hint=cache_window_hint,
        )

    @staticmethod
    async def query_insights_mongo_only(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        mask_ad_ids: bool = False,
    ) -> dict[str, Any]:
        """
        Query insights data from MongoDB database only (no Facebook API calls).

        TODO: Migrate to use new sub-services
        """
        return await _LegacyInsightsService.query_insights_mongo_only(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=mask_ad_ids,
        )

    @staticmethod
    async def query_insights_mongo_redis(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        mask_ad_ids: bool = False,
    ) -> dict[str, Any]:
        """
        Query insights from MongoDB (historical) + Redis (recent 3 days) hybrid cache.

        TODO: Migrate to use new sub-services
        """
        return await _LegacyInsightsService.query_insights_mongo_redis(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=mask_ad_ids,
        )

    # Async job methods - delegate to AsyncJobService (or legacy for now)
    @staticmethod
    async def create_async_job(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
    ) -> dict[str, Any]:
        """Create async insights job. TODO: Migrate to AsyncJobService."""
        return await _LegacyInsightsService.create_async_job(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
        )

    @staticmethod
    async def check_job_status(ad_account_id: str, job_id: str) -> dict[str, Any]:
        """Check async job status. TODO: Migrate to AsyncJobService."""
        return await _LegacyInsightsService.check_job_status(
            ad_account_id=ad_account_id,
            job_id=job_id,
        )

    @staticmethod
    async def get_job_result(ad_account_id: str, job_id: str) -> dict[str, Any]:
        """Get async job result. TODO: Migrate to AsyncJobService."""
        return await _LegacyInsightsService.get_job_result(
            ad_account_id=ad_account_id,
            job_id=job_id,
        )
