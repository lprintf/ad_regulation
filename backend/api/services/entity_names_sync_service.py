"""
Service for syncing Facebook ad entity names (Campaign, AdSet, Ad).
Fetches missing entity names from Facebook API on demand.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Literal, Set
from pymongo import UpdateOne

from facebook_business.exceptions import FacebookRequestError

from utils.account_id import normalize_account_id, remove_account_id_prefix
from utils.db import (
    AdEntityNamesDocument,
    get_document_collection,
)
from utils.fb_api_flyweight_factory import get_api

MAX_ENTITY_NAME_BATCH_SIZE = 50
RATE_LIMIT_ERROR_CODES = {80004}
RATE_LIMIT_ERROR_SUBCODES = {2446079}


def _chunk_entity_ids(entity_ids: List[str], chunk_size: int) -> List[List[str]]:
    if chunk_size <= 0:
        return [entity_ids]
    return [entity_ids[i : i + chunk_size] for i in range(0, len(entity_ids), chunk_size)]


class EntityNamesSyncService:
    """Service for syncing ad entity names from Facebook API"""

    @staticmethod
    def _schedule_background_write(operations: list[UpdateOne]) -> None:
        """Fire-and-forget bulk write so API response isn't blocked by DB I/O."""

        if not operations:
            return

        async def _run(batch: list[UpdateOne]) -> None:
            collection = get_document_collection(AdEntityNamesDocument)
            try:
                await collection.bulk_write(batch, ordered=False)
                print(f"[EntityNamesSync] Background bulk write completed for {len(batch)} entities")
            except Exception as exc:
                print(f"[EntityNamesSync] Background bulk write failed ({len(batch)} entities): {exc}")

        asyncio.create_task(_run(operations))

    @staticmethod
    async def fetch_entity_names_batch(
        entity_type: Literal["campaign", "adset", "ad"],
        entity_ids: List[str],
        account_id: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> tuple[Dict[str, Dict[str, Any]], bool]:
        """
        ?? Graph API ? ids ???????????

        Returns:
            (entity_id -> ????, ????????)
        """
        if not entity_ids:
            return {}, False

        params = {
            "ids": ",".join(entity_ids),
            "fields": "name,configured_status,effective_status",
        }

        for attempt in range(max_retries + 1):
            try:
                api = await get_api(account_id)
                response = api.call("GET", (), params=params)
                payload = response.json() or {}
                normalized: Dict[str, Dict[str, Any]] = {}

                for entity_id, data in payload.items():
                    if not isinstance(data, dict):
                        continue
                    normalized[str(entity_id)] = {
                        "entity_name": data.get("name", ""),
                        "configured_status": data.get("configured_status"),
                        "effective_status": data.get("effective_status"),
                    }

                return normalized, False

            except FacebookRequestError as exc:
                error_code = exc.api_error_code()
                error_subcode = exc.api_error_subcode()
                is_rate_limited = (
                    (error_code in RATE_LIMIT_ERROR_CODES)
                    or (error_subcode in RATE_LIMIT_ERROR_SUBCODES)
                )

                if is_rate_limited and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    print(
                        f"Rate limit hit when fetching {len(entity_ids)} {entity_type} names. Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue

                if is_rate_limited:
                    print(
                        f"Rate limit exceeded when fetching {len(entity_ids)} {entity_type} names after {max_retries} retries."
                    )
                    return {}, True

                print(
                    f"Facebook API error fetching {entity_type} batch ({len(entity_ids)} ids): {exc.api_error_message()}"
                )
                return {}, False

            except Exception as exc:  # pragma: no cover - defensive logging
                print(
                    f"Unexpected error fetching {entity_type} batch ({len(entity_ids)} ids): {type(exc).__name__}: {exc}"
                )
                return {}, False

        print(
            f"Failed to fetch {entity_type} batch ({len(entity_ids)} ids) after retries."
        )
        return {}, False

    @staticmethod
    async def sync_entity_names(
        account_id: str,
        entity_ids: List[str],
        entity_type: Literal["campaign", "adset", "ad"],
        batch_delay: float = 0.5,
    ) -> Dict[str, Any]:
        """
        为指定的实体ID列表同步名称（按需同步）。
        在请求之间添加延迟以避免速率限制。

        Args:
            account_id: 广告账号ID（不带 act_ 前缀）
            entity_ids: 需要同步名称的实体ID列表
            entity_type: 实体类型 (campaign, adset, ad)
            batch_delay: 每个请求之间的延迟时间（秒，默认0.5秒）

        Returns:
            同步结果统计：{"synced": count, "failed": count, "total": count, "rate_limited": count}
        """
        if not entity_ids:
            return {
                "synced": 0,
                "failed": 0,
                "total": 0,
                "rate_limited": 0,
                "entities": [],
                "failed_entities": [],
            }

        # 去重，避免重复同步，并限制最大批次
        normalized_ids: List[str] = []
        seen: Set[str] = set()
        for entity_id in entity_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            normalized_ids.append(entity_id)

        if len(normalized_ids) > MAX_ENTITY_NAME_BATCH_SIZE:
            raise ValueError(
                f"最多一次同步 {MAX_ENTITY_NAME_BATCH_SIZE} 个实体，请分批请求"
            )

        account_id_with_prefix = normalize_account_id(account_id)
        account_id_without_prefix = remove_account_id_prefix(account_id)

        synced = 0
        failed = 0
        rate_limited = 0
        operations = []
        synced_entities: List[Dict[str, Any]] = []
        failed_entities: List[str] = []

        print(
            f"Starting sync for {len(normalized_ids)} {entity_type} entities in account {account_id_with_prefix}"
        )

        batches = _chunk_entity_ids(normalized_ids, MAX_ENTITY_NAME_BATCH_SIZE)

        for batch_index, batch_ids in enumerate(batches, start=1):
            if batch_index > 1:
                await asyncio.sleep(batch_delay)

            batch_data, hit_rate_limit = await EntityNamesSyncService.fetch_entity_names_batch(
                entity_type=entity_type,
                entity_ids=batch_ids,
                account_id=account_id_with_prefix,
            )

            if hit_rate_limit:
                rate_limited += 1
                failed += len(batch_ids)
                failed_entities.extend(batch_ids)
                print(
                    f"Rate limit encountered. Stopping sync after batch {batch_index}/{len(batches)}."
                )
                break

            for entity_id in batch_ids:
                entity_data = batch_data.get(entity_id)
                if not entity_data:
                    failed += 1
                    failed_entities.append(entity_id)
                    continue

                entity_name = (entity_data.get("entity_name") or "").strip()

                operations.append(
                    UpdateOne(
                        {
                            "account_id": account_id_without_prefix,
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                        },
                        {
                            "$set": {
                                "account_id": account_id_without_prefix,
                                "entity_type": entity_type,
                                "entity_id": entity_id,
                                "entity_name": entity_name,
                                "configured_status": entity_data.get("configured_status"),
                                "effective_status": entity_data.get("effective_status"),
                                "updated_at": datetime.utcnow(),
                            },
                            "$setOnInsert": {"fetched_at": datetime.utcnow()},
                        },
                        upsert=True,
                    )
                )

                synced += 1
                synced_entities.append(
                    {
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "configured_status": entity_data.get("configured_status"),
                        "effective_status": entity_data.get("effective_status"),
                        "entity_type": entity_type,
                        "account_id": account_id_without_prefix,
                    }
                )

                if len(operations) >= 50:
                    batch_ops = operations
                    operations = []
                    EntityNamesSyncService._schedule_background_write(batch_ops)

        if operations:
            batch_ops = operations
            operations = []
            EntityNamesSyncService._schedule_background_write(batch_ops)

        result = {
            "synced": synced,
            "failed": failed,
            "total": len(normalized_ids),
            "rate_limited": rate_limited,
            "entities": synced_entities,
            "failed_entities": failed_entities,
        }

        print(f"Sync completed: {result}")
        return result
