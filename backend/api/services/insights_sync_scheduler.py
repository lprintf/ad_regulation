"""
APScheduler integration for historical insights sync tasks.
Provides scheduler introspection utilities for the dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from apscheduler.job import Job
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.insights_sync_service import InsightsSyncService
from api.services.scheduler_state_store import (
    INSIGHTS_SCHEDULER_NAMESPACE,
    load_namespace,
    save_namespace,
)

logger = logging.getLogger(__name__)


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


_scheduler: AsyncIOScheduler | None = None
JOB_ID = "insights::daily_backfill"
INSIGHTS_SCHEDULER_TASK_ID = JOB_ID
_JOB_DISPLAY_NAME = "每日洞察补采"
_job_metrics: Dict[str, JobMetrics] = {}
_job_configs: Dict[str, SchedulerJobConfig] = {
    JOB_ID: SchedulerJobConfig(cron_kwargs={"hour": "11", "minute": "0"})
}


def _serialize_config_for_store() -> Dict[str, Any]:
    config = _job_configs[JOB_ID]
    return {
        JOB_ID: {
            "cron_kwargs": dict(config.cron_kwargs),
            "metadata": dict(config.metadata),
            "is_paused": bool(config.is_paused),
        }
    }


def _persist_config() -> None:
    save_namespace(INSIGHTS_SCHEDULER_NAMESPACE, _serialize_config_for_store())


def _hydrate_config_from_store() -> None:
    stored = load_namespace(INSIGHTS_SCHEDULER_NAMESPACE).get(JOB_ID)
    if not isinstance(stored, dict):
        return

    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())

    cron_kwargs = stored.get("cron_kwargs")
    if isinstance(cron_kwargs, dict):
        config.cron_kwargs = dict(cron_kwargs)

    metadata = stored.get("metadata")
    if isinstance(metadata, dict):
        config.metadata = dict(metadata)

    is_paused = stored.get("is_paused")
    if isinstance(is_paused, bool):
        config.is_paused = is_paused

    if config.metadata:
        metrics = _job_metrics.setdefault(JOB_ID, JobMetrics())
        metrics.metadata = dict(config.metadata)


_hydrate_config_from_store()


async def _run_daily_sync(config: dict[str, Any] | None = None):
    metrics = _job_metrics.setdefault(JOB_ID, JobMetrics())
    if isinstance(config, dict):
        metrics.metadata = config

    started_at = datetime.utcnow()
    error: Exception | None = None
    try:
        await InsightsSyncService.run_daily_schedule()
    except Exception as exc:  # pragma: no cover - scheduler safety net
        error = exc
        logger.exception("Insights daily sync job failed: %s", exc)
        raise
    finally:
        finished_at = datetime.utcnow()
        latency_ms = (finished_at - started_at).total_seconds() * 1000
        metrics.update(finished_at=finished_at, latency_ms=latency_ms, error=error)


def _serialize_job(job: Job | None) -> dict[str, Any]:
    metrics = _job_metrics.get(JOB_ID, JobMetrics())
    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())

    if config.is_paused or (job and job.next_run_time is None):
        status = "paused"
    elif job and job.next_run_time is not None:
        status = "running" if metrics.last_status != "error" else "error"
    elif metrics.last_status == "error":
        status = "error"
    else:
        status = "paused"

    cron_repr = str(job.trigger) if job else config.cron_expression()

    return {
        "id": JOB_ID,
        "name": _JOB_DISPLAY_NAME,
        "cron": cron_repr,
        "status": status,
        "next_run_at": job.next_run_time if job else None,
        "last_run_at": metrics.last_run_at,
        "average_latency_ms": metrics.average_latency_ms,
        "max_latency_ms": metrics.max_latency_ms or None,
        "last_error": metrics.last_error if status == "error" else None,
        "metadata": config.metadata,
    }


async def start_insights_sync_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 600})
    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())

    cron_kwargs = dict(config.cron_kwargs)
    trigger_kwargs = {k: v for k, v in cron_kwargs.items() if k != "timezone"}
    trigger = CronTrigger(timezone=cron_kwargs.get("timezone"), **trigger_kwargs)
    _scheduler.add_job(
        _run_daily_sync,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        kwargs={"config": config.metadata.copy()},
    )
    _scheduler.start()
    if config.is_paused:
        try:
            _scheduler.pause_job(JOB_ID)
        except JobLookupError:
            logger.warning("Failed to restore paused state for job %s", JOB_ID)
    logger.info("Insights sync scheduler started with job %s", JOB_ID)
    return _scheduler


async def stop_insights_sync_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Insights sync scheduler stopped")
    _scheduler = None


def get_insights_scheduler_task() -> dict[str, Any]:
    job = _scheduler.get_job(JOB_ID) if _scheduler else None
    return _serialize_job(job)


def update_insights_scheduler_task(
    *, cron_expression: str | None = None, metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    if _scheduler is None:
        raise ValueError("Insights scheduler is not running")

    job = _scheduler.get_job(JOB_ID)
    if job is None:
        raise ValueError("Insights scheduler task not found")

    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())
    state_changed = False

    if cron_expression is not None:
        cron_kwargs = _parse_cron_expression(cron_expression)
        trigger_kwargs = {k: v for k, v in cron_kwargs.items() if k != "timezone"}
        timezone_arg = cron_kwargs.get("timezone")
        trigger = CronTrigger(timezone=timezone_arg, **trigger_kwargs)
        job = _scheduler.reschedule_job(JOB_ID, trigger=trigger)
        config.cron_kwargs = cron_kwargs
        if config.is_paused:
            _scheduler.pause_job(JOB_ID)
        state_changed = True

    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be an object/dict")
        config.metadata = metadata
        _scheduler.modify_job(JOB_ID, kwargs={"config": metadata.copy()})
        metrics = _job_metrics.setdefault(JOB_ID, JobMetrics())
        metrics.metadata = metadata
        state_changed = True

    if state_changed:
        _persist_config()
    return _serialize_job(job)


def pause_insights_scheduler_task() -> None:
    if _scheduler is None:
        raise ValueError("Insights scheduler is not running")
    try:
        _scheduler.pause_job(JOB_ID)
        logger.info("Paused insights scheduler task %s", JOB_ID)
    except JobLookupError as exc:
        raise ValueError("Insights scheduler task not found") from exc
    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())
    if not config.is_paused:
        config.is_paused = True
        _persist_config()


def resume_insights_scheduler_task() -> None:
    if _scheduler is None:
        raise ValueError("Insights scheduler is not running")
    try:
        _scheduler.resume_job(JOB_ID)
        logger.info("Resumed insights scheduler task %s", JOB_ID)
    except JobLookupError as exc:
        raise ValueError("Insights scheduler task not found") from exc
    config = _job_configs.setdefault(JOB_ID, SchedulerJobConfig())
    if config.is_paused:
        config.is_paused = False
        _persist_config()


async def run_insights_scheduler_task_now() -> None:
    """
    Manually trigger the insights sync task immediately.
    Runs in the background to avoid blocking the HTTP response.
    """
    if _scheduler is None:
        raise ValueError("Insights scheduler is not running")
    job = _scheduler.get_job(JOB_ID)
    if job is None:
        raise ValueError("Insights scheduler task not found")

    # Import asyncio for background execution
    import asyncio

    # Run in background to avoid blocking HTTP response
    asyncio.create_task(job.func(*job.args, **job.kwargs))
    logger.info("Insights sync task triggered manually (running in background)")
