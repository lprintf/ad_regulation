"""
Realtime insights cache sync scheduler.
Syncs from last synced date to today into Redis every N minutes (configurable: 10/20/30).
Executes at exact intervals (mm%N==0) for predictable scheduling.
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.insights_sync_service import _fetch_insights_sync
from api.services.sync_history_service import SyncHistoryService
from config import REALTIME_CACHE_SYNC_INTERVAL_MINUTES
from utils.db import get_all_ad_account_documents, InsightsSyncStateDocument, ADAccountDocument
from utils.redis_client import cache_insights_for_date

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "insights::realtime_cache_sync"
SYNC_INTERVAL_MINUTES = REALTIME_CACHE_SYNC_INTERVAL_MINUTES
_JOB_DISPLAY_NAME = "Realtime Cache Sync"


async def sync_redis_for_account(
    account: ADAccountDocument,
    *,
    trigger_type: str = "auto",
    triggered_by: str | None = None,
) -> tuple[int, str | None]:
    """
    Sync Redis cache for a single account using default strategy:
    - From last_synced_date + 1 day to today (max 7 days lookback)

    Args:
        account: AD account document
        trigger_type: Trigger type (auto/manual/retry)
        triggered_by: User ID who triggered (for manual triggers)

    Returns:
        Tuple of (records_synced, error_message)
    """
    account_id = account.id if account.id.startswith("act_") else f"act_{account.id}"
    today = datetime.utcnow().date()

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

    # If cache_start_date is in the future, create history record and skip
    if cache_start_date > today:
        logger.debug(f"Account {account_id} Redis cache is up to date, skipping")

        # Create history record showing the sync was triggered but skipped
        history = await SyncHistoryService.create_history_record(
            account_id=account.id,
            account_name=account.name,
            trigger_type=trigger_type,
            triggered_by=triggered_by or "redis_cache_service",
            since=cache_start_date,
            until=today,
            mode="sync",
            data_target="redis",
        )

        # Mark as success with 0 records and explanation
        await SyncHistoryService.update_history_status(
            history_id=history.id,
            status="success",
            records_count=0,
            metadata={"skip_reason": f"Already up to date (next sync date: {cache_start_date.isoformat()}, today: {today.isoformat()})", "skipped": True},
        )

        return 0, None

    logger.info(
        f"Syncing Redis cache for {account_id} from {cache_start_date.isoformat()} to {today.isoformat()}"
    )

    # Create sync history record
    history = await SyncHistoryService.create_history_record(
        account_id=account.id,
        account_name=account.name,
        trigger_type=trigger_type,
        triggered_by=triggered_by or "redis_cache_service",
        since=cache_start_date,
        until=today,
        mode="sync",
        data_target="redis",
    )

    try:
        # Track the actual range that was synced
        first_synced_date = None
        last_synced_date = None
        synced_records = 0

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

                synced_records += cached_count

                # Track the actual range
                if first_synced_date is None:
                    first_synced_date = current_date
                last_synced_date = current_date

                logger.debug(
                    f"Cached {cached_count} insights for {account_id} on {current_date.isoformat()}"
                )

            except Exception as exc:
                logger.exception(
                    f"Failed to sync Redis cache for {account_id} on {current_date.isoformat()}: {exc}"
                )

            current_date += timedelta(days=1)

        # Update Redis cache status in InsightsSyncStateDocument
        if first_synced_date and last_synced_date:
            now = datetime.utcnow()
            await InsightsSyncStateDocument.find_one(
                InsightsSyncStateDocument.account_id == account.id
            ).update(
                {
                    "$set": {
                        "redis_cache_since": datetime.combine(first_synced_date, datetime.min.time()),
                        "redis_cache_until": datetime.combine(last_synced_date, datetime.min.time()),
                        "redis_cache_updated_at": now,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )

            # Update history record with success status
            await SyncHistoryService.update_history_status(
                history_id=history.id,
                status="success",
                records_count=synced_records,
            )
            logger.info(
                f"Updated Redis cache status for {account_id}: {first_synced_date} → {last_synced_date}, {synced_records} records"
            )
        else:
            # If no data was synced, mark history as completed with 0 records
            await SyncHistoryService.update_history_status(
                history_id=history.id,
                status="success",
                records_count=0,
            )

        return synced_records, None

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"Failed to sync Redis cache for {account_id}: {exc}")

        # Mark history as failed
        await SyncHistoryService.update_history_status(
            history_id=history.id,
            status="failed",
            records_count=synced_records if 'synced_records' in locals() else 0,
            error_message=error_msg,
        )

        return 0, error_msg


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

        total_synced = 0
        total_failed = 0

        for account in accounts:
            try:
                synced_records, error_msg = await sync_redis_for_account(
                    account,
                    trigger_type="auto",
                    triggered_by="realtime_cache_scheduler",
                )

                if error_msg:
                    total_failed += 1
                    logger.error(f"Failed to sync Redis for {account.id}: {error_msg}")
                else:
                    total_synced += synced_records

            except Exception as exc:
                logger.exception(f"Failed to process account {account.id} for cache sync: {exc}")
                total_failed += 1

        finished_at = datetime.utcnow()
        duration_seconds = (finished_at - started_at).total_seconds()

        logger.info(
            f"Realtime insights cache sync completed: "
            f"synced={total_synced} records, failed={total_failed}, "
            f"accounts={len(accounts)}, "
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


def _serialize_job(job: Any | None) -> dict[str, Any]:
    """Serialize job information for API responses."""
    if job is None or _scheduler is None:
        status = "stopped"
        cron_repr = f"cron[minute='*/{SYNC_INTERVAL_MINUTES}', second='0']"
        next_run_time = None
    else:
        status = "running" if job.next_run_time is not None else "paused"
        cron_repr = str(job.trigger)
        next_run_time = job.next_run_time

    return {
        "id": JOB_ID,
        "name": _JOB_DISPLAY_NAME,
        "cron": cron_repr,
        "status": status,
        "next_run_at": next_run_time,
        "last_run_at": None,  # Not tracked yet
        "average_latency_ms": None,  # Not tracked yet
        "max_latency_ms": None,  # Not tracked yet
        "last_error": None,  # Not tracked yet
        "metadata": {"interval_minutes": SYNC_INTERVAL_MINUTES},
    }


def get_realtime_cache_scheduler_task() -> dict[str, Any]:
    """Get the current status of the realtime cache sync task."""
    job = _scheduler.get_job(JOB_ID) if _scheduler else None
    return _serialize_job(job)


def pause_realtime_cache_scheduler_task() -> None:
    """Pause the realtime cache sync task."""
    if _scheduler is None:
        raise ValueError("Realtime cache scheduler is not running")
    try:
        _scheduler.pause_job(JOB_ID)
        logger.info("Paused realtime cache scheduler task %s", JOB_ID)
    except JobLookupError as exc:
        raise ValueError("Realtime cache scheduler task not found") from exc


def resume_realtime_cache_scheduler_task() -> None:
    """Resume the realtime cache sync task."""
    if _scheduler is None:
        raise ValueError("Realtime cache scheduler is not running")
    try:
        _scheduler.resume_job(JOB_ID)
        logger.info("Resumed realtime cache scheduler task %s", JOB_ID)
    except JobLookupError as exc:
        raise ValueError("Realtime cache scheduler task not found") from exc


async def run_realtime_cache_scheduler_task_now() -> None:
    """
    Manually trigger the realtime cache sync task immediately.
    Runs in the background to avoid blocking the HTTP response.
    """
    if _scheduler is None:
        raise ValueError("Realtime cache scheduler is not running")
    job = _scheduler.get_job(JOB_ID)
    if job is None:
        raise ValueError("Realtime cache scheduler task not found")

    # Run in background to avoid blocking HTTP response
    asyncio.create_task(job.func(*job.args, **job.kwargs))
    logger.info("Realtime cache sync task triggered manually (running in background)")



def update_realtime_cache_scheduler_task(
    *, cron_expression: str | None = None, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Update realtime cache scheduler configuration.

    Note: Cron expression changes are not supported for realtime cache scheduler
    as it uses a fixed interval from config. Metadata updates are allowed.
    """
    if _scheduler is None:
        raise ValueError("Realtime cache scheduler is not running")

    job = _scheduler.get_job(JOB_ID)
    if job is None:
        raise ValueError("Realtime cache scheduler task not found")

    if cron_expression is not None:
        logger.warning(
            "Cron expression update ignored for realtime cache scheduler. "
            "Interval is controlled by REALTIME_CACHE_SYNC_INTERVAL_MINUTES config."
        )

    # Metadata updates are allowed but don't affect the job behavior
    if metadata is not None:
        logger.info("Metadata update for realtime cache scheduler: %s", metadata)

    return _serialize_job(job)
