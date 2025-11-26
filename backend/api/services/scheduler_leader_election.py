"""
基于 Redis 原子操作的调度器 Leader 选举
利用 SETNX 的原子性实现分布式锁，自动选举调度器实例
"""

import asyncio
import logging
import os
import socket
from typing import Optional

from redis.asyncio import Redis
from utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class SchedulerLeaderElection:
    """
    调度器 Leader 选举器

    原理：
    1. 多个实例竞争同一个 Redis key（调度器锁）
    2. 使用 SET key value EX seconds NX 原子抢占
    3. 只有持有锁的实例执行调度任务
    4. 定期续约（心跳），崩溃自动释放

    使用示例：
        election = SchedulerLeaderElection(redis)
        await election.start()

        if election.is_leader():
            # 执行调度任务
            pass
    """

    def __init__(
        self,
        redis: Redis,
        lock_key: str = "scheduler:leader_lock",
        ttl: int = 30,  # 锁过期时间（秒）
        renew_interval: int = 10,  # 续约间隔（秒）
    ):
        self.redis = redis
        self.lock_key = lock_key
        self.ttl = ttl
        self.renew_interval = renew_interval

        # 实例标识（容器名 + PID）
        self.instance_id = f"{socket.gethostname()}-{os.getpid()}"

        self._is_leader = False
        self._renew_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """启动选举流程"""
        if self._running:
            logger.warning(f"Leader election already running for {self.instance_id}")
            return

        self._running = True
        logger.info(f"Starting leader election for instance: {self.instance_id}")

        # 启动竞选和心跳任务
        self._renew_task = asyncio.create_task(self._election_loop())

    async def stop(self) -> None:
        """停止选举并释放锁"""
        self._running = False

        if self._renew_task:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError:
                pass

        # 主动释放锁（仅当自己持有时）
        if self._is_leader:
            await self._release_lock()
            self._is_leader = False

    def is_leader(self) -> bool:
        """当前实例是否是 Leader"""
        return self._is_leader

    async def _try_acquire_lock(self) -> bool:
        """
        尝试获取调度器锁（原子操作）

        使用 SET key value EX seconds NX:
        - NX: 只在 key 不存在时设置
        - EX: 设置过期时间（防止死锁）

        Returns:
            是否成功获取锁
        """
        result = await self.redis.set(
            self.lock_key,
            self.instance_id,
            ex=self.ttl,
            nx=True,  # 原子性保证：只在不存在时设置
        )

        return result is True

    async def _renew_lock(self) -> bool:
        """
        续约锁（心跳）

        使用 Lua 脚本保证原子性：
        1. 检查锁是否属于自己
        2. 如果是，刷新过期时间
        """
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        result = await self.redis.eval(
            lua_script,
            1,  # 1 个 key
            self.lock_key,
            self.instance_id,
            self.ttl,
        )

        return result == 1

    async def _release_lock(self) -> bool:
        """
        释放锁（原子操作）

        使用 Lua 脚本保证原子性：
        只有持有锁的实例才能释放
        """
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = await self.redis.eval(
            lua_script,
            1,
            self.lock_key,
            self.instance_id,
        )

        released = result == 1
        if released:
            logger.info(f"Released leader lock: {self.instance_id}")

        return released

    async def _election_loop(self) -> None:
        """选举主循环"""
        while self._running:
            try:
                if not self._is_leader:
                    # 尝试成为 Leader
                    if await self._try_acquire_lock():
                        self._is_leader = True
                        logger.info(
                            f"🎯 Became scheduler leader: {self.instance_id}"
                        )
                    else:
                        # 未获得锁，等待下次竞选
                        logger.debug(
                            f"Waiting for leadership (current: {await self.redis.get(self.lock_key)})"
                        )
                        await asyncio.sleep(self.renew_interval)
                        continue

                # 已是 Leader，定期续约
                if self._is_leader:
                    await asyncio.sleep(self.renew_interval)

                    renewed = await self._renew_lock()
                    if not renewed:
                        # 续约失败（可能被其他实例抢占）
                        logger.warning(
                            f"❌ Lost leader lock: {self.instance_id}"
                        )
                        self._is_leader = False
                    else:
                        logger.debug(f"Renewed leader lock: {self.instance_id}")

            except asyncio.CancelledError:
                logger.info("Election loop cancelled")
                break
            except Exception as e:
                logger.error(f"Election loop error: {e}", exc_info=True)
                self._is_leader = False
                await asyncio.sleep(5)  # 出错后短暂休眠


# ===== 全局单例 =====

_leader_election: Optional[SchedulerLeaderElection] = None


async def get_leader_election() -> SchedulerLeaderElection:
    """获取选举器单例"""
    global _leader_election
    if _leader_election is None:
        redis = await get_redis_client()
        _leader_election = SchedulerLeaderElection(redis)
    return _leader_election


def is_scheduler_leader() -> bool:
    """
    当前实例是否是调度器 Leader

    Returns:
        True if this instance is the scheduler leader
    """
    if _leader_election is None:
        return False
    return _leader_election.is_leader()


async def start_leader_election() -> None:
    """启动 Leader 选举"""
    election = await get_leader_election()
    await election.start()


async def stop_leader_election() -> None:
    """停止 Leader 选举"""
    if _leader_election is not None:
        await _leader_election.stop()


async def get_leader_info() -> dict:
    """
    获取 Leader 信息

    Returns:
        Leader 信息字典
    """
    election = await get_leader_election()

    # 查询 Redis 获取当前 Leader
    current_leader = await election.redis.get(election.lock_key)
    ttl = await election.redis.ttl(election.lock_key)

    return {
        "current_leader": current_leader,
        "is_self_leader": election.is_leader(),
        "self_instance_id": election.instance_id,
        "lock_ttl_seconds": ttl,
        "lock_key": election.lock_key,
    }
