"""
Entity name sync service with Redis-based debouncing.
Prevents concurrent duplicate sync requests for the same entity.
"""

import asyncio
from typing import Any, Dict, List, Literal
from datetime import datetime

from utils.redis_client import get_redis
from utils.account_id import remove_account_id_prefix
from .entity_names_sync_service import EntityNamesSyncService


class EntitySyncDebounceService:
    """Service for managing entity name sync with debouncing"""

    SYNC_LOCK_TTL = 60  # Lock duration: 60 seconds
    SYNC_LOCK_PREFIX = "sync:entity"

    @staticmethod
    def _get_lock_key(account_id: str, entity_type: str, entity_id: str) -> str:
        """Generate Redis lock key for entity sync"""
        clean_account_id = remove_account_id_prefix(account_id)
        return f"{EntitySyncDebounceService.SYNC_LOCK_PREFIX}:{clean_account_id}:{entity_type}:{entity_id}"

    @staticmethod
    async def is_syncing(account_id: str, entity_type: str, entity_id: str) -> bool:
        """Check if entity is currently being synced"""
        redis = get_redis()
        lock_key = EntitySyncDebounceService._get_lock_key(account_id, entity_type, entity_id)
        return await redis.exists(lock_key) > 0

    @staticmethod
    async def acquire_sync_lock(account_id: str, entity_type: str, entity_id: str) -> bool:
        """
        Try to acquire sync lock for entity.

        Returns:
            True if lock acquired (can proceed with sync)
            False if lock already exists (someone else is syncing)
        """
        redis = get_redis()
        lock_key = EntitySyncDebounceService._get_lock_key(account_id, entity_type, entity_id)

        # SET NX (only set if not exists) with TTL
        result = await redis.set(
            lock_key,
            datetime.utcnow().isoformat(),
            ex=EntitySyncDebounceService.SYNC_LOCK_TTL,
            nx=True
        )
        return result is not None

    @staticmethod
    async def release_sync_lock(account_id: str, entity_type: str, entity_id: str) -> None:
        """Release sync lock for entity"""
        redis = get_redis()
        lock_key = EntitySyncDebounceService._get_lock_key(account_id, entity_type, entity_id)
        await redis.delete(lock_key)

    @staticmethod
    async def sync_with_debounce(
        account_id: str,
        entity_ids: List[str],
        entity_type: Literal["campaign", "adset", "ad"],
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync entity names with debouncing.

        Args:
            account_id: Ad account ID
            entity_ids: List of entity IDs to sync
            entity_type: Type of entity (campaign, adset, ad)
            force: If True, bypass debounce check (for manual refresh)

        Returns:
            {
                "synced": int,
                "failed": int,
                "skipped": int,  # Already syncing
                "entities": list,
                "status": "completed" | "partial" | "skipped"
            }
        """
        if not entity_ids:
            return {
                "synced": 0,
                "failed": 0,
                "skipped": 0,
                "entities": [],
                "status": "completed"
            }

        # Filter out entities that are already being synced (unless force=True)
        clean_account_id = remove_account_id_prefix(account_id)
        to_sync = []
        skipped = []

        if not force:
            for entity_id in entity_ids:
                is_locked = await EntitySyncDebounceService.is_syncing(
                    clean_account_id, entity_type, entity_id
                )
                if is_locked:
                    skipped.append(entity_id)
                else:
                    to_sync.append(entity_id)
        else:
            to_sync = entity_ids

        if not to_sync:
            return {
                "synced": 0,
                "failed": 0,
                "skipped": len(skipped),
                "entities": [],
                "status": "skipped",
                "message": f"{len(skipped)} entities are already being synced"
            }

        # Acquire locks for entities we're about to sync
        locks_acquired = []
        for entity_id in to_sync:
            acquired = await EntitySyncDebounceService.acquire_sync_lock(
                clean_account_id, entity_type, entity_id
            )
            if acquired:
                locks_acquired.append(entity_id)

        if not locks_acquired:
            return {
                "synced": 0,
                "failed": 0,
                "skipped": len(entity_ids),
                "entities": [],
                "status": "skipped",
                "message": "All entities are currently being synced by another request"
            }

        # Perform actual sync
        try:
            result = await EntityNamesSyncService.sync_entity_names(
                account_id=clean_account_id,
                entity_ids=locks_acquired,
                entity_type=entity_type,
            )

            # Release locks
            for entity_id in locks_acquired:
                await EntitySyncDebounceService.release_sync_lock(
                    clean_account_id, entity_type, entity_id
                )

            # Add skipped count to result
            result["skipped"] = len(skipped)
            result["status"] = "completed" if result["failed"] == 0 else "partial"

            return result

        except Exception as e:
            # Release locks on error
            for entity_id in locks_acquired:
                await EntitySyncDebounceService.release_sync_lock(
                    clean_account_id, entity_type, entity_id
                )
            raise
