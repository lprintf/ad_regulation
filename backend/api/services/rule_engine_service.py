"""
Service layer implementation for the rule engine domain.
Provides CRUD, binding management, execution, and scheduler entry points.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from bson import ObjectId

from api.models.rules import (
    BindingEntityType,
    BindingSource,
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleDefinitionCreate,
    RuleDefinitionResponse,
    RuleDefinitionUpdate,
    RuleExecutionListResponse,
    RuleExecutionLogResponse,
    RuleExecutionRequest,
    RuleExecutionStatus,
    RuleStatus,
    RuleTrigger,
)
from api.services.rule_context_service import RuleContextService
from utils.db import (
    RuleBindingDocument,
    RuleDefinitionDocument,
    RuleExecutionLogDocument,
)
from utils.rule_sandbox import (
    RuleExecutionError,
    RuleValidationError,
    execute_rule_script,
)

logger = logging.getLogger(__name__)


def _to_object_id(identifier: str) -> ObjectId:
    if not ObjectId.is_valid(identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    return ObjectId(identifier)


def _serialize_rule_definition(doc: RuleDefinitionDocument) -> RuleDefinitionResponse:
    return RuleDefinitionResponse(
        id=str(doc.id),
        name=doc.name,
        description=doc.description,
        version=doc.version,
        code=doc.code,
        parameters_schema=doc.parameters_schema,
        tags=doc.tags,
        status=RuleStatus(doc.status),
        is_active=doc.is_active,
        created_by=doc.created_by,
        updated_by=doc.updated_by,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        published_at=doc.published_at,
    )


def _serialize_binding(doc: RuleBindingDocument) -> RuleBindingResponse:
    return RuleBindingResponse(
        id=str(doc.id),
        rule_id=doc.rule_id,
        rule_name=doc.rule_name,
        entity_type=BindingEntityType(doc.entity_type),
        entity_id=doc.entity_id,
        source=BindingSource(doc.source),
        metadata=doc.metadata,
        is_active=doc.is_active,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        last_executed_at=doc.last_executed_at,
    )


def _serialize_execution(doc: RuleExecutionLogDocument) -> RuleExecutionLogResponse:
    binding_id: Optional[str] = None
    if doc.binding is not None:
        try:
            binding_id = str(doc.binding.id)  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback when lazy link not fetched yet
            binding_id = str(doc.binding)  # type: ignore

    return RuleExecutionLogResponse(
        id=str(doc.id),
        rule_id=doc.rule_id,
        rule_name=doc.rule_name,
        rule_version=doc.rule_version,
        binding_id=binding_id,
        entity_type=doc.entity_type,
        entity_id=doc.entity_id,
        trigger=RuleTrigger(doc.trigger),
        scheduled_run_time=doc.scheduled_run_time,
        actual_start_time=doc.actual_start_time,
        completed_at=doc.completed_at,
        status=RuleExecutionStatus(doc.status),
        actions=doc.actions,
        reasons=doc.reasons,
        metrics=doc.metrics,
        context_snapshot=doc.context_snapshot,
        error_message=doc.error_message,
        execution_duration_ms=doc.execution_duration_ms,
    )


class RuleEngineService:
    """Service layer for rule engine functionality."""

    @staticmethod
    async def create_rule(data: RuleDefinitionCreate) -> RuleDefinitionResponse:
        existing = await RuleDefinitionDocument.find_one(
            RuleDefinitionDocument.name == data.name
        )
        if existing:
            raise ValueError(f"Rule name '{data.name}' already exists")

        now = datetime.utcnow()
        rule_doc = RuleDefinitionDocument(
            name=data.name,
            description=data.description,
            code=data.code,
            parameters_schema=data.parameters_schema,
            tags=data.tags,
            created_by=data.created_by,
            updated_by=data.created_by,
            created_at=now,
            updated_at=now,
        )
        await rule_doc.insert()
        logger.info("Created rule definition '%s'", rule_doc.name)
        return _serialize_rule_definition(rule_doc)

    @staticmethod
    async def list_rules(status: RuleStatus | None = None) -> list[RuleDefinitionResponse]:
        query = {}
        if status:
            query["status"] = status.value
        docs = await RuleDefinitionDocument.find(query).to_list()
        return [_serialize_rule_definition(doc) for doc in docs]

    @staticmethod
    async def get_rule(rule_id: str) -> RuleDefinitionResponse:
        doc = await RuleDefinitionDocument.get(_to_object_id(rule_id))
        if doc is None:
            raise ValueError("Rule not found")
        return _serialize_rule_definition(doc)

    @staticmethod
    async def update_rule(rule_id: str, data: RuleDefinitionUpdate) -> RuleDefinitionResponse:
        doc = await RuleDefinitionDocument.get(_to_object_id(rule_id))
        if doc is None:
            raise ValueError("Rule not found")

        updated = False
        if data.description is not None:
            doc.description = data.description
            updated = True
        if data.code is not None:
            doc.code = data.code
            updated = True
        if data.parameters_schema is not None:
            doc.parameters_schema = data.parameters_schema
            updated = True
        if data.tags is not None:
            doc.tags = data.tags
            updated = True
        if data.status is not None:
            doc.status = data.status.value
            updated = True
        if data.is_active is not None:
            doc.is_active = data.is_active
            updated = True
        if data.version is not None:
            doc.version = data.version
            updated = True
        if data.updated_by is not None:
            doc.updated_by = data.updated_by
            updated = True

        if updated:
            doc.updated_at = datetime.utcnow()
            if doc.status == RuleStatus.PUBLISHED.value and not doc.published_at:
                doc.published_at = doc.updated_at
            await doc.save()
            logger.info("Updated rule definition '%s'", doc.name)

        return _serialize_rule_definition(doc)

    # ===== Binding management =====

    @staticmethod
    async def create_binding(data: RuleBindingCreate) -> RuleBindingResponse:
        rule = await RuleDefinitionDocument.get(_to_object_id(data.rule_id))
        if rule is None:
            raise ValueError("Rule not found for binding")

        existing = await RuleBindingDocument.find_one(
            RuleBindingDocument.rule_name == rule.name,
            RuleBindingDocument.entity_id == data.entity_id,
        )
        if existing:
            raise ValueError("Binding already exists for this rule and entity")

        now = datetime.utcnow()
        binding = RuleBindingDocument(
            rule=rule,
            rule_id=str(rule.id),
            rule_name=rule.name,
            entity_type=data.entity_type.value,
            entity_id=data.entity_id,
            source=data.source.value,
            metadata=data.metadata,
            created_at=now,
            updated_at=now,
        )
        await binding.insert()
        logger.info("Created binding %s for rule '%s'", binding.id, rule.name)
        return _serialize_binding(binding)

    @staticmethod
    async def list_bindings(
        rule_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[RuleBindingResponse]:
        filters: list[Any] = []
        if rule_id:
            rule = await RuleDefinitionDocument.get(_to_object_id(rule_id))
            if rule is None:
                raise ValueError("Rule not found")
            filters.append(RuleBindingDocument.rule_id == str(rule.id))
        if entity_id:
            filters.append(RuleBindingDocument.entity_id == entity_id)
        if active_only:
            filters.append(RuleBindingDocument.is_active == True)  # noqa: E712

        cursor = (
            RuleBindingDocument.find(*filters)
            if filters
            else RuleBindingDocument.find({})
        )
        docs = await cursor.to_list()

        return [_serialize_binding(doc) for doc in docs]

    @staticmethod
    async def update_binding(binding_id: str, data: RuleBindingUpdate) -> RuleBindingResponse:
        binding = await RuleBindingDocument.get(_to_object_id(binding_id))
        if binding is None:
            raise ValueError("Binding not found")

        if data.metadata is not None:
            binding.metadata = data.metadata
        if data.is_active is not None:
            binding.is_active = data.is_active
        binding.updated_at = datetime.utcnow()
        await binding.save()
        logger.info("Updated binding %s", binding_id)
        return _serialize_binding(binding)

    @staticmethod
    async def delete_binding(binding_id: str) -> None:
        binding = await RuleBindingDocument.get(_to_object_id(binding_id))
        if binding is None:
            return
        await binding.delete()
        logger.info("Deleted binding %s", binding_id)

    # ===== Execution =====

    @staticmethod
    async def execute_rule(
        request: RuleExecutionRequest,
        scheduled_run_time: datetime | None = None,
    ) -> RuleExecutionLogResponse:
        if request.binding_id:
            binding = await RuleBindingDocument.get(
                _to_object_id(request.binding_id), fetch_links=True
            )
            if binding is None:
                raise ValueError("Binding not found")
            rule = None
            try:
                rule = await binding.fetch_link(RuleBindingDocument.rule)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to fetch linked rule for binding %s: %s",
                    request.binding_id,
                    exc,
                )

            if rule is None and binding.rule_id:
                try:
                    rule = await RuleDefinitionDocument.get(
                        _to_object_id(binding.rule_id)
                    )
                except ValueError:
                    logger.warning(
                        "Stored rule_id '%s' on binding %s is not a valid ObjectId",
                        binding.rule_id,
                        request.binding_id,
                    )

            if rule is None:
                rule = await RuleDefinitionDocument.find_one(
                    RuleDefinitionDocument.name == binding.rule_name
                )

            if rule is None:
                raise ValueError(
                    f"Rule definition not found for binding {request.binding_id}"
                )
        elif request.rule_id:
            rule = await RuleDefinitionDocument.get(_to_object_id(request.rule_id))
            if rule is None:
                raise ValueError("Rule not found")
            binding = None
        else:
            raise ValueError("Either rule_id or binding_id must be provided")

        if request.context is not None:
            context = request.context
        else:
            try:
                context = await RuleContextService.build_context(binding)
            except Exception as exc:
                logger.warning(
                    "Failed to build context for rule '%s': %s",
                    rule.name,
                    exc,
                )
                context = RuleEngineService._build_default_context(binding)
                context["context_error"] = str(exc)
        params = request.params or {}

        start_time = datetime.utcnow()

        try:
            execution_result = execute_rule_script(rule.code, context, params)
            status = RuleExecutionStatus.SUCCESS
            error_message = None
        except (RuleValidationError, RuleExecutionError) as exc:
            execution_result = {}
            status = RuleExecutionStatus.FAILED
            error_message = str(exc)
            logger.warning(
                "Rule '%s' execution failed: %s", rule.name, error_message, exc_info=True
            )

        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - start_time).total_seconds() * 1000)

        log_doc = RuleExecutionLogDocument(
            rule_name=rule.name,
            rule_id=str(rule.id),
            rule_version=rule.version,
            binding=binding,
            entity_type=binding.entity_type if binding else None,
            entity_id=binding.entity_id if binding else None,
            trigger=request.trigger.value,
            scheduled_run_time=scheduled_run_time,
            actual_start_time=start_time,
            completed_at=completed_at,
            status=status.value,
            actions=execution_result.get("actions", []),
            reasons=execution_result.get("reasons", []),
            metrics=execution_result.get("metrics", {}),
            context_snapshot=context,
            error_message=error_message,
            execution_duration_ms=duration_ms,
        )
        await log_doc.insert()

        if binding and status == RuleExecutionStatus.SUCCESS:
            binding.last_executed_at = completed_at
            binding.updated_at = completed_at
            await binding.save()

        return _serialize_execution(log_doc)

    @staticmethod
    async def list_executions(limit: int = 50) -> RuleExecutionListResponse:
        docs = (
            await RuleExecutionLogDocument.find({})
            .sort(-RuleExecutionLogDocument.actual_start_time)
            .limit(limit)
            .to_list()
        )
        return RuleExecutionListResponse(
            executions=[_serialize_execution(doc) for doc in docs],
            total=len(docs),
        )

    @staticmethod
    async def run_scheduled_evaluations(
        scheduled_run_time: datetime | None = None,
        limit: Optional[int] = None,
    ) -> None:
        bindings = await RuleBindingDocument.find(
            RuleBindingDocument.is_active == True  # noqa: E712
        ).to_list()

        processed = 0
        for binding in bindings:
            if limit is not None and processed >= limit:
                break

            try:
                await RuleEngineService.execute_rule(
                    RuleExecutionRequest(
                        binding_id=str(binding.id),
                        trigger=RuleTrigger.SCHEDULER,
                    ),
                    scheduled_run_time=scheduled_run_time,
                )
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Scheduled evaluation failed for binding %s: %s",
                    binding.id,
                    exc,
                )

    @staticmethod
    async def auto_unbind_stale_bindings(inactive_days: int = 7) -> int:
        cutoff = datetime.utcnow() - timedelta(days=inactive_days)
        bindings = await RuleBindingDocument.find(
            RuleBindingDocument.is_active == True  # noqa: E712
        ).to_list()

        updated_count = 0
        for binding in bindings:
            if binding.last_executed_at and binding.last_executed_at < cutoff:
                binding.is_active = False
                binding.updated_at = datetime.utcnow()
                await binding.save()
                updated_count += 1
                logger.info(
                    "Auto-unbound stale binding %s (rule=%s, entity=%s)",
                    binding.id,
                    binding.rule_name,
                    binding.entity_id,
                )

                await RuleExecutionLogDocument(
                    rule_name=binding.rule_name,
                    rule_id=binding.rule_id,
                    rule_version=None,
                    binding=binding,
                    entity_type=binding.entity_type,
                    entity_id=binding.entity_id,
                    trigger=RuleTrigger.AUTO_UNBIND.value,
                    scheduled_run_time=None,
                    actual_start_time=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    status=RuleExecutionStatus.SUCCESS.value,
                    actions=[
                        {
                            "type": "auto_unbind",
                            "reason": "inactive_binding",
                            "inactive_days": inactive_days,
                        }
                    ],
                    reasons=["Binding inactive for configured window"],
                    metrics={},
                    context_snapshot={"last_executed_at": binding.last_executed_at},
                    error_message=None,
                    execution_duration_ms=0,
                ).insert()

        return updated_count

    @staticmethod
    async def scan_new_ad_bindings(ad_accounts: list[str] | None = None) -> None:
        """
        Placeholder for ad naming parser integration.
        Currently logs execution to create observable heartbeat in execution history.
        """
        now = datetime.utcnow()
        accounts_payload = (
            [account for account in ad_accounts if account]
            if ad_accounts
            else []
        )
        await RuleExecutionLogDocument(
            rule_name="scheduler::scan_new_ads",
            rule_version=None,
            binding=None,
            entity_type=None,
            entity_id=None,
            trigger=RuleTrigger.SCHEDULER.value,
            scheduled_run_time=None,
            actual_start_time=now,
            completed_at=now,
            status=RuleExecutionStatus.SUCCESS.value,
            actions=[],
            reasons=[
                "Scan new ads task executed (no-op placeholder)",
                f"Target accounts: {', '.join(accounts_payload) or 'all'}",
            ],
            metrics={"account_count": len(accounts_payload)},
            context_snapshot={"ad_accounts": accounts_payload},
            error_message=None,
            execution_duration_ms=0,
        ).insert()
        logger.debug(
            "Executed placeholder new ad scan task at %s (accounts=%s)",
            now.isoformat(),
            accounts_payload or "all",
        )

    @staticmethod
    async def ensure_demo_rule_seed() -> None:
        """
        Ensure the demo spend guard rule definition exists.
        """
        rule_name = "demo_spend_guard"
        existing = await RuleDefinitionDocument.find_one(
            RuleDefinitionDocument.name == rule_name
        )
        if existing:
            return

        script_path = Path("rules/scripts/demo_spend_guard.py")
        try:
            code = script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("Demo rule script not found at %s", script_path)
            return

        now = datetime.utcnow()
        doc = RuleDefinitionDocument(
            name=rule_name,
            description="素材测试规则：花费≥3美金时评估CPC/CTR，未达标建议暂停（仅输出建议，不直接调控）",
            code=code,
            parameters_schema={
                "spend_threshold": {
                    "type": "number",
                    "default": 3.0,
                    "unit": "USD",
                    "description": "Minimum spend before evaluating performance.",
                },
                "north_america_cpc_threshold": {
                    "type": "number",
                    "default": 3.0,
                    "unit": "USD",
                },
                "rest_of_world_cpc_threshold": {
                    "type": "number",
                    "default": 1.5,
                    "unit": "USD",
                },
                "ctr_threshold": {
                    "type": "number",
                    "default": 1.0,
                    "unit": "percent",
                },
            },
            tags=["demo", "spend_guard", "creative"],
            status=RuleStatus.PUBLISHED.value,
            is_active=True,
            version="1.0.0",
            created_by="system",
            updated_by="system",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        await doc.insert()
        logger.info("Seeded demo rule '%s' from %s", rule_name, script_path)

    # ===== Helpers =====

    @staticmethod
    def _build_default_context(binding: RuleBindingDocument | None) -> dict[str, Any]:
        if binding is None:
            return {}
        return {
            "entity_type": binding.entity_type,
            "entity_id": binding.entity_id,
            "rule_name": binding.rule_name,
            "rule_id": binding.rule_id,
            "metadata": binding.metadata,
        }
