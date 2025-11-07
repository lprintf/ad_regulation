"""
Rules API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.models.responses import SuccessResponse
from api.models.rules import (
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleDefinitionCreate,
    RuleDefinitionResponse,
    RuleDefinitionUpdate,
    RuleExecutionListResponse,
    RuleExecutionLogResponse,
    RuleExecutionRequest,
    RuleStatus,
    SchedulerTaskResponse,
    SchedulerTaskUpdateRequest,
)
from api.services.rule_engine_service import RuleEngineService
from api.services.rule_scheduler import (
    get_scheduler_tasks,
    pause_scheduler_task,
    resume_scheduler_task,
    run_scheduler_task_now,
    update_scheduler_task,
)
from api.services.insights_sync_scheduler import (
    INSIGHTS_SCHEDULER_TASK_ID,
    get_insights_scheduler_task,
    pause_insights_scheduler_task,
    resume_insights_scheduler_task,
    run_insights_scheduler_task_now,
    update_insights_scheduler_task,
)

router = APIRouter(prefix="/rules", tags=["Rules"])


def _handle_value_error(exc: ValueError) -> None:
    message = str(exc)
    status_code = (
        status.HTTP_404_NOT_FOUND
        if "not found" in message.lower()
        else status.HTTP_400_BAD_REQUEST
    )
    raise HTTPException(status_code=status_code, detail=message)


@router.post(
    "/definitions",
    response_model=SuccessResponse[RuleDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_definition(request: RuleDefinitionCreate):
    """Create a new rule definition."""
    try:
        result = await RuleEngineService.create_rule(request)
        return SuccessResponse(data=result, message="Rule definition created")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/definitions",
    response_model=SuccessResponse[list[RuleDefinitionResponse]],
)
async def list_rule_definitions(
    status_filter: RuleStatus | None = Query(
        default=None,
        alias="status",
        description="Optional status filter",
    ),
):
    """List rule definitions."""
    try:
        result = await RuleEngineService.list_rules(status=status_filter)
        return SuccessResponse(data=result, message="Rule definitions retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/definitions/{rule_id}",
    response_model=SuccessResponse[RuleDefinitionResponse],
)
async def get_rule_definition(rule_id: str):
    """Retrieve a single rule definition by id."""
    try:
        result = await RuleEngineService.get_rule(rule_id)
        return SuccessResponse(data=result, message="Rule definition retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.patch(
    "/definitions/{rule_id}",
    response_model=SuccessResponse[RuleDefinitionResponse],
)
async def update_rule_definition(rule_id: str, request: RuleDefinitionUpdate):
    """Update a rule definition."""
    try:
        result = await RuleEngineService.update_rule(rule_id, request)
        return SuccessResponse(data=result, message="Rule definition updated")
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/bindings",
    response_model=SuccessResponse[RuleBindingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_binding(request: RuleBindingCreate):
    """Bind a rule to a specific entity."""
    try:
        result = await RuleEngineService.create_binding(request)
        return SuccessResponse(data=result, message="Rule binding created")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/bindings",
    response_model=SuccessResponse[list[RuleBindingResponse]],
)
async def list_rule_bindings(
    rule_id: str | None = Query(default=None, description="Filter by rule id"),
    entity_id: str | None = Query(default=None, description="Filter by entity id"),
    active_only: bool = Query(
        default=False, description="Only return active bindings"
    ),
):
    """List rule bindings."""
    try:
        result = await RuleEngineService.list_bindings(
            rule_id=rule_id, entity_id=entity_id, active_only=active_only
        )
        return SuccessResponse(data=result, message="Rule bindings retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.patch(
    "/bindings/{binding_id}",
    response_model=SuccessResponse[RuleBindingResponse],
)
async def update_rule_binding(binding_id: str, request: RuleBindingUpdate):
    """Update rule binding metadata or status."""
    try:
        result = await RuleEngineService.update_binding(binding_id, request)
        return SuccessResponse(data=result, message="Rule binding updated")
    except ValueError as exc:
        _handle_value_error(exc)


@router.delete(
    "/bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rule_binding(binding_id: str):
    """Delete or unbind a rule from an entity."""
    try:
        await RuleEngineService.delete_binding(binding_id)
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/execute",
    response_model=SuccessResponse[RuleExecutionLogResponse],
)
async def execute_rule(request: RuleExecutionRequest):
    """Manually trigger rule execution."""
    try:
        result = await RuleEngineService.execute_rule(request)
        return SuccessResponse(data=result, message="Rule execution completed")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/executions",
    response_model=SuccessResponse[RuleExecutionListResponse],
)
async def list_rule_executions(
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
):
    """List recent rule execution logs."""
    try:
        result = await RuleEngineService.list_executions(limit=limit)
        return SuccessResponse(data=result, message="Rule executions retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/scheduler/tasks",
    response_model=SuccessResponse[list[SchedulerTaskResponse]],
)
async def list_scheduler_tasks():
    """List APScheduler tasks registered for rule engine and insights sync."""
    tasks = get_scheduler_tasks()
    tasks.append(get_insights_scheduler_task())
    return SuccessResponse(data=tasks, message="Scheduler tasks retrieved")


@router.patch(
    "/scheduler/tasks/{task_id}",
    response_model=SuccessResponse[SchedulerTaskResponse],
)
async def update_scheduler(task_id: str, request: SchedulerTaskUpdateRequest):
    """Update scheduler task cron expression or metadata."""
    try:
        if task_id == INSIGHTS_SCHEDULER_TASK_ID:
            task = update_insights_scheduler_task(
                cron_expression=request.cron,
                metadata=request.metadata,
            )
        else:
            task = update_scheduler_task(
                task_id,
                cron_expression=request.cron,
                metadata=request.metadata,
            )
        return SuccessResponse(
            data=task,
            message="Scheduler task updated",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/scheduler/tasks/{task_id}/pause",
    response_model=SuccessResponse[dict[str, str]],
)
async def pause_scheduler(task_id: str):
    """Pause a scheduler task."""
    try:
        if task_id == INSIGHTS_SCHEDULER_TASK_ID:
            pause_insights_scheduler_task()
        else:
            pause_scheduler_task(task_id)
        return SuccessResponse(
            data={"task_id": task_id, "status": "paused"},
            message="Scheduler task paused",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/scheduler/tasks/{task_id}/resume",
    response_model=SuccessResponse[dict[str, str]],
)
async def resume_scheduler(task_id: str):
    """Resume a scheduler task."""
    try:
        if task_id == INSIGHTS_SCHEDULER_TASK_ID:
            resume_insights_scheduler_task()
        else:
            resume_scheduler_task(task_id)
        return SuccessResponse(
            data={"task_id": task_id, "status": "running"},
            message="Scheduler task resumed",
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/scheduler/tasks/{task_id}/run",
    response_model=SuccessResponse[dict[str, str]],
)
async def run_scheduler_now(task_id: str):
    """Trigger a scheduler task immediately."""
    try:
        if task_id == INSIGHTS_SCHEDULER_TASK_ID:
            await run_insights_scheduler_task_now()
        else:
            await run_scheduler_task_now(task_id)
        return SuccessResponse(
            data={"task_id": task_id, "status": "triggered"},
            message="Scheduler task executed",
        )
    except ValueError as exc:
        _handle_value_error(exc)
