"""
APScheduler integration for rule engine periodic jobs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from apscheduler.job import Job
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.rule_engine_service import RuleEngineService
from api.services.scheduler_state_store import (
    RULE_SCHEDULER_NAMESPACE,
    load_namespace,
    save_namespace,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_JOB_DISPLAY_NAMES = {
    "rules::daily_evaluation": "每日规则评估",
    "rules::hourly_new_ad_scan": "每小时新广告扫描",
    "rules::daily_auto_unbind": "每日自动解绑",
}


@dataclass
class JobMetrics:
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    runs: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def update(self, *, finished_at: datetime, latency_ms: float, error: Exception | None) -> None:
        self.last_run_at = finished_at
        self.runs += 1
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        if error:
            self.last_status = "error"
            self.last_error = str(error)
        else:
            self.last_status = "success"
            self.last_error = None

    @property
    def average_latency_ms(self) -> float | None:
        if self.runs == 0:
            return None
        return self.total_latency_ms / self.runs


@dataclass
class SchedulerJobConfig:
    cron_kwargs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_paused: bool = False

    def cron_expression(self) -> str:
        if not self.cron_kwargs:
            return "cron[]"
        parts = []
        for key in sorted(self.cron_kwargs):
            value = self.cron_kwargs[key]
            if value is None or value == "":
                parts.append(f"{key}=None")
            else:
                parts.append(f"{key}='{value}'")
        return f"cron[{', '.join(parts)}]"


def _parse_cron_expression(expression: str) -> dict[str, Any]:
    expression = expression.strip()
    if not expression.startswith("cron[") or not expression.endswith("]"):
        raise ValueError("Cron 表达式需保持 `cron[...]` 格式")

    inner = expression[len("cron[") : -1].strip()
    if not inner:
        return {}

    result: dict[str, Any] = {}
    for part in inner.split(","):
        key_value = part.strip()
        if not key_value:
            continue
        if "=" not in key_value:
            raise ValueError(f"非法 Cron 片段: {key_value}")
        key, value = key_value.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError("Cron 字段名不能为空")

        if value in {"None", "null"}:
            result[key] = None
            continue

        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        result[key] = value
    return result


_job_metrics: dict[str, JobMetrics] = {}
_job_configs: dict[str, SchedulerJobConfig] = {
    "rules::daily_evaluation": SchedulerJobConfig(
        cron_kwargs={"hour": "2", "minute": "0"}
    ),
    "rules::hourly_new_ad_scan": SchedulerJobConfig(
        cron_kwargs={"minute": "0"}, metadata={"ad_accounts": []}
    ),
    "rules::daily_auto_unbind": SchedulerJobConfig(
        cron_kwargs={"hour": "3", "minute": "30"}, metadata={"inactive_days": 7}
    ),
}


def _serialize_configs_for_store() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for job_id, config in _job_configs.items():
        payload[job_id] = {
            "cron_kwargs": dict(config.cron_kwargs),
            "metadata": dict(config.metadata),
            "is_paused": bool(config.is_paused),
        }
    return payload


def _persist_configs() -> None:
    save_namespace(RULE_SCHEDULER_NAMESPACE, _serialize_configs_for_store())


def _hydrate_configs_from_store() -> None:
    stored = load_namespace(RULE_SCHEDULER_NAMESPACE)
    for job_id, raw_config in stored.items():
        if not isinstance(raw_config, dict):
            continue

        config = _job_configs.setdefault(job_id, SchedulerJobConfig())

        cron_kwargs = raw_config.get("cron_kwargs")
        if isinstance(cron_kwargs, dict):
            config.cron_kwargs = dict(cron_kwargs)

        metadata = raw_config.get("metadata")
        if isinstance(metadata, dict):
            config.metadata = dict(metadata)

        is_paused = raw_config.get("is_paused")
        if isinstance(is_paused, bool):
            config.is_paused = is_paused

        if config.metadata:
            metrics = _job_metrics.setdefault(job_id, JobMetrics())
            metrics.metadata = dict(config.metadata)


_hydrate_configs_from_store()

SchedulerJobHandler = Callable[[dict[str, Any] | None], Awaitable[None]]
_job_handlers: dict[str, SchedulerJobHandler] = {}


async def _scheduled_rule_execution(config: dict[str, Any] | None = None) -> None:
    scheduled_time = datetime.utcnow()
    limit: int | None = None
    if config:
        raw_limit = config.get("limit") or config.get("max_bindings")
        if isinstance(raw_limit, int):
            limit = raw_limit
        elif isinstance(raw_limit, str) and raw_limit.isdigit():
            limit = int(raw_limit)

    await _execute_job(
        job_id="rules::daily_evaluation",
        coro=RuleEngineService.run_scheduled_evaluations(
            scheduled_run_time=scheduled_time,
            limit=limit,
        ),
        metadata=config,
    )


async def _scheduled_auto_unbind(config: dict[str, Any] | None = None) -> None:
    inactive_days = 7
    if config and "inactive_days" in config:
        raw_value = config["inactive_days"]
        if isinstance(raw_value, int):
            inactive_days = raw_value
        elif isinstance(raw_value, str):
            try:
                inactive_days = int(raw_value)
            except ValueError:
                logger.warning(
                    "Invalid inactive_days value '%s' for auto unbind task",
                    raw_value,
                )

    await _execute_job(
        job_id="rules::daily_auto_unbind",
        coro=RuleEngineService.auto_unbind_stale_bindings(
            inactive_days=inactive_days
        ),
        metadata=config,
    )


async def _scheduled_scan_new_ads(config: dict[str, Any] | None = None) -> None:
    ad_accounts: list[str] | None = None
    if config:
        raw_accounts = config.get("ad_accounts") or config.get("accounts")
        if isinstance(raw_accounts, str):
            # Accept comma or newline separated account ids
            tokens = [
                token.strip()
                for token in raw_accounts.replace("\n", ",").split(",")
                if token.strip()
            ]
            ad_accounts = tokens or None
        elif isinstance(raw_accounts, (list, tuple, set)):
            ad_accounts = [
                str(value).strip()
                for value in raw_accounts
                if str(value).strip()
            ] or None

    await _execute_job(
        job_id="rules::hourly_new_ad_scan",
        coro=RuleEngineService.scan_new_ad_bindings(ad_accounts=ad_accounts),
        metadata=config,
    )


_job_handlers = {
    "rules::daily_evaluation": _scheduled_rule_execution,
    "rules::daily_auto_unbind": _scheduled_auto_unbind,
    "rules::hourly_new_ad_scan": _scheduled_scan_new_ads,
}


async def _execute_job(
    *, job_id: str, coro: Awaitable[Any], metadata: dict[str, Any] | None = None
) -> None:
    start_time = datetime.utcnow()
    error: Exception | None = None
    try:
        await coro
    except Exception as exc:  # noqa: BLE001
        error = exc
        logger.exception("Rule scheduler job %s failed", job_id)
        raise
    finally:
        finished_at = datetime.utcnow()
        latency_ms = (finished_at - start_time).total_seconds() * 1000
        metrics = _job_metrics.setdefault(job_id, JobMetrics())
        metrics.metadata = metadata or {}
        metrics.update(finished_at=finished_at, latency_ms=latency_ms, error=error)


def _serialize_job(job: Job) -> dict[str, Any]:
    metrics = _job_metrics.get(job.id, JobMetrics())
    config = _job_configs.setdefault(job.id, SchedulerJobConfig())

    if config.is_paused or job.next_run_time is None:
        status = "paused"
    elif metrics.last_status == "error":
        status = "error"
    else:
        status = "running"

    return {
        "id": job.id,
        "name": _JOB_DISPLAY_NAMES.get(job.id, job.id),
        "cron": str(job.trigger),
        "status": status,
        "next_run_at": job.next_run_time,
        "last_run_at": metrics.last_run_at,
        "average_latency_ms": metrics.average_latency_ms,
        "max_latency_ms": metrics.max_latency_ms or None,
        "last_error": metrics.last_error if status == "error" else None,
        "metadata": config.metadata,
    }


async def start_rule_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 300})
    paused_jobs: list[str] = []
    for job_id, handler in _job_handlers.items():
        config = _job_configs.setdefault(job_id, SchedulerJobConfig())
        if not config.cron_kwargs:
            logger.warning("Skip scheduling job %s due to missing cron config", job_id)
            continue

        cron_kwargs = dict(config.cron_kwargs)
        timezone_arg = cron_kwargs.pop("timezone", None)
        trigger = CronTrigger(timezone=timezone_arg, **cron_kwargs)
        job = _scheduler.add_job(
            handler,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs={"config": config.metadata.copy()},
        )
        if config.is_paused:
            paused_jobs.append(job_id)

    _scheduler.start()
    for job_id in paused_jobs:
        try:
            _scheduler.pause_job(job_id)
        except JobLookupError:
            logger.warning("Failed to restore paused state for job %s", job_id)

    logger.info(
        "Rule scheduler started with jobs: %s",
        [job.id for job in _scheduler.get_jobs()],
    )
    return _scheduler


async def stop_rule_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Rule scheduler stopped")
    _scheduler = None


def get_scheduler_tasks() -> list[dict[str, Any]]:
    if _scheduler is None:
        return []

    return [_serialize_job(job) for job in _scheduler.get_jobs()]


def update_scheduler_task(
    task_id: str,
    *,
    cron_expression: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _scheduler is None:
        raise ValueError("Scheduler is not running")

    job = _scheduler.get_job(task_id)
    if job is None:
        raise ValueError(f"Scheduler task {task_id} not found")

    config = _job_configs.setdefault(task_id, SchedulerJobConfig())
    state_changed = False

    if cron_expression is not None:
        cron_kwargs = _parse_cron_expression(cron_expression)

        existing_timezone = getattr(job.trigger, "timezone", None)
        timezone_arg = cron_kwargs.get("timezone", existing_timezone)
        trigger_kwargs = {k: v for k, v in cron_kwargs.items() if k != "timezone"}
        trigger = CronTrigger(timezone=timezone_arg, **trigger_kwargs)

        job = _scheduler.reschedule_job(task_id, trigger=trigger)
        config.cron_kwargs = cron_kwargs
        if config.is_paused:
            _scheduler.pause_job(task_id)
        state_changed = True

    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be an object/dict")
        config.metadata = metadata
        _scheduler.modify_job(task_id, kwargs={"config": metadata.copy()})
        metrics = _job_metrics.setdefault(task_id, JobMetrics())
        metrics.metadata = metadata
        state_changed = True

    job = _scheduler.get_job(task_id)
    if job is None:
        raise ValueError(f"Scheduler task {task_id} not found")

    if state_changed:
        _persist_configs()
    return _serialize_job(job)


def pause_scheduler_task(task_id: str) -> None:
    if _scheduler is None:
        raise ValueError("Scheduler is not running")
    try:
        _scheduler.pause_job(task_id)
        logger.info("Paused scheduler task %s", task_id)
    except JobLookupError as exc:
        raise ValueError(f"Scheduler task {task_id} not found") from exc
    config = _job_configs.setdefault(task_id, SchedulerJobConfig())
    if not config.is_paused:
        config.is_paused = True
        _persist_configs()


def resume_scheduler_task(task_id: str) -> None:
    if _scheduler is None:
        raise ValueError("Scheduler is not running")
    try:
        _scheduler.resume_job(task_id)
        logger.info("Resumed scheduler task %s", task_id)
    except JobLookupError as exc:
        raise ValueError(f"Scheduler task {task_id} not found") from exc
    config = _job_configs.setdefault(task_id, SchedulerJobConfig())
    if config.is_paused:
        config.is_paused = False
        _persist_configs()


async def run_scheduler_task_now(task_id: str) -> None:
    if _scheduler is None:
        raise ValueError("Scheduler is not running")
    job = _scheduler.get_job(task_id)
    if job is None:
        raise ValueError(f"Scheduler task {task_id} not found")

    await job.func(*job.args, **job.kwargs)
