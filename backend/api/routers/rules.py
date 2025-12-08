"""
Rules API endpoints.

Refactored to use registry-based rules instead of database-stored code.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status

from api.models.responses import SuccessResponse
from api.models.rules import (
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleConfigArchive,
    RuleConfigClone,
    RuleConfigCreate,
    RuleConfigResponse,
    RuleConfigUpdate,
    RuleExecutionListResponse,
    RuleExecutionRequest,
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


# ===== Rule Discovery (Read-only from Registry) =====


@router.get(
    "/available",
    response_model=SuccessResponse[list[dict]],
)
async def list_available_rules():
    """
    List all available rules from the registry.

    Rules are defined in Python code (rules/builtin/) and registered at startup.
    This endpoint returns metadata only (name, description, parameters_schema).
    """
    result = RuleEngineService.list_available_rules()
    return SuccessResponse(data=result, message="Available rules retrieved")


@router.get(
    "/available/{rule_name}",
    response_model=SuccessResponse[dict],
)
async def get_rule_info(rule_name: str):
    """Get metadata for a specific rule by name."""
    result = RuleEngineService.get_rule_info(rule_name)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_name}' not found"
        )
    return SuccessResponse(data=result, message="Rule info retrieved")


# ===== Rule Configs (Clone rules with modified parameters) =====


@router.post(
    "/configs",
    response_model=SuccessResponse[RuleConfigResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_config(
    request: RuleConfigCreate,
    x_user_id: str = Header(..., alias="X-User-Id", description="User ID from auth header"),
):
    """
    Create a new rule configuration (clone a rule with modified default parameters).
    
    命名规则: {base_rule}:{user_id}:{suffix}
    - evaluation_date 参数不可覆盖，永远为空
    - User ID 从 X-User-Id header 获取
    """
    try:
        # Set created_by from X-User-Id header
        request.created_by = x_user_id
        result = await RuleEngineService.create_config(request)
        return SuccessResponse(data=result, message="Rule config created")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/configs",
    response_model=SuccessResponse[list[RuleConfigResponse]],
)
async def list_rule_configs(
    base_rule: str | None = Query(default=None, description="Filter by base rule name"),
    source: str | None = Query(default=None, description="Filter by source: 'system' or 'user'"),
    include_archived: bool = Query(default=False, description="Include archived configs"),
):
    """
    List all rule configurations (unified model for system and user rules).
    
    - System rules: template_id=null, source='system'
    - User rules: template_id=cloned_from_id, source='user:{user_id}'
    """
    try:
        result = await RuleEngineService.list_configs(
            base_rule=base_rule,
            source=source,
            include_archived=include_archived,
        )
        return SuccessResponse(data=result, message="Rule configs retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.get(
    "/configs/{config_id}",
    response_model=SuccessResponse[RuleConfigResponse],
)
async def get_rule_config(config_id: str):
    """Get a specific rule configuration by ID."""
    try:
        result = await RuleEngineService.get_config(config_id)
        return SuccessResponse(data=result, message="Rule config retrieved")
    except ValueError as exc:
        _handle_value_error(exc)


@router.patch(
    "/configs/{config_id}",
    response_model=SuccessResponse[RuleConfigResponse],
)
async def update_rule_config(config_id: str, request: RuleConfigUpdate):
    """
    Update a rule configuration.

    Modifying parameter_overrides will automatically increment the version.
    """
    try:
        result = await RuleEngineService.update_config(config_id, request)
        return SuccessResponse(data=result, message="Rule config updated")
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/configs/{config_id}/clone",
    response_model=SuccessResponse[RuleConfigResponse],
    status_code=status.HTTP_201_CREATED,
)
async def clone_rule_config(config_id: str, request: RuleConfigClone):
    """
    Clone an existing rule configuration with additional parameter modifications.

    The new config will have version 1.0.0 and merge the source's parameter
    overrides with the provided overrides.
    """
    try:
        result = await RuleEngineService.clone_config(config_id, request)
        return SuccessResponse(data=result, message="Rule config cloned")
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/configs/{config_id}/archive",
    response_model=SuccessResponse[RuleConfigResponse],
)
async def archive_rule_config(config_id: str, request: RuleConfigArchive | None = None):
    """
    Archive a rule configuration (soft delete).
    
    Rules cannot be deleted, only archived. System rules cannot be archived.
    Archived rules are hidden by default but can be retrieved with include_archived=true.
    """
    try:
        result = await RuleEngineService.archive_config(config_id, request)
        return SuccessResponse(data=result, message="Rule config archived")
    except ValueError as exc:
        _handle_value_error(exc)


@router.delete(
    "/configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_rule_config(config_id: str):
    """
    Delete a rule configuration.
    
    Note: This actually archives the config instead of deleting it.
    Rules cannot be permanently deleted.
    """
    try:
        await RuleEngineService.delete_config(config_id)
    except ValueError as exc:
        _handle_value_error(exc)


@router.post(
    "/sync-system-rules",
    response_model=SuccessResponse[dict],
)
async def sync_system_rules():
    """
    Sync system rules from code registry to database.
    
    This creates or updates RuleConfigDocument records for each registered rule
    with source='system' and template_id=null.
    """
    try:
        count = await RuleEngineService.sync_system_rules()
        return SuccessResponse(
            data={"synced_count": count},
            message=f"Synced {count} system rules to database"
        )
    except ValueError as exc:
        _handle_value_error(exc)


# ===== Bindings Management =====


@router.post(
    "/bindings",
    response_model=SuccessResponse[RuleBindingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_binding(request: RuleBindingCreate):
    """
    Bind a rule to a specific entity.

    The rule_id should be the rule name (e.g., "demo_spend_guard", "ml_auto_stop").
    """
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
    rule_name: str | None = Query(default=None, description="Filter by rule name"),
    entity_id: str | None = Query(default=None, description="Filter by entity id"),
    active_only: bool = Query(
        default=False, description="Only return active bindings"
    ),
):
    """List rule bindings."""
    try:
        result = await RuleEngineService.list_bindings(
            rule_name=rule_name, entity_id=entity_id, active_only=active_only
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


# ===== Execution =====


async def _execute_rule_background(request: RuleExecutionRequest):
    """Wrapper for background rule execution with error logging."""
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(
            "Starting background rule execution for binding_id=%s rule_id=%s",
            request.binding_id,
            request.rule_id,
        )
        result = await RuleEngineService.execute_rule(request)
        logger.info("Background rule execution completed successfully: %s", result.id)
    except Exception as exc:
        logger.exception(
            "Background rule execution failed for binding_id=%s rule_id=%s: %s",
            request.binding_id,
            request.rule_id,
            exc,
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

    Either binding_id or rule_id (rule name) must be provided.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info(
            "[ENDPOINT] Received execute request for binding_id=%s rule_id=%s",
            request.binding_id,
            request.rule_id,
        )

        background_tasks.add_task(_execute_rule_background, request)

        logger.info("[ENDPOINT] Background task added successfully")

        return SuccessResponse(
            data={
                "status": "accepted",
                "message": "Rule execution started in background",
                "binding_id": request.binding_id,
                "rule_id": request.rule_id,
            },
            message="Rule execution task submitted",
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
