"""
Async job service for Facebook Ads Insights.

Handles Facebook async job operations:
- Create async insights job
- Check job status
- Get completed job results
"""

from typing import Any


class AsyncJobService:
    """Service for managing Facebook async insights jobs."""

    @staticmethod
    async def create_async_job(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an async insights job in Facebook API.

        TODO: Extract from insights_service.py:create_async_job()
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    async def check_job_status(
        ad_account_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """
        Check the status of an async insights job.

        TODO: Extract from insights_service.py:check_job_status()
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    async def get_job_result(
        ad_account_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """
        Get the result of a completed async insights job.

        TODO: Extract from insights_service.py:get_job_result()
        """
        raise NotImplementedError("To be migrated from insights_service.py")
