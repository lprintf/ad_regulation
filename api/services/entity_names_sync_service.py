"""
Service for syncing Facebook ad entity names (Campaign, AdSet, Ad).
Fetches missing entity names from Facebook API on demand.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Literal, Set
from pymongo import UpdateOne

from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.exceptions import FacebookRequestError

from utils.db import (
    AdEntityNamesDocument,
    get_document_collection,
)
from utils.fb_api_flyweight_factory import get_api

MAX_ENTITY_NAME_BATCH_SIZE = 50


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
    async def fetch_entity_name(
        entity_type: Literal["campaign", "adset", "ad"],
        entity_id: str,
        account_id: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> Dict[str, Any] | None:
        """
        从 Facebook API 获取单个实体的名称和状态信息。
        实现指数退避重试机制以处理速率限制。

        Args:
            entity_type: 实体类型 (campaign, adset, ad)
            entity_id: 实体ID
            account_id: 广告账号ID（需要带 act_ 前缀）
            max_retries: 最大重试次数（默认3次）
            base_delay: 基础延迟时间（秒，默认2秒）

        Returns:
            包含 entity_name, configured_status, effective_status 的字典
            如果获取失败返回 None
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                # 获取 API 实例
                api = await get_api(account_id)

                # 根据实体类型选择对应的类和字段
                if entity_type == "campaign":
                    entity_obj = Campaign(fbid=entity_id, api=api)
                    fields = [
                        Campaign.Field.name,
                        Campaign.Field.configured_status,
                        Campaign.Field.effective_status,
                    ]
                elif entity_type == "adset":
                    entity_obj = AdSet(fbid=entity_id, api=api)
                    fields = [
                        AdSet.Field.name,
                        AdSet.Field.configured_status,
                        AdSet.Field.effective_status,
                    ]
                elif entity_type == "ad":
                    entity_obj = Ad(fbid=entity_id, api=api)
                    fields = [
                        Ad.Field.name,
                        Ad.Field.configured_status,
                        Ad.Field.effective_status,
                    ]
                else:
                    raise ValueError(f"Unknown entity_type: {entity_type}")

                # 调用 API 获取数据
                entity_obj.api_get(fields=fields)

                # 提取字段值
                if entity_type == "campaign":
                    name = entity_obj.get(Campaign.Field.name, "")
                    configured_status = entity_obj.get(
                        Campaign.Field.configured_status, None
                    )
                    effective_status = entity_obj.get(
                        Campaign.Field.effective_status, None
                    )
                elif entity_type == "adset":
                    name = entity_obj.get(AdSet.Field.name, "")
                    configured_status = entity_obj.get(
                        AdSet.Field.configured_status, None
                    )
                    effective_status = entity_obj.get(AdSet.Field.effective_status, None)
                else:  # ad
                    name = entity_obj.get(Ad.Field.name, "")
                    configured_status = entity_obj.get(Ad.Field.configured_status, None)
                    effective_status = entity_obj.get(Ad.Field.effective_status, None)

                return {
                    "entity_name": name,
                    "configured_status": configured_status,
                    "effective_status": effective_status,
                }

            except FacebookRequestError as e:
                last_error = e
                error_code = e.api_error_code()
                error_subcode = e.api_error_subcode()

                # 检查是否为速率限制错误（错误代码 80004）
                if error_code == 80004 or error_subcode == 2446079:
                    if attempt < max_retries:
                        # 计算指数退避延迟时间
                        delay = base_delay * (2 ** attempt)
                        print(
                            f"Rate limit hit for {entity_type} {entity_id}. "
                            f"Retry {attempt + 1}/{max_retries} after {delay}s delay. "
                            f"Error: {str(e)}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(
                            f"Rate limit exceeded for {entity_type} {entity_id} "
                            f"after {max_retries} retries. Error: {str(e)}"
                        )
                        return None
                else:
                    # 非速率限制错误，直接返回失败
                    print(
                        f"Facebook API error for {entity_type} {entity_id}: "
                        f"Code={error_code}, Subcode={error_subcode}, Message={str(e)}"
                    )
                    return None

            except Exception as e:
                last_error = e
                print(
                    f"Unexpected error fetching {entity_type} name for {entity_id}: "
                    f"{type(e).__name__}: {str(e)}"
                )
                import traceback
                traceback.print_exc()
                return None

        # 如果所有重试都失败
        print(f"All retries failed for {entity_type} {entity_id}. Last error: {last_error}")
        return None

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

        account_id_with_prefix = (
            account_id if account_id.startswith("act_") else f"act_{account_id}"
        )
        account_id_without_prefix = account_id.replace("act_", "")

        synced = 0
        failed = 0
        rate_limited = 0
        operations = []
        synced_entities: List[Dict[str, Any]] = []
        failed_entities: List[str] = []

        print(f"Starting sync for {len(entity_ids)} {entity_type} entities in account {account_id_with_prefix}")

        for idx, entity_id in enumerate(normalized_ids, 1):
            # 在请求之间添加延迟（除了第一个请求）
            if idx > 1:
                await asyncio.sleep(batch_delay)

            # 获取实体名称
            entity_data = await EntityNamesSyncService.fetch_entity_name(
                entity_type, entity_id, account_id_with_prefix
            )

            if entity_data is None:
                failed += 1
                failed_entities.append(entity_id)
                # 简单检测：如果连续失败可能是速率限制
                if failed > len(entity_ids) * 0.3:  # 超过30%失败率
                    rate_limited += 1
                continue

            # 准备 upsert 操作
            # IMPORTANT: Include account_id in the query filter to prevent
            # overwriting records from different accounts with the same entity_id
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
                            "entity_name": entity_data["entity_name"],
                            "configured_status": entity_data["configured_status"],
                            "effective_status": entity_data["effective_status"],
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
                    "entity_name": entity_data["entity_name"],
                    "configured_status": entity_data["configured_status"],
                    "effective_status": entity_data["effective_status"],
                    "entity_type": entity_type,
                    "account_id": account_id_without_prefix,
                }
            )

            # 定期把 upsert 任务交给后台写库，避免阻塞响应
            if len(operations) >= 50:
                batch = operations
                operations = []
                EntityNamesSyncService._schedule_background_write(batch)

        # 把剩余操作交给后台写库协程
        if operations:
            batch = operations
            operations = []
            EntityNamesSyncService._schedule_background_write(batch)

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
