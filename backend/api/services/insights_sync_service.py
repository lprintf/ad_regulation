"""
Historical insights ingestion and sync service.

Handles storage of Facebook Ads Insights into MongoDB, including
daily backfills, manual re-sync, and status tracking for UI display.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence, Tuple

import calendar

from facebook_business.adobjects.adreportrun import AdReportRun

from utils.db import (
    ADAccountDocument,
    InsightsDailyDocument,
    InsightsSyncStateDocument,
    drop_insights_indexes,
    ensure_insights_indexes,
    get_all_ad_account_documents,
    get_document_collection,
)
from utils.account_id import normalize_account_id
from utils.fb_api_flyweight_factory import get_ad_object
from utils.insight_tool import ATOMIC_FIELDS, get_atomic_metric, get_daily_insight

from pymongo import UpdateOne

logger = logging.getLogger(__name__)

INSIGHTS_ASYNC_THRESHOLD_DAYS = 7
REALTIME_LOOKBACK_DAYS = 3
HISTORICAL_MONTH_LOOKBACK = 37
ASYNC_POLL_INTERVAL = 30  # seconds
ASYNC_MAX_ATTEMPTS = 200

INSIGHT_FIELDS = [
    "account_id",
    "campaign_id",
    "adset_id",
    "ad_id",
    *ATOMIC_FIELDS,
]


def _to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _combine_date(dt: date) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


def _subtract_months(input_date: date, months: int) -> date:
    year = input_date.year - months // 12
    month = input_date.month - months % 12
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(input_date.day, last_day)
    return date(year, month, day)


def _normalize_insight_row(raw: dict[str, Any]) -> dict[str, Any]:
    metrics = get_atomic_metric(raw)
    normalized = {
        "account_id": raw.get("account_id"),
        "campaign_id": raw.get("campaign_id"),
        "adset_id": raw.get("adset_id"),
        "ad_id": raw["ad_id"],
        "date_start": _to_date(raw["date_start"]),
        **metrics,
    }
    return normalized


async def _fetch_insights_sync(
    account_id: str,
    since: date,
    until: date,
) -> list[dict[str, Any]]:
    ad_object = await get_ad_object(account_id, account_id)
    insights_cursor = await asyncio.to_thread(
        get_daily_insight,
        adobject=ad_object,
        level="ad",
        fields=INSIGHT_FIELDS,
        since=since.strftime("%Y-%m-%d"),
        until=until.strftime("%Y-%m-%d"),
        sort="",
        limit=100000,
        is_async=False,
    )
    return [_normalize_insight_row(raw) for raw in insights_cursor]



async def _bulk_upsert_insights(
    records: Sequence[dict[str, Any]],
    *,
    fetched_start: date,
    fetched_end: date,
) -> None:
    if not records:
        return

    collection = get_document_collection(InsightsDailyDocument)
    operations: list[UpdateOne] = []
    now = datetime.utcnow()
    range_start_dt = _combine_date(fetched_start)
    range_end_dt = _combine_date(fetched_end)

    for record in records:
        if not record:
            continue
        ad_id = record.get("ad_id")
        raw_date = record.get("date_start")
        if not ad_id or raw_date is None:
            continue

        if isinstance(raw_date, datetime):
            date_start_dt = datetime(raw_date.year, raw_date.month, raw_date.day)
        elif isinstance(raw_date, date):
            date_start_dt = _combine_date(raw_date)
        elif isinstance(raw_date, str):
            date_start_dt = _combine_date(_to_date(raw_date))
        else:
            continue

        update_doc = {
            "account_id": record.get("account_id"),
            "campaign_id": record.get("campaign_id"),
            "adset_id": record.get("adset_id"),
            "ad_id": ad_id,
            "date_start": date_start_dt,
            "fetched_range_start": range_start_dt,
            "fetched_range_end": range_end_dt,
            "updated_at": now,
        }

        for key, value in record.items():
            if key in {
                "account_id",
                "campaign_id",
                "adset_id",
                "ad_id",
                "date_start",
            }:
                continue
            update_doc[key] = value

        operations.append(
            UpdateOne(
                {"ad_id": ad_id, "date_start": date_start_dt},
                {
                    "$set": update_doc,
                    "$setOnInsert": {"ingested_at": now},
                },
                upsert=True,
            )
        )

    if operations:
        await collection.bulk_write(operations, ordered=False)



@dataclass
class SyncResult:
    total_accounts: int
    processed_accounts: dict[str, dict[str, Any]]
    failed_accounts: dict[str, str]


@dataclass
class AsyncJobWrapper:
    account: ADAccountDocument
    account_id: str
    job: AdReportRun
    since: date
    until: date


class InsightsSyncService:
    """Coordinates insights ingestion tasks and status management."""

    @staticmethod
    async def run_daily_schedule(triggered_by: str | None = "scheduler") -> SyncResult | None:
        today = datetime.utcnow().date()
        target_until = today - timedelta(days=REALTIME_LOOKBACK_DAYS)

        accounts = await get_all_ad_account_documents(fetch_links=True)
        if not accounts:
            logger.warning("No ad accounts registered; skipping insights sync")
            return None

        states = await InsightsSyncStateDocument.find_all().to_list()
        state_map = {state.account_id: state for state in states}

        base_start = _subtract_months(today, HISTORICAL_MONTH_LOOKBACK)
        earliest_start: date | None = None
        for account in accounts:
            account_start = base_start
            state = state_map.get(account.id)
            if state:
                has_full_history = False
                if state.initial_requested_since and state.initial_requested_since.date() <= base_start:
                    has_full_history = True
                elif state.obs_since and state.obs_since.date() <= base_start:
                    has_full_history = True

                if state.last_synced_date and has_full_history:
                    last_date = state.last_synced_date.date()
                    account_start = max(account_start, last_date + timedelta(days=1))

            earliest_start = account_start if earliest_start is None else min(earliest_start, account_start)

        if earliest_start is None or earliest_start > target_until:
            logger.info("All accounts are up to date (target until %s); skipping sync", target_until)
            return None

        logger.info(
            "Running scheduled insights sync per account (since >= %s, until %s)",
            earliest_start,
            target_until,
        )

        result = await InsightsSyncService.sync_range(
            since=earliest_start,
            until=target_until,
            mode="auto",
            triggered_by=triggered_by,
            accounts=accounts,
            state_map=state_map,
        )

        if not result.processed_accounts and not result.failed_accounts:
            return None
        return result

    @staticmethod
    async def sync_range(
        *,
        since: date,
        until: date,
        mode: str,
        triggered_by: str | None,
        accounts: list[ADAccountDocument] | None = None,
        state_map: dict[str, InsightsSyncStateDocument] | None = None,
        respect_last_synced: bool = True,
    ) -> SyncResult:
        if since > until:
            raise ValueError("Since date must be earlier than or equal to until date")

        if accounts is None:
            accounts = await get_all_ad_account_documents(fetch_links=True)
        if state_map is None:
            states = await InsightsSyncStateDocument.find_all().to_list()
            state_map = {state.account_id: state for state in states}

        if not accounts:
            return SyncResult(total_accounts=0, processed_accounts={}, failed_accounts={})

        now = datetime.utcnow()
        today_date = now.date()
        base_start = _subtract_months(today_date, HISTORICAL_MONTH_LOOKBACK)
        sync_ranges: list[tuple[ADAccountDocument, date, date]] = []
        async_ranges: list[tuple[ADAccountDocument, date, date]] = []
        skipped_accounts: list[tuple[ADAccountDocument, str]] = []  # Track skipped accounts with reason

        for account in accounts:
            account_start = max(since, base_start)
            state = state_map.get(account.id)
            if respect_last_synced and state and state.last_synced_date:
                last_date = state.last_synced_date.date()
                account_start = max(account_start, last_date + timedelta(days=1))

            if account_start > until:
                # Account is already up to date
                skipped_accounts.append((account, f"Already up to date (last sync: {account_start.isoformat()}, target: {until.isoformat()})"))
                continue

            days = (until - account_start).days + 1
            if days <= 0:
                skipped_accounts.append((account, f"No new data to sync (calculated days: {days})"))
                continue

            range_payload = {
                "since": account_start.isoformat(),
                "until": until.isoformat(),
            }

            if days <= INSIGHTS_ASYNC_THRESHOLD_DAYS:
                range_payload["mode"] = "sync"
                sync_ranges.append((account, account_start, until))
            else:
                range_payload["mode"] = "async"
                async_ranges.append((account, account_start, until))

            range_payload["trigger"] = mode
            if triggered_by:
                range_payload["triggered_by"] = triggered_by

            update_fields = {
                "last_status": "running",
                "last_error": None,
                "metadata": {"range": range_payload},
                "updated_at": now,
            }
            state_record = state_map.get(account.id)

            existing_initial = (
                state_record.initial_requested_since.date()
                if state_record and state_record.initial_requested_since
                else None
            )
            desired_initial = min(account_start, base_start) if mode == "auto" else account_start
            if existing_initial is None or desired_initial < existing_initial:
                update_fields["initial_requested_since"] = _combine_date(desired_initial)

            existing_obs_since = (
                state_record.obs_since.date() if state_record and state_record.obs_since else None
            )
            if mode == "auto":
                desired_obs_since = base_start
                if existing_obs_since is None or existing_obs_since > desired_obs_since:
                    update_fields["obs_since"] = _combine_date(desired_obs_since)
            else:
                if existing_obs_since is None or account_start < existing_obs_since:
                    update_fields["obs_since"] = _combine_date(account_start)

            existing_obs_until = (
                state_record.obs_until.date() if state_record and state_record.obs_until else None
            )
            if existing_obs_until is None or until > existing_obs_until:
                update_fields["obs_until"] = _combine_date(until)

            await InsightsSyncStateDocument.find_one(
                InsightsSyncStateDocument.account_id == account.id
            ).update(
                {
                    "$set": update_fields,
                },
                upsert=True,
            )

        # Initialize result dictionaries
        processed_accounts: dict[str, dict[str, Any]] = {}
        failed_accounts: dict[str, str] = {}

        # Handle skipped accounts - create history records for "already up to date" cases
        if skipped_accounts:
            from api.services.sync_history_service import SyncHistoryService

            for account, reason in skipped_accounts:
                try:
                    # Create history record showing the sync was triggered but skipped
                    history = await SyncHistoryService.create_history_record(
                        account_id=account.id,
                        account_name=account.name,
                        trigger_type=mode if mode in ("manual", "auto", "retry") else "manual",
                        triggered_by=triggered_by or "insights_sync_service",
                        since=since,
                        until=until,
                        mode="sync",
                        data_target="mongodb",
                    )

                    # Mark as success with 0 records and explanation in metadata
                    await SyncHistoryService.update_history_status(
                        history_id=history.id,
                        status="success",
                        records_count=0,
                        metadata={"skip_reason": reason, "skipped": True},
                    )

                    logger.info(f"Created history record for skipped account {account.id}: {reason}")
                except Exception as exc:
                    logger.exception(f"Failed to create history for skipped account {account.id}: {exc}")

        if not sync_ranges and not async_ranges:
            logger.info(
                "No accounts require synchronization for window %s-%s (all up to date)",
                since,
                until,
            )
            return SyncResult(
                total_accounts=len(accounts),
                processed_accounts=processed_accounts,
                failed_accounts=failed_accounts,
            )

        total_days = (until - since).days + 1
        disable_indexes = total_days > 365
        if disable_indexes:
            dropped = await drop_insights_indexes()
            logger.info("Dropped insights indexes to speed up backfill: %s", dropped)

        try:
            if sync_ranges:
                sync_processed, sync_failures = await InsightsSyncService._process_sync_accounts(
                    accounts=sync_ranges,
                    trigger=mode,
                    triggered_by=triggered_by,
                )
                processed_accounts.update(sync_processed)
                failed_accounts.update(sync_failures)

            if async_ranges:
                async_processed, async_failures = await InsightsSyncService._process_async_accounts(
                    accounts=async_ranges,
                    trigger=mode,
                    triggered_by=triggered_by,
                )
                processed_accounts.update(async_processed)
                failed_accounts.update(async_failures)
        finally:
            if disable_indexes:
                await ensure_insights_indexes()
                logger.info("Insights indexes recreated after backfill")

        return SyncResult(
            total_accounts=len(accounts),
            processed_accounts=processed_accounts,
            failed_accounts=failed_accounts,
        )

    @staticmethod
    async def get_account_sync_status() -> list[dict[str, Any]]:
        states = (
            await InsightsSyncStateDocument.find_all()
            .sort(-InsightsSyncStateDocument.updated_at)
            .to_list()
        )
        account_docs = await get_all_ad_account_documents(fetch_links=True)
        account_map = {doc.id: doc for doc in account_docs}
        items: list[dict[str, Any]] = []
        for state in states:
            account = account_map.get(state.account_id)
            range_info = (state.metadata or {}).get("range", {})
            items.append(
                {
                    "account_id": state.account_id,
                    "account_name": account.name if account else None,
                    "status": state.last_status,
                    "since": state.initial_requested_since.date().isoformat()
                    if state.initial_requested_since
                    else None,
                    "until": state.last_synced_date.date().isoformat()
                    if state.last_synced_date
                    else None,
                    "obs_since": state.obs_since.date().isoformat()
                    if state.obs_since
                    else None,
                    "obs_until": state.obs_until.date().isoformat()
                    if state.obs_until
                    else None,
                    "last_synced_at": state.last_synced_at.isoformat()
                    if state.last_synced_at
                    else None,
                    "last_error": state.last_error,
                    "range_since": range_info.get("since"),
                    "range_until": range_info.get("until"),
                    "mode": range_info.get("mode"),
                    "trigger": range_info.get("trigger"),
                    "triggered_by": range_info.get("triggered_by"),
                    "updated_at": state.updated_at.isoformat()
                    if state.updated_at
                    else None,
                }
            )
        return items

    @staticmethod
    async def trigger_manual_sync(
        account_ids: list[str] | None,
        since: date,
        until: date,
        *,
        triggered_by: str | None,
    ) -> SyncResult:
        if since > until:
            raise ValueError("since date must not be later than until date")

        accounts = await get_all_ad_account_documents(fetch_links=True)
        if account_ids:
            normalized_targets = {normalize_account_id(acc_id) for acc_id in account_ids}
            accounts = [
                account
                for account in accounts
                if normalize_account_id(account.id) in normalized_targets
            ]

        if not accounts:
            return SyncResult(total_accounts=0, processed_accounts={}, failed_accounts={})

        states = await InsightsSyncStateDocument.find_all().to_list()
        state_map = {state.account_id: state for state in states}

        today_date = datetime.utcnow().date()
        base_start = _subtract_months(today_date, HISTORICAL_MONTH_LOOKBACK)
        adjusted_since = max(since, base_start)

        if adjusted_since > until:
            raise ValueError(
                f"Requested range {since}~{until} overlaps before supported window starting {base_start}"
            )

        return await InsightsSyncService.sync_range(
            since=adjusted_since,
            until=until,
            mode="manual",
            triggered_by=triggered_by,
            accounts=accounts,
            state_map=state_map,
            respect_last_synced=False,
        )

    @staticmethod
    async def _process_sync_accounts(
        *,
        accounts: list[tuple[ADAccountDocument, date, date]],
        trigger: str,
        triggered_by: str | None,
    ) -> Tuple[dict[str, dict[str, Any]], dict[str, str]]:
        from api.services.sync_history_service import SyncHistoryService

        processed: dict[str, dict[str, Any]] = {}
        failures: dict[str, str] = {}
        for account, range_start, range_end in accounts:
            account_id = normalize_account_id(account.id)
            range_payload = {
                "since": range_start.isoformat(),
                "until": range_end.isoformat(),
                "mode": "sync",
            }
            range_payload["trigger"] = trigger
            if triggered_by:
                range_payload["triggered_by"] = triggered_by

            # Create sync history record
            history = await SyncHistoryService.create_history_record(
                account_id=account.id,
                account_name=account.name,
                trigger_type=trigger if trigger in ("manual", "auto", "retry") else "manual",
                triggered_by=triggered_by or "insights_sync_service",
                since=range_start,
                until=range_end,
                mode="sync",
                data_target="mongodb",
            )

            try:
                records = await _fetch_insights_sync(account_id, range_start, range_end)
                await _bulk_upsert_insights(
                    records,
                    fetched_start=range_start,
                    fetched_end=range_end,
                )
                now = datetime.utcnow()
                await InsightsSyncStateDocument.find_one(
                    InsightsSyncStateDocument.account_id == account.id
                ).update(
                    {
                        "$set": {
                            "last_synced_at": now,
                            "last_synced_date": _combine_date(range_end),
                            "last_status": "success",
                            "last_error": None,
                            "metadata": {"range": {**range_payload, "records": len(records)}},
                            "updated_at": now,
                        },
                    },
                    upsert=True,
                )

                # Update sync history record with success status
                await SyncHistoryService.update_history_status(
                    history_id=history.id,
                    status="success",
                    records_count=len(records),
                )

                processed[account_id] = {
                    "mode": "sync",
                    "since": range_start.isoformat(),
                    "until": range_end.isoformat(),
                    "records": len(records),
                    "trigger": trigger,
                    "triggered_by": triggered_by,
                }
            except Exception as exc:
                message = str(exc)
                failures[account_id] = message
                logger.exception(
                    "Failed to sync insights for account %s within %s-%s: %s",
                    account_id,
                    range_start,
                    range_end,
                    message,
                )
                now = datetime.utcnow()
                await InsightsSyncStateDocument.find_one(
                    InsightsSyncStateDocument.account_id == account.id
                ).update(
                    {
                        "$set": {
                            "last_status": "failed",
                            "last_error": message,
                            "metadata": {"range": range_payload},
                            "updated_at": now,
                        }
                    },
                    upsert=True,
                )

                # Update sync history record with failed status
                await SyncHistoryService.update_history_status(
                    history_id=history.id,
                    status="failed",
                    records_count=0,
                    error_message=message,
                )

        return processed, failures

    @staticmethod
    async def _process_async_accounts(
        *,
        accounts: list[tuple[ADAccountDocument, date, date]],
        trigger: str,
        triggered_by: str | None,
    ) -> Tuple[dict[str, dict[str, Any]], dict[str, str]]:
        from api.services.sync_history_service import SyncHistoryService

        processed: dict[str, dict[str, Any]] = {}
        failures: dict[str, str] = {}
        range_lookup = {
            normalize_account_id(account.id): (range_start, range_end)
            for account, range_start, range_end in accounts
        }

        # Create sync history records for all accounts before launching jobs
        history_map: dict[str, Any] = {}
        for account, range_start, range_end in accounts:
            account_id = normalize_account_id(account.id)
            history = await SyncHistoryService.create_history_record(
                account_id=account.id,
                account_name=account.name,
                trigger_type=trigger if trigger in ("manual", "auto", "retry") else "manual",
                triggered_by=triggered_by or "insights_sync_service",
                since=range_start,
                until=range_end,
                mode="async",
                data_target="mongodb",
            )
            history_map[account_id] = history

        jobs, launch_failures = await _launch_async_jobs(accounts)
        for account_id, message in launch_failures.items():
            failures[account_id] = message
            logger.error("Failed to launch async insights job for account %s: %s", account_id, message)
            now = datetime.utcnow()
            range_bounds = range_lookup.get(account_id)
            range_payload = {"mode": "async", "trigger": trigger}
            if range_bounds:
                range_payload["since"] = range_bounds[0].isoformat()
                range_payload["until"] = range_bounds[1].isoformat()
            if triggered_by:
                range_payload["triggered_by"] = triggered_by
            await InsightsSyncStateDocument.find_one(
                InsightsSyncStateDocument.account_id == account_id
            ).update(
                {
                    "$set": {
                        "last_status": "failed",
                        "last_error": message,
                        "metadata": {"range": range_payload},
                        "updated_at": now,
                    }
                },
                upsert=True,
            )

            # Update sync history record with failed status (job launch failure)
            history = history_map.get(account_id)
            if history:
                await SyncHistoryService.update_history_status(
                    history_id=history.id,
                    status="failed",
                    records_count=0,
                    error_message=f"Failed to launch async job: {message}",
                )
        completed_jobs, failed_jobs = await _await_async_jobs(jobs)
        for wrapper in completed_jobs:
            range_payload = {"since": wrapper.since.isoformat(), "until": wrapper.until.isoformat(), "mode": "async", "trigger": trigger}
            if triggered_by:
                range_payload["triggered_by"] = triggered_by
            try:
                records = await _collect_async_job_records(wrapper.job)
                await _bulk_upsert_insights(records, fetched_start=wrapper.since, fetched_end=wrapper.until)
                now = datetime.utcnow()
                await InsightsSyncStateDocument.find_one(
                    InsightsSyncStateDocument.account_id == wrapper.account.id
                ).update(
                    {
                        "$set": {
                            "last_synced_at": now,
                            "last_synced_date": _combine_date(wrapper.until),
                            "last_status": "success",
                            "last_error": None,
                            "metadata": {"range": {**range_payload, "records": len(records)}},
                            "updated_at": now,
                        },
                    },
                    upsert=True,
                )

                # Update sync history record with success status
                history = history_map.get(wrapper.account_id)
                if history:
                    await SyncHistoryService.update_history_status(
                        history_id=history.id,
                        status="success",
                        records_count=len(records),
                    )

                processed[wrapper.account_id] = {
                    "mode": "async",
                    "since": wrapper.since.isoformat(),
                    "until": wrapper.until.isoformat(),
                    "records": len(records),
                    "trigger": trigger,
                    "triggered_by": triggered_by,
                }
            except Exception as exc:
                message = str(exc)
                failures[wrapper.account_id] = message
                logger.exception("Failed to store async insights for account %s within %s-%s: %s", wrapper.account_id, wrapper.since, wrapper.until, message)
                now = datetime.utcnow()
                await InsightsSyncStateDocument.find_one(
                    InsightsSyncStateDocument.account_id == wrapper.account.id
                ).update(
                    {
                        "$set": {
                            "last_status": "failed",
                            "last_error": message,
                            "metadata": {"range": range_payload},
                            "updated_at": now,
                        }
                    },
                    upsert=True,
                )

                # Update sync history record with failed status (data collection/storage failure)
                history = history_map.get(wrapper.account_id)
                if history:
                    await SyncHistoryService.update_history_status(
                        history_id=history.id,
                        status="failed",
                        records_count=0,
                        error_message=message,
                    )

        for wrapper, reason in failed_jobs:
            range_payload = {"since": wrapper.since.isoformat(), "until": wrapper.until.isoformat(), "mode": "async", "trigger": trigger}
            if triggered_by:
                range_payload["triggered_by"] = triggered_by
            message = f"Async job failed with status {reason}"
            failures[wrapper.account_id] = message
            logger.error("Async insights job failed for account %s within %s-%s: %s", wrapper.account_id, wrapper.since, wrapper.until, reason)
            now = datetime.utcnow()
            await InsightsSyncStateDocument.find_one(
                InsightsSyncStateDocument.account_id == wrapper.account.id
            ).update(
                {
                    "$set": {
                        "last_status": "failed",
                        "last_error": message,
                        "metadata": {"range": range_payload},
                        "updated_at": now,
                    }
                },
                upsert=True,
            )

            # Update sync history record with failed status (async job failure)
            history = history_map.get(wrapper.account_id)
            if history:
                await SyncHistoryService.update_history_status(
                    history_id=history.id,
                    status="failed",
                    records_count=0,
                    error_message=message,
                )
        return processed, failures

async def _launch_async_jobs(
    accounts: list[tuple[ADAccountDocument, date, date]]
) -> Tuple[list[AsyncJobWrapper], dict[str, str]]:
    jobs: list[AsyncJobWrapper] = []
    failures: dict[str, str] = {}
    for account, range_start, range_end in accounts:
        account_id = normalize_account_id(account.id)
        try:
            ad_object = await get_ad_object(account_id, account_id)
            job = await asyncio.to_thread(
                get_daily_insight,
                adobject=ad_object,
                level="ad",
                fields=INSIGHT_FIELDS,
                since=range_start.strftime("%Y-%m-%d"),
                until=range_end.strftime("%Y-%m-%d"),
                sort="",
                limit=100000,
                is_async=True,
            )
            jobs.append(
                AsyncJobWrapper(
                    account=account,
                    account_id=account_id,
                    job=job,
                    since=range_start,
                    until=range_end,
                )
            )
        except Exception as exc:
            failures[account_id] = str(exc)
    return jobs, failures


async def _await_async_jobs(
    jobs: list[AsyncJobWrapper],
) -> Tuple[list[AsyncJobWrapper], list[Tuple[AsyncJobWrapper, str]]]:
    running = jobs.copy()
    completed: list[AsyncJobWrapper] = []
    failed: list[Tuple[AsyncJobWrapper, str]] = []
    for attempt in range(ASYNC_MAX_ATTEMPTS):
        for i in range(len(running) - 1, -1, -1):
            wrapper = running[i]
            job = wrapper.job
            await asyncio.to_thread(job.api_get)
            status = job.get(AdReportRun.Field.async_status, "Unknown")
            if status == "Job Completed":
                running.pop(i)
                completed.append(wrapper)
                logger.info(
                    "Async insights job completed for account %s (%s-%s)",
                    wrapper.account_id,
                    wrapper.since,
                    wrapper.until,
                )
            elif status in {"Job Failed", "Job Skipped"}:
                running.pop(i)
                failed.append((wrapper, status))
                logger.error(
                    "Async insights job %s for account %s failed with status %s",
                    job.get(AdReportRun.Field.id),
                    wrapper.account_id,
                    status,
                )
            else:
                percent = job.get(AdReportRun.Field.async_percent_completion, 0)
                logger.debug(
                    "Async job %s for account %s in progress: %s%%",
                    job.get(AdReportRun.Field.id),
                    wrapper.account_id,
                    percent,
                )
        if not running:
            break
        await asyncio.sleep(ASYNC_POLL_INTERVAL)
    if running:
        for wrapper in running:
            failed.append((wrapper, "timeout"))
            logger.warning(
                "Async insights job %s for account %s timed out after %s attempts",
                wrapper.job.get(AdReportRun.Field.id),
                wrapper.account_id,
                ASYNC_MAX_ATTEMPTS,
            )
    return completed, failed


async def _collect_async_job_records(job: AdReportRun) -> list[dict[str, Any]]:
    insights_cursor = await asyncio.to_thread(job.get_insights)
    return [_normalize_insight_row(raw) for raw in insights_cursor]







