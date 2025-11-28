"""
Rules API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from api.models.responses import SuccessResponse
from api.models.rules import (
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleDefinitionClone,
    RuleDefinitionCreate,
    RuleDefinitionResponse,
    RuleDefinitionUpdate,
    RuleExecutionListResponse,
    RuleExecutionLogResponse,
    RuleExecutionRequest,
    RuleStatus,
)
from api.services.rule_engine_service import RuleEngineService

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
    "/definitions/{rule_id}/clone",
    response_model=SuccessResponse[RuleDefinitionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def clone_rule_definition(rule_id: str, request: RuleDefinitionClone):
    """Clone an existing rule with modified parameters and version."""
    try:
        result = await RuleEngineService.clone_rule(rule_id, request)
        return SuccessResponse(data=result, message="Rule definition cloned")
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


@router.get(
    "/bindings/{binding_id}/executions",
    response_model=SuccessResponse[RuleExecutionListResponse],
)
async def list_binding_executions(
    binding_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
):
    """List execution history for a specific binding."""
    try:
        result = await RuleEngineService.list_binding_executions(binding_id, limit=limit)
        return SuccessResponse(data=result, message="Binding execution history retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


async def _execute_rule_background(request: RuleExecutionRequest):
    """
    Wrapper for background rule execution with error logging.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting background rule execution for binding_id=%s rule_id=%s",
                   request.binding_id, request.rule_id)
        result = await RuleEngineService.execute_rule(request)
        logger.info("Background rule execution completed successfully: %s", result.id)
    except Exception as exc:
        logger.exception(
            "Background rule execution failed for binding_id=%s rule_id=%s: %s",
            request.binding_id,
            request.rule_id,
            exc
        )


@router.post(
    "/execute",
    response_model=SuccessResponse[dict],
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_rule(request: RuleExecutionRequest, background_tasks: BackgroundTasks):
    """
    Manually trigger rule execution in background.
    Returns immediately without waiting for execution to complete.
    Check execution history for results.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info("[ENDPOINT] Received execute request for binding_id=%s rule_id=%s",
                   request.binding_id, request.rule_id)

        # Execute rule in background with error logging wrapper
        background_tasks.add_task(_execute_rule_background, request)

        logger.info("[ENDPOINT] Background task added successfully")

        return SuccessResponse(
            data={
                "status": "accepted",
                "message": "Rule execution started in background",
                "binding_id": request.binding_id,
                "rule_id": request.rule_id,
            },
            message="Rule execution task submitted"
        )
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

