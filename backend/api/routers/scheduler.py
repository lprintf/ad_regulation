"""
Scheduler management endpoints.

Consolidates rule, insights, and realtime cache scheduler controls under a single namespace-aware API.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status

from api.models.responses import SuccessResponse
from api.models.scheduler import (
    SchedulerNamespace,
    SchedulerTaskResponse,
    SchedulerTaskUpdateRequest,
)
from api.services.insights_sync_scheduler import (
    INSIGHTS_SCHEDULER_TASK_ID,
    get_insights_scheduler_task,
    pause_insights_scheduler_task,
    resume_insights_scheduler_task,
    run_insights_scheduler_task_now,
    update_insights_scheduler_task,
)
from api.services.realtime_cache_scheduler import (
    JOB_ID as REALTIME_CACHE_JOB_ID,
    get_realtime_cache_scheduler_task,
    pause_realtime_cache_scheduler_task,
    resume_realtime_cache_scheduler_task,
    run_realtime_cache_scheduler_task_now,
    update_realtime_cache_scheduler_task,
)
from api.services.rule_scheduler import (
    get_scheduler_tasks as get_rule_scheduler_tasks,
    pause_scheduler_task as pause_rule_scheduler_task,
    resume_scheduler_task as resume_rule_scheduler_task,
    run_scheduler_task_now as run_rule_scheduler_task_now,
    update_scheduler_task as update_rule_scheduler_task,
)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


def _handle_value_error(exc: ValueError) -> None:
    message = str(exc)
    status_code = (
        status.HTTP_404_NOT_FOUND
        if "not found" in message.lower()
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=message)


def _with_namespace(
    namespace: SchedulerNamespace, payload: dict[str, object]
) -> SchedulerTaskResponse:
    return SchedulerTaskResponse(namespace=namespace, **payload)


def _ensure_insights_task(task_id: str) -> None:
    if task_id != INSIGHTS_SCHEDULER_TASK_ID:
        raise ValueError(f"Insights scheduler task {task_id} not found")


def _ensure_realtime_cache_task(task_id: str) -> None:
    if task_id != REALTIME_CACHE_JOB_ID:
        raise ValueError(f"Realtime cache scheduler task {task_id} not found")


@router.get(
    "/tasks",
    response_model=SuccessResponse[list[SchedulerTaskResponse]],
)
async def list_scheduler_tasks():
    """List APScheduler tasks grouped by namespace."""
    tasks = [
        _with_namespace(SchedulerNamespace.RULES, task)
        for task in get_rule_scheduler_tasks()
    ]
    tasks.append(
        _with_namespace(
            SchedulerNamespace.INSIGHTS,
            get_insights_scheduler_task(),
        )
    )
    tasks.append(
        _with_namespace(
            SchedulerNamespace.REALTIME_CACHE,
            get_realtime_cache_scheduler_task(),
        )
    )
    return SuccessResponse(data=tasks, message="Scheduler tasks retrieved")


@router.patch(
    "/tasks/{namespace}/{task_id}",
    response_model=SuccessResponse[SchedulerTaskResponse],
)
async def update_scheduler_task(
    namespace: SchedulerNamespace,
    task_id: str = Path(..., description="Scheduler job identifier"),
    request: SchedulerTaskUpdateRequest | None = None,
):
    """Update cron expression or metadata for a scheduler task."""
    try:
        req = request or SchedulerTaskUpdateRequest()
        if namespace is SchedulerNamespace.RULES:
            task = update_rule_scheduler_task(
                task_id,
                cron_expression=req.cron,
                metadata=req.metadata,
            )
        elif namespace is SchedulerNamespace.INSIGHTS:
            _ensure_insights_task(task_id)
            task = update_insights_scheduler_task(
                cron_expression=req.cron,
                metadata=req.metadata,
            )
        else:  # REALTIME_CACHE
            _ensure_realtime_cache_task(task_id)
            task = update_realtime_cache_scheduler_task(
                cron_expression=req.cron,
                metadata=req.metadata,
            )
        return SuccessResponse(
            data=_with_namespace(namespace, task),
            message="Scheduler task updated",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/tasks/{namespace}/{task_id}/pause",
    response_model=SuccessResponse[dict[str, str]],
)
async def pause_scheduler_task(
    namespace: SchedulerNamespace,
    task_id: str = Path(..., description="Scheduler job identifier"),
):
    """Pause a scheduler task."""
    try:
        if namespace is SchedulerNamespace.RULES:
            pause_rule_scheduler_task(task_id)
        elif namespace is SchedulerNamespace.INSIGHTS:
            _ensure_insights_task(task_id)
            pause_insights_scheduler_task()
        else:  # REALTIME_CACHE
            _ensure_realtime_cache_task(task_id)
            pause_realtime_cache_scheduler_task()
        return SuccessResponse(
            data={
                "namespace": namespace.value,
                "task_id": task_id,
                "status": "paused",
            },
            message="Scheduler task paused",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/tasks/{namespace}/{task_id}/resume",
    response_model=SuccessResponse[dict[str, str]],
)
async def resume_scheduler_task(
    namespace: SchedulerNamespace,
    task_id: str = Path(..., description="Scheduler job identifier"),
):
    """Resume a scheduler task."""
    try:
        if namespace is SchedulerNamespace.RULES:
            resume_rule_scheduler_task(task_id)
        elif namespace is SchedulerNamespace.INSIGHTS:
            _ensure_insights_task(task_id)
            resume_insights_scheduler_task()
        else:  # REALTIME_CACHE
            _ensure_realtime_cache_task(task_id)
            resume_realtime_cache_scheduler_task()
        return SuccessResponse(
            data={
                "namespace": namespace.value,
                "task_id": task_id,
                "status": "running",
            },
            message="Scheduler task resumed",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/tasks/{namespace}/{task_id}/run",
    response_model=SuccessResponse[dict[str, str]],
)
async def run_scheduler_task(
    namespace: SchedulerNamespace,
    task_id: str = Path(..., description="Scheduler job identifier"),
):
    """Trigger a scheduler task immediately."""
    try:
        if namespace is SchedulerNamespace.RULES:
            await run_rule_scheduler_task_now(task_id)
        elif namespace is SchedulerNamespace.INSIGHTS:
            _ensure_insights_task(task_id)
            await run_insights_scheduler_task_now()
        else:  # REALTIME_CACHE
            _ensure_realtime_cache_task(task_id)
            await run_realtime_cache_scheduler_task_now()
        return SuccessResponse(
            data={
                "namespace": namespace.value,
                "task_id": task_id,
                "status": "triggered",
            },
            message="Scheduler task executed",
        )
    except ValueError as exc:
        _handle_value_error(exc)

