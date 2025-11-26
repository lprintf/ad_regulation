"""
Sync history management service.

Handles creation, retrieval, and updating of sync history records.
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any

from beanie import PydanticObjectId

from utils.db import (
    SyncHistoryDocument,
    InsightsSyncStateDocument,
    ADAccountDocument,
    get_all_ad_account_documents,
)
from utils.account_id import normalize_account_id

logger = logging.getLogger(__name__)


class SyncHistoryService:
    """Manages sync history records and overview data."""

    @staticmethod
    async def create_history_record(
        *,
        account_id: str,
        account_name: str | None,
        trigger_type: str,
        triggered_by: str | None,
        since: date,
        until: date,
        mode: str,
        data_target: str = "mongodb",
    ) -> SyncHistoryDocument:
        """
        Create a new sync history record with pending status.

        Args:
            account_id: Ad account ID
            account_name: Display name of the account
            trigger_type: How sync was triggered (manual/auto/retry)
            triggered_by: User ID who triggered it
            since: Start date
            until: End date
            mode: Execution mode (sync/async)
            data_target: Data storage target (mongodb/redis/hybrid)

        Returns:
            Created history document
        """
        total_days = (until - since).days + 1

        history = SyncHistoryDocument(
            account_id=account_id,
            account_name=account_name,
            trigger_type=trigger_type,  # type: ignore
            triggered_by=triggered_by,
            since=datetime(since.year, since.month, since.day),
            until=datetime(until.year, until.month, until.day),
            mode=mode,  # type: ignore
            data_target=data_target,  # type: ignore
            status="pending",
            total_days=total_days,
            started_at=datetime.utcnow(),
        )

        await history.insert()
        logger.info(
            f"Created sync history record {history.id} for account {account_id}"
        )
        return history

    @staticmethod
    async def update_history_status(
        *,
        history_id: PydanticObjectId | str,
        status: str,
        records_count: int = 0,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Update sync history record status.

        Args:
            history_id: History record ID
            status: New status (running/success/failed)
            records_count: Number of records synced
            error_message: Error message if failed
            metadata: Optional metadata to attach to the record
        """
        now = datetime.utcnow()
        update_fields: dict[str, Any] = {
            "status": status,
            "records_count": records_count,
        }

        if status in ("success", "failed"):
            # Calculate duration
            history = await SyncHistoryDocument.get(history_id)
            if history:
                duration = (now - history.started_at).total_seconds()
                update_fields["duration_seconds"] = duration
                update_fields["completed_at"] = now
                update_fields["percent_complete"] = 100

        if error_message:
            update_fields["error_message"] = error_message

        if metadata:
            update_fields["metadata"] = metadata

        await SyncHistoryDocument.find_one(
            SyncHistoryDocument.id == history_id
        ).update({"$set": update_fields})

        logger.info(f"Updated sync history {history_id} to status: {status}")

    @staticmethod
    async def update_history_progress(
        *,
        history_id: PydanticObjectId | str,
        processed_days: int,
        current_date: str | None = None,
    ) -> None:
        """
        Update sync history progress (for async jobs).

        Args:
            history_id: History record ID
            processed_days: Number of days processed so far
            current_date: Current date being processed
        """
        history = await SyncHistoryDocument.get(history_id)
        if not history:
            return

        percent = int((processed_days / history.total_days) * 100) if history.total_days > 0 else 0

        await SyncHistoryDocument.find_one(
            SyncHistoryDocument.id == history_id
        ).update(
            {
                "$set": {
                    "processed_days": processed_days,
                    "current_date": current_date,
                    "percent_complete": min(percent, 99),  # Never 100 until complete
                    "status": "running",
                }
            }
        )

    @staticmethod
    async def get_history_list(
        *,
        account_id: str | None = None,
        status: str | None = None,
        trigger_type: str | None = None,
        data_target: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Get paginated sync history records.

        Args:
            account_id: Filter by account ID (optional)
            status: Filter by status (optional)
            trigger_type: Filter by trigger type (optional)
            data_target: Filter by data target (mongodb/redis/hybrid) (optional)
            page: Page number (1-indexed)
            page_size: Records per page

        Returns:
            Tuple of (history records, total count)
        """
        query = SyncHistoryDocument.find()

        if account_id:
            query = query.find(SyncHistoryDocument.account_id == account_id)
        if status:
            query = query.find(SyncHistoryDocument.status == status)
        if trigger_type:
            query = query.find(SyncHistoryDocument.trigger_type == trigger_type)
        if data_target:
            query = query.find(SyncHistoryDocument.data_target == data_target)

        # Get total count
        total = await query.count()

        # Get paginated results
        skip = (page - 1) * page_size
        records = (
            await query.sort(-SyncHistoryDocument.started_at)
            .skip(skip)
            .limit(page_size)
            .to_list()
        )

        items = [
            {
                "id": str(record.id),
                "account_id": record.account_id,
                "account_name": record.account_name,
                "trigger_type": record.trigger_type,
                "triggered_by": record.triggered_by,
                "since": record.since.date().isoformat(),
                "until": record.until.date().isoformat(),
                "mode": record.mode,
                "data_target": record.data_target,
                "status": record.status,
                "started_at": record.started_at.isoformat() + "Z",
                "completed_at": record.completed_at.isoformat() + "Z"
                if record.completed_at
                else None,
                "records_count": record.records_count,
                "error_message": record.error_message,
                "duration_seconds": record.duration_seconds,
                "percent_complete": record.percent_complete,
                "total_days": record.total_days,
                "processed_days": record.processed_days,
            }
            for record in records
        ]

        return items, total

    @staticmethod
    async def get_sync_overview() -> list[dict[str, Any]]:
        """
        Get sync overview for all accounts.

        Returns:
            List of account sync overview items
        """
        accounts = await get_all_ad_account_documents(fetch_links=True)
        states = await InsightsSyncStateDocument.find_all().to_list()
        state_map = {state.account_id: state for state in states}

        # Get most recent MongoDB and Redis history for each account
        mongodb_history_map: dict[str, SyncHistoryDocument] = {}
        redis_history_map: dict[str, SyncHistoryDocument] = {}

        for account in accounts:
            # Get most recent MongoDB sync history
            mongodb_recent = (
                await SyncHistoryDocument.find(
                    SyncHistoryDocument.account_id == account.id,
                    SyncHistoryDocument.data_target == "mongodb",
                )
                .sort(-SyncHistoryDocument.started_at)
                .limit(1)
                .to_list()
            )
            if mongodb_recent:
                mongodb_history_map[account.id] = mongodb_recent[0]

            # Get most recent Redis sync history
            redis_recent = (
                await SyncHistoryDocument.find(
                    SyncHistoryDocument.account_id == account.id,
                    SyncHistoryDocument.data_target == "redis",
                )
                .sort(-SyncHistoryDocument.started_at)
                .limit(1)
                .to_list()
            )
            if redis_recent:
                redis_history_map[account.id] = redis_recent[0]

        items: list[dict[str, Any]] = []
        for account in accounts:
            state = state_map.get(account.id)
            mongodb_history = mongodb_history_map.get(account.id)
            redis_history = redis_history_map.get(account.id)

            # Determine MongoDB status
            mongodb_status = "pending"
            mongodb_is_running = False
            mongodb_last_error = None
            if mongodb_history:
                if mongodb_history.status == "running":
                    mongodb_status = "running"
                    mongodb_is_running = True
                elif mongodb_history.status in ("success", "failed"):
                    mongodb_status = mongodb_history.status
                    if mongodb_history.status == "failed":
                        mongodb_last_error = mongodb_history.error_message
            elif state and state.last_status:
                mongodb_status = state.last_status
                mongodb_last_error = state.last_error

            # Determine Redis status
            redis_status = "pending"
            redis_is_running = False
            redis_last_error = None
            if redis_history:
                if redis_history.status == "running":
                    redis_status = "running"
                    redis_is_running = True
                elif redis_history.status in ("success", "failed"):
                    redis_status = redis_history.status
                    if redis_history.status == "failed":
                        redis_last_error = redis_history.error_message

            items.append(
                {
                    "account_id": account.id,
                    "account_name": account.name,
                    # MongoDB 同步状态
                    "mongodb_status": mongodb_status,
                    "mongodb_is_running": mongodb_is_running,
                    "mongodb_last_synced_at": state.last_synced_at.isoformat() + "Z"
                    if state and state.last_synced_at
                    else (mongodb_history.completed_at.isoformat() + "Z" if mongodb_history and mongodb_history.completed_at else None),
                    # MongoDB 数据覆盖范围
                    "mongodb_coverage_since": state.obs_since.date().isoformat()
                    if state and state.obs_since
                    else None,
                    "mongodb_coverage_until": state.obs_until.date().isoformat()
                    if state and state.obs_until
                    else None,
                    "mongodb_last_error": mongodb_last_error,
                    "mongodb_last_history_id": str(mongodb_history.id) if mongodb_history else None,
                    # Redis 同步状态
                    "redis_status": redis_status,
                    "redis_is_running": redis_is_running,
                    "redis_last_synced_at": state.redis_cache_updated_at.isoformat() + "Z"
                    if state and state.redis_cache_updated_at
                    else (redis_history.completed_at.isoformat() + "Z" if redis_history and redis_history.completed_at else None),
                    "redis_cache_since": state.redis_cache_since.date().isoformat()
                    if state and state.redis_cache_since
                    else None,
                    "redis_cache_until": state.redis_cache_until.date().isoformat()
                    if state and state.redis_cache_until
                    else None,
                    "redis_last_error": redis_last_error,
                    "redis_last_history_id": str(redis_history.id) if redis_history else None,
                }
            )

        # Sort by mongodb_last_synced_at descending, then by account name
        items.sort(
            key=lambda x: (
                x["mongodb_last_synced_at"] or "",
                x["account_name"] or x["account_id"],
            ),
            reverse=True,
        )

        return items

    @staticmethod
    async def get_history_by_id(history_id: str) -> dict[str, Any] | None:
        """
        Get a single sync history record by ID.

        Args:
            history_id: History record ID

        Returns:
            History record dict or None if not found
        """
        try:
            record = await SyncHistoryDocument.get(history_id)
        except Exception:
            return None

        if not record:
            return None

        return {
            "id": str(record.id),
            "account_id": record.account_id,
            "account_name": record.account_name,
            "trigger_type": record.trigger_type,
            "triggered_by": record.triggered_by,
            "since": record.since.date().isoformat(),
            "until": record.until.date().isoformat(),
            "mode": record.mode,
            "data_target": record.data_target,
            "status": record.status,
            "started_at": record.started_at.isoformat() + "Z",
            "completed_at": record.completed_at.isoformat() + "Z"
            if record.completed_at
            else None,
            "records_count": record.records_count,
            "error_message": record.error_message,
            "duration_seconds": record.duration_seconds,
            "percent_complete": record.percent_complete,
            "total_days": record.total_days,
            "processed_days": record.processed_days,
            "metadata": record.metadata,
        }
