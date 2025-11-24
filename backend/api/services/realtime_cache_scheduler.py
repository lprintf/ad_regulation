"""
Realtime insights cache sync scheduler.
Syncs last 3 days of insights data to Redis every 30 minutes.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from api.services.insights_sync_service import _fetch_insights_sync
from utils.db import get_all_ad_account_documents
from utils.redis_client import cache_insights_for_date

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "insights::realtime_cache_sync"
SYNC_INTERVAL_MINUTES = 30
REALTIME_CACHE_DAYS = 3


async def _sync_realtime_insights():
    """
    Sync last 3 days of insights data to Redis for all accounts.
    Called every 30 minutes by the scheduler.
    """
    try:
        logger.info("Starting realtime insights cache sync")
        started_at = datetime.utcnow()

        # Get all ad accounts
        accounts = await get_all_ad_account_documents(fetch_links=True)
        if not accounts:
            logger.warning("No ad accounts found for realtime cache sync")
            return

        today = datetime.utcnow().date()
        # Sync last 3 days: today, today-1, today-2
        date_range = [today - timedelta(days=i) for i in range(REALTIME_CACHE_DAYS)]

        total_synced = 0
        total_failed = 0

        for account in accounts:
            account_id = account.id if account.id.startswith("act_") else f"act_{account.id}"

            for target_date in date_range:
                try:
                    # Fetch insights for this specific date
                    insights_data = await _fetch_insights_sync(
                        account_id=account_id,
                        since=target_date,
                        until=target_date,
                    )

                    # Cache in Redis
                    cached_count = await cache_insights_for_date(
                        account_id=account_id,
                        date_str=target_date.isoformat(),
                        insights_data=insights_data,
                    )

                    total_synced += cached_count
                    logger.debug(
                        f"Cached {cached_count} insights for {account_id} on {target_date.isoformat()}"
                    )

                except Exception as exc:
                    total_failed += 1
                    logger.exception(
                        f"Failed to sync realtime cache for {account_id} on {target_date.isoformat()}: {exc}"
                    )

        finished_at = datetime.utcnow()
        duration_seconds = (finished_at - started_at).total_seconds()

        logger.info(
            f"Realtime insights cache sync completed: "
            f"synced={total_synced}, failed={total_failed}, "
            f"accounts={len(accounts)}, duration={duration_seconds:.2f}s"
        )

    except Exception as exc:
        logger.exception(f"Realtime insights cache sync failed: {exc}")
        raise


async def start_realtime_cache_scheduler() -> AsyncIOScheduler:
    """
    Start the realtime insights cache sync scheduler.

    Returns:
        Scheduler instance
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 600})

    # Schedule every 30 minutes
    trigger = IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES)

    _scheduler.add_job(
        _sync_realtime_insights,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        next_run_time=datetime.now(),  # Run immediately on startup
    )

    _scheduler.start()
    logger.info(
        f"Realtime insights cache scheduler started (interval: {SYNC_INTERVAL_MINUTES} minutes)"
    )

    return _scheduler


async def stop_realtime_cache_scheduler() -> None:
    """Stop the realtime insights cache sync scheduler."""
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Realtime insights cache scheduler stopped")

    _scheduler = None


async def trigger_realtime_cache_sync_now() -> dict[str, Any]:
    """
    Manually trigger an immediate realtime cache sync.

    Returns:
        Status dictionary
    """
    if _scheduler is None:
        raise ValueError("Realtime cache scheduler is not running")

    job = _scheduler.get_job(JOB_ID)
    if job is None:
        raise ValueError("Realtime cache sync job not found")

    # Execute immediately
    await job.func()

    return {
        "status": "completed",
        "message": "Realtime cache sync executed successfully",
        "timestamp": datetime.utcnow().isoformat(),
    }
