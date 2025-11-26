"""
分布式任务处理器

定义所有任务队列的具体处理逻辑
"""

import logging
from datetime import datetime
from typing import Any

from api.services.insights_sync_service import InsightsSyncService
from api.services.realtime_cache_scheduler import sync_redis_for_account
from utils.db import ADAccountDocument

logger = logging.getLogger(__name__)


async def handle_sync_account_redis(payload: dict[str, Any]):
    """
    处理 Redis 缓存同步任务

    Payload:
        account_id: 广告账号 ID
        _scheduled_time: 调度时间（ISO 格式字符串，可选）
    """
    account_id = payload["account_id"]
    scheduled_time_str = payload.get("_scheduled_time")

    # 从数据库加载账号信息
    account = await ADAccountDocument.find_one(ADAccountDocument.id == account_id)

    if not account:
        logger.warning(f"Account {account_id} not found in database")
        return

    # 记录调度信息
    if scheduled_time_str:
        logger.info(
            f"Syncing Redis for {account_id} (scheduled at {scheduled_time_str})"
        )

    # 执行同步
    try:
        records, error = await sync_redis_for_account(
            account,
            trigger_type="auto",
            triggered_by=None,
        )

        if error:
            logger.error(f"Failed to sync Redis for {account_id}: {error}")
            raise Exception(error)
        else:
            logger.info(f"Successfully synced {records} records to Redis for {account_id}")

    except Exception as e:
        logger.error(f"Error syncing Redis for {account_id}: {e}", exc_info=True)
        raise


async def handle_sync_account_mongo(payload: dict[str, Any]):
    """
    处理 MongoDB 历史数据同步任务

    Payload:
        account_id: 广告账号 ID
        since: 开始日期 (YYYY-MM-DD)
        until: 结束日期 (YYYY-MM-DD)
        _scheduled_time: 调度时间（ISO 格式字符串，可选）
    """
    account_id = payload["account_id"]
    since = payload["since"]
    until = payload["until"]
    scheduled_time_str = payload.get("_scheduled_time")

    # 记录调度信息
    if scheduled_time_str:
        logger.info(
            f"Syncing MongoDB for {account_id} ({since} to {until}) "
            f"(scheduled at {scheduled_time_str})"
        )

    # 执行同步
    try:
        result = await InsightsSyncService.sync_insights_for_account(
            ad_account_id=account_id,
            since=since,
            until=until,
        )

        logger.info(
            f"Successfully synced MongoDB for {account_id}: "
            f"{result.get('records_synced', 0)} records"
        )

    except Exception as e:
        logger.error(
            f"Error syncing MongoDB for {account_id} ({since} to {until}): {e}",
            exc_info=True,
        )
        raise
