"""
Realtime insights cache sync scheduler.
Syncs from last synced date to today into Redis every N minutes (configurable: 10/20/30).
Executes at exact intervals (mm%N==0) for predictable scheduling.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.insights_sync_service import _fetch_insights_sync
from config import REALTIME_CACHE_SYNC_INTERVAL_MINUTES
from utils.db import get_all_ad_account_documents, InsightsSyncStateDocument
from utils.redis_client import cache_insights_for_date

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "insights::realtime_cache_sync"
SYNC_INTERVAL_MINUTES = REALTIME_CACHE_SYNC_INTERVAL_MINUTES


async def _sync_realtime_insights():
    """
    Sync from last synced date to today into Redis for all accounts.
    Called at regular intervals (every 10/20/30 minutes) by the scheduler.
    """
    try:
        logger.info("Starting realtime insights cache sync (from_last strategy)")
        started_at = datetime.utcnow()

        # Get all ad accounts
        accounts = await get_all_ad_account_documents(fetch_links=True)
        if not accounts:
            logger.warning("No ad accounts found for realtime cache sync")
            return

        today = datetime.utcnow().date()

        total_synced = 0
        total_failed = 0
        total_date_ranges = 0

        for account in accounts:
            account_id = account.id if account.id.startswith("act_") else f"act_{account.id}"

            try:
                # Query the last synced date from MongoDB
                sync_state = await InsightsSyncStateDocument.find_one(
                    InsightsSyncStateDocument.account_id == account.id
                )

                # Determine the starting date for cache sync
                if sync_state and sync_state.last_synced_date:
                    # Start from the day after last synced date
                    cache_start_date = sync_state.last_synced_date.date() + timedelta(days=1)
                else:
                    # No sync state, default to last 3 days
                    cache_start_date = today - timedelta(days=3)

                # Ensure we don't go too far back (max 7 days for safety)
                earliest_allowed = today - timedelta(days=7)
                if cache_start_date < earliest_allowed:
                    cache_start_date = earliest_allowed

                # If cache_start_date is in the future, skip
                if cache_start_date > today:
                    logger.debug(f"Account {account_id} is up to date, skipping cache sync")
                    continue

                logger.info(
                    f"Syncing cache for {account_id} from {cache_start_date.isoformat()} to {today.isoformat()}"
                )

                # Sync each date in the range
                current_date = cache_start_date
                while current_date <= today:
                    try:
                        # Fetch insights for this specific date
                        insights_data = await _fetch_insights_sync(
                            account_id=account_id,
                            since=current_date,
                            until=current_date,
                        )

                        # Cache in Redis
                        cached_count = await cache_insights_for_date(
                            account_id=account_id,
                            date_str=current_date.isoformat(),
                            insights_data=insights_data,
                        )

                        total_synced += cached_count
                        total_date_ranges += 1
                        logger.debug(
                            f"Cached {cached_count} insights for {account_id} on {current_date.isoformat()}"
                        )

                    except Exception as exc:
                        total_failed += 1
                        logger.exception(
                            f"Failed to sync cache for {account_id} on {current_date.isoformat()}: {exc}"
                        )

                    current_date += timedelta(days=1)

            except Exception as exc:
                logger.exception(f"Failed to process account {account_id} for cache sync: {exc}")
                total_failed += 1

        finished_at = datetime.utcnow()
        duration_seconds = (finished_at - started_at).total_seconds()

        logger.info(
            f"Realtime insights cache sync completed: "
            f"synced={total_synced} records, failed={total_failed}, "
            f"date_ranges={total_date_ranges}, accounts={len(accounts)}, "
            f"duration={duration_seconds:.2f}s"
        )

    except Exception as exc:
        logger.exception(f"Realtime insights cache sync failed: {exc}")
        raise


async def start_realtime_cache_scheduler() -> AsyncIOScheduler:
    """
    Start the realtime insights cache sync scheduler.
    Uses CronTrigger to execute at exact minute intervals (mm%N==0).

    Returns:
        Scheduler instance
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 600})

    # Calculate cron minute expression based on interval
    # For 30: "*/30" (0, 30)
    # For 20: "*/20" (0, 20, 40)
    # For 10: "*/10" (0, 10, 20, 30, 40, 50)
    minute_expression = f"*/{SYNC_INTERVAL_MINUTES}"

    # Use CronTrigger for exact minute scheduling
    trigger = CronTrigger(minute=minute_expression, second=0)

    _scheduler.add_job(
        _sync_realtime_insights,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        next_run_time=datetime.now(),  # Run immediately on startup
    )

    _scheduler.start()
    logger.info(
        f"Realtime insights cache scheduler started "
        f"(interval: every {SYNC_INTERVAL_MINUTES} minutes at mm%{SYNC_INTERVAL_MINUTES}==0)"
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
