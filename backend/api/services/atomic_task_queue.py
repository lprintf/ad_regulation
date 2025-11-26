"""
基于 Redis 原子操作的轻量级分布式任务队列

利用 Redis BRPOP 的原子性实现：
- 多实例自动负载均衡（无需协调）
- 任务不重复执行（BRPOP 原子获取）
- 零额外依赖（只需 Redis）
- 高性能低延迟（~1ms）
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable

from redis.asyncio import Redis

from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class AtomicTaskQueue:
    """原子任务队列 - 利用 Redis BRPOP 原子性实现分布式任务调度"""

    def __init__(self, queue_name: str, redis: Redis):
        self.queue_name = queue_name
        self.redis = redis
        self.handlers: dict[str, Callable] = {}
        self._running = False
        self._workers: list[asyncio.Task] = []

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        scheduled_time: datetime | None = None,
    ) -> None:
        """
        原子入队操作

        Args:
            task_type: 任务类型（用于路由到对应 handler）
            payload: 任务数据
            priority: 优先级（0=普通，1=高优先级）
            scheduled_time: 调度时间（用于保留任务的预期执行时间）
        """
        task = {
            "type": task_type,
            "payload": payload,
            "enqueued_at": datetime.utcnow().isoformat(),
            "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
        }

        # 根据优先级选择队列
        queue_key = f"{self.queue_name}:high" if priority > 0 else self.queue_name

        # LPUSH 是原子操作，线程安全
        await self.redis.lpush(queue_key, json.dumps(task))

    async def enqueue_batch(
        self,
        tasks: list[tuple[str, dict[str, Any]]],
        scheduled_time: datetime | None = None,
    ) -> int:
        """
        批量入队（使用 pipeline 保证原子性）

        Args:
            tasks: 任务列表 [(task_type, payload), ...]
            scheduled_time: 所有任务的调度时间

        Returns:
            入队的任务数量
        """
        if not tasks:
            return 0

        pipeline = self.redis.pipeline()
        for task_type, payload in tasks:
            task = {
                "type": task_type,
                "payload": payload,
                "enqueued_at": datetime.utcnow().isoformat(),
                "scheduled_time": scheduled_time.isoformat()
                if scheduled_time
                else None,
            }
            pipeline.lpush(self.queue_name, json.dumps(task))

        # pipeline.execute() 保证原子性
        await pipeline.execute()
        logger.info(f"Enqueued {len(tasks)} tasks to '{self.queue_name}'")
        return len(tasks)

    def register_handler(self, task_type: str, handler: Callable):
        """
        注册任务处理函数

        Args:
            task_type: 任务类型
            handler: 异步或同步处理函数，接受 (payload: dict) 参数
        """
        self.handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")

    async def start_workers(self, concurrency: int = 5):
        """
        启动多个 worker 协程消费任务

        利用 BRPOP 的原子性：
        - 多个 worker 同时 BRPOP，每个任务只会被一个 worker 获取
        - 自动负载均衡，无需额外协调机制
        - 支持跨进程、跨容器的分布式消费

        Args:
            concurrency: 并发 worker 数量
        """
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(f"worker-{i}"))
            for i in range(concurrency)
        ]

        logger.info(
            f"Started {concurrency} workers for queue '{self.queue_name}' "
            f"(handlers: {list(self.handlers.keys())})"
        )

    async def _worker_loop(self, worker_id: str):
        """Worker 主循环 - 持续从队列获取并执行任务"""
        # 优先处理高优先级队列
        queue_keys = [
            f"{self.queue_name}:high",
            self.queue_name,
        ]

        logger.info(f"{worker_id} started, waiting for tasks...")

        while self._running:
            try:
                # BRPOP 是原子的阻塞操作（timeout=1秒）
                # 多个 worker 竞争，只有一个能获取到任务
                result = await self.redis.brpop(queue_keys, timeout=1)

                if not result:
                    continue  # 超时，继续等待

                queue_key, task_json = result
                task = json.loads(task_json)

                # 执行任务
                await self._execute_task(worker_id, task)

            except asyncio.CancelledError:
                logger.info(f"{worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"{worker_id} error: {e}", exc_info=True)
                await asyncio.sleep(1)  # 出错后短暂休眠

        logger.info(f"{worker_id} stopped")

    async def _execute_task(self, worker_id: str, task: dict):
        """执行单个任务"""
        task_type = task["type"]
        payload = task["payload"]
        scheduled_time_str = task.get("scheduled_time")

        handler = self.handlers.get(task_type)
        if not handler:
            logger.error(f"No handler for task type: {task_type}")
            return

        try:
            start = datetime.utcnow()

            # 将 scheduled_time 注入到 payload（如果存在）
            if scheduled_time_str:
                payload["_scheduled_time"] = scheduled_time_str

            # 执行 handler
            if asyncio.iscoroutinefunction(handler):
                await handler(payload)
            else:
                await asyncio.to_thread(handler, payload)

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info(f"{worker_id} completed {task_type} in {duration:.2f}s")

        except Exception as e:
            logger.error(
                f"{worker_id} failed to execute {task_type}: {e}",
                exc_info=True,
            )

            # TODO: 可选的失败重试机制
            # await self._retry_task(task, max_retries=3)

    async def stop(self):
        """停止所有 worker"""
        logger.info(f"Stopping workers for queue '{self.queue_name}'...")
        self._running = False

        # 等待所有 worker 完成当前任务
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

        logger.info("All workers stopped")

    async def get_queue_size(self) -> dict[str, int]:
        """获取队列长度统计"""
        return {
            "normal": await self.redis.llen(self.queue_name),
            "high": await self.redis.llen(f"{self.queue_name}:high"),
        }


# ===== 全局队列单例 =====

_sync_queue: AtomicTaskQueue | None = None


async def get_sync_queue() -> AtomicTaskQueue:
    """获取同步任务队列单例"""
    global _sync_queue
    if _sync_queue is None:
        redis = await get_redis_client()
        _sync_queue = AtomicTaskQueue("tasks:insights_sync", redis)

        # 延迟注册 handler（避免循环导入）
        from api.services.task_handlers import (
            handle_sync_account_redis,
            handle_sync_account_mongo,
        )

        _sync_queue.register_handler("sync_account_redis", handle_sync_account_redis)
        _sync_queue.register_handler("sync_account_mongo", handle_sync_account_mongo)

    return _sync_queue


async def start_sync_queue_workers(concurrency: int = 10):
    """启动同步任务队列的 worker"""
    queue = await get_sync_queue()
    await queue.start_workers(concurrency)
    logger.info(f"Sync queue workers started with concurrency={concurrency}")


async def stop_sync_queue_workers():
    """停止同步任务队列的 worker"""
    global _sync_queue
    if _sync_queue:
        await _sync_queue.stop()
        logger.info("Sync queue workers stopped")
