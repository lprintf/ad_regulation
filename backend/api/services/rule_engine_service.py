"""
Service layer implementation for the rule engine domain.
Provides binding management, execution, and scheduler entry points.

Refactored to use Python module-based rules instead of database-stored code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from bson import ObjectId

from api.models.rules import (
    BindingEntityType,
    BindingSource,
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleConfigArchive,
    RuleConfigClone,
    RuleConfigCreate,
    RuleConfigResponse,
    RuleConfigUpdate,
    RuleExecutionListResponse,
    RuleExecutionLogResponse,
    RuleExecutionRequest,
    RuleExecutionStatus,
    RuleTrigger,
)
from rules import get_rule_class, get_rule_metadata, list_rules as registry_list_rules
from utils.db import (
    RuleBindingDocument,
    RuleConfigDocument,
    RuleExecutionLogDocument,
)

logger = logging.getLogger(__name__)


def _to_object_id(identifier: str) -> ObjectId:
    if not ObjectId.is_valid(identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    return ObjectId(identifier)


def _serialize_binding(doc: RuleBindingDocument) -> RuleBindingResponse:
    return RuleBindingResponse(
        id=str(doc.id),
        rule_id=doc.rule_id,
        rule_name=doc.rule_name,
        rule_config_id=doc.rule_config_id,
        entity_type=BindingEntityType(doc.entity_type),
        entity_id=doc.entity_id,
        ad_account_id=doc.ad_account_id,
        campaign_id=doc.campaign_id,
        adset_id=doc.adset_id,
        ad_id=doc.ad_id,
        source=BindingSource(doc.source),
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
        execution_logs=doc.execution_logs,
    )


def _merge_parameters_schema(
    base_schema: dict[str, Any],
    overrides: dict[str, Any]
) -> dict[str, Any]:
    """Merge base parameters_schema with overrides (update default values)."""
    merged = {}
    for key, param in base_schema.items():
        merged[key] = dict(param)  # Copy base param
        if key in overrides:
            merged[key]["default"] = overrides[key]
    return merged


async def _serialize_config(doc: RuleConfigDocument) -> RuleConfigResponse:
    """Serialize RuleConfigDocument to response model."""
    # Resolve base_rule_name
    # For system rules: base_rule == name (the rule name itself)
    # For user rules: base_rule is the ID of the system rule
    if doc.source == "system":
        base_rule_name = doc.name
        base_meta = get_rule_metadata(doc.name)
    else:
        # base_rule is an ID, need to look up the system rule
        base_rule_name = doc.name.split(":")[0] if ":" in doc.name else doc.base_rule
        base_meta = get_rule_metadata(base_rule_name)
    
    base_schema = base_meta.get("parameters_schema", {}) if base_meta else {}

    # Merge with overrides
    merged_schema = _merge_parameters_schema(base_schema, doc.parameter_overrides)

    return RuleConfigResponse(
        id=str(doc.id),
        name=doc.name,
        base_rule=doc.base_rule,
        base_rule_name=base_rule_name,
        description=doc.description,
        version=doc.version,
        template_id=doc.template_id,
        source=doc.source,
        parameter_overrides=doc.parameter_overrides,
        parameters_schema=merged_schema,
        tags=doc.tags,
        is_active=doc.is_active,
        is_archived=doc.is_archived,
        created_by=doc.created_by,
        updated_by=doc.updated_by,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _increment_version(version: str) -> str:
    """Increment the patch version number. e.g., '1.0.0' -> '1.0.1'"""
    try:
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            return ".".join(parts)
    except (ValueError, IndexError):
        pass
    return version + ".1"


class RuleEngineService:
    """Service layer for rule engine functionality."""

    # ===== Rule Discovery (from Registry) =====

    @staticmethod
    def list_available_rules() -> list[dict]:
        """List all available rules from the registry."""
        return registry_list_rules()

    @staticmethod
    def get_rule_info(rule_name: str) -> dict | None:
        """Get metadata for a specific rule."""
        return get_rule_metadata(rule_name)

    @staticmethod
    async def sync_system_rules() -> int:
        """
        Sync system rules from code registry to database.
        Creates or updates RuleConfigDocument for each registered rule.
        Returns the number of rules synced.
        """
        rules = registry_list_rules()
        synced = 0
        
        for rule_meta in rules:
            rule_name = rule_meta.get("name")
            if not rule_name:
                continue
            
            # Check if system rule already exists
            existing = await RuleConfigDocument.find_one(
                RuleConfigDocument.name == rule_name,
                RuleConfigDocument.source == "system"
            )
            
            now = datetime.utcnow()
            
            if existing:
                # Update existing system rule
                existing.description = rule_meta.get("description")
                existing.version = rule_meta.get("version", "1.0.0")
                existing.tags = rule_meta.get("tags", [])
                existing.updated_at = now
                await existing.save()
            else:
                # Create new system rule
                config = RuleConfigDocument(
                    name=rule_name,
                    base_rule=rule_name,
                    description=rule_meta.get("description"),
                    version=rule_meta.get("version", "1.0.0"),
                    template_id=None,  # System rules have no template
                    source="system",
                    parameter_overrides={},  # System rules use defaults
                    tags=rule_meta.get("tags", []),
                    is_active=True,
                    is_archived=False,
                    created_by="system",
                    updated_by="system",
                    created_at=now,
                    updated_at=now,
                )
                await config.insert()
            
            synced += 1
            logger.debug("Synced system rule '%s' to database", rule_name)
        
        logger.info("Synced %d system rules to database", synced)
        return synced

    # ===== Rule Config Management (Clone with modified parameters) =====

    @staticmethod
    async def create_config(data: RuleConfigCreate) -> RuleConfigResponse:
        """Create a new rule configuration (clone from base rule or another config).
        
        命名规则: {base_rule_name}:{user_id}:{suffix}
        - base_rule 存储系统规则的 ID
        - evaluation_date 参数不可覆盖，永远为空
        - 默认复制模板规则的标签
        """
        # template_id is required - must clone from an existing rule
        if not data.template_id:
            raise ValueError("template_id is required - must clone from an existing rule")
        
        # Get template rule
        template_doc = await RuleConfigDocument.get(_to_object_id(data.template_id))
        if template_doc is None:
            raise ValueError(f"Template rule '{data.template_id}' not found")
        
        # Get the base rule name for naming (traverse to system rule if needed)
        base_rule_id = template_doc.base_rule if template_doc.source != "system" else str(template_doc.id)
        base_rule_name = template_doc.name.split(":")[0] if ":" in template_doc.name else template_doc.name
        
        # Validate base rule exists in registry
        base_meta = get_rule_metadata(base_rule_name)
        if base_meta is None:
            raise ValueError(f"Base rule '{base_rule_name}' not found in registry")

        # Build rule name: {base_rule_name}:{user_id}:{suffix}
        user_id = data.created_by or "unknown"
        rule_name = f"{base_rule_name}:{user_id}:{data.suffix}"

        # Check name uniqueness
        existing = await RuleConfigDocument.find_one(
            RuleConfigDocument.name == rule_name
        )
        if existing:
            raise ValueError(f"Config name '{rule_name}' already exists")

        # Filter out evaluation_date from parameter_overrides (always empty)
        filtered_overrides = {
            k: v for k, v in data.parameter_overrides.items() 
            if k != "evaluation_date"
        }

        # Validate parameter_overrides keys exist in base schema
        base_schema = base_meta.get("parameters_schema", {})
        for key in filtered_overrides.keys():
            if key not in base_schema:
                logger.warning(f"Parameter override key '{key}' not in base schema, skipping validation")

        # Determine version based on template
        template_version = template_doc.version
        version = _increment_version(template_version)

        # Determine source
        source = f"user:{user_id}"

        # Copy tags from template if not provided
        tags = data.tags if data.tags else list(template_doc.tags)

        now = datetime.utcnow()
        config = RuleConfigDocument(
            name=rule_name,
            base_rule=base_rule_id,  # Store ID, not name
            description=data.description or template_doc.description,
            version=version,
            template_id=data.template_id,
            source=source,
            parameter_overrides=filtered_overrides,
            tags=tags,
            created_by=data.created_by,
            updated_by=data.created_by,
            created_at=now,
            updated_at=now,
        )
        await config.insert()
        logger.info("Created rule config '%s' based on template '%s' (v%s, source=%s)", 
                   config.name, template_doc.name, config.version, config.source)
        return await _serialize_config(config)

    @staticmethod
    async def list_configs(
        base_rule: str | None = None,
        include_archived: bool = False,
        source: str | None = None,
    ) -> list[RuleConfigResponse]:
        """List rule configurations, optionally filtered by base rule and source."""
        filters = []
        if base_rule:
            filters.append(RuleConfigDocument.base_rule == base_rule)
        if not include_archived:
            filters.append(RuleConfigDocument.is_archived == False)  # noqa: E712
        if source:
            if source == "system":
                filters.append(RuleConfigDocument.source == "system")
            elif source == "user":
                # Match any user source (starts with "user:")
                filters.append(RuleConfigDocument.source != "system")

        cursor = RuleConfigDocument.find(*filters) if filters else RuleConfigDocument.find({})
        docs = await cursor.to_list()
        return [await _serialize_config(doc) for doc in docs]

    @staticmethod
    async def get_config(config_id: str) -> RuleConfigResponse:
        """Get a specific rule configuration."""
        doc = await RuleConfigDocument.get(_to_object_id(config_id))
        if doc is None:
            raise ValueError("Config not found")
        return await _serialize_config(doc)

    @staticmethod
    async def get_config_by_name(name: str) -> RuleConfigResponse:
        """Get a rule configuration by name."""
        doc = await RuleConfigDocument.find_one(RuleConfigDocument.name == name)
        if doc is None:
            raise ValueError(f"Config '{name}' not found")
        return await _serialize_config(doc)

    @staticmethod
    async def update_config(config_id: str, data: RuleConfigUpdate) -> RuleConfigResponse:
        """Update a rule configuration."""
        doc = await RuleConfigDocument.get(_to_object_id(config_id))
        if doc is None:
            raise ValueError("Config not found")

        updated = False
        if data.description is not None:
            doc.description = data.description
            updated = True
        if data.parameter_overrides is not None:
            doc.parameter_overrides = data.parameter_overrides
            doc.version = _increment_version(doc.version)  # Auto-increment version
            updated = True
        if data.tags is not None:
            doc.tags = data.tags
            updated = True
        if data.is_active is not None:
            doc.is_active = data.is_active
            updated = True
        if data.updated_by is not None:
            doc.updated_by = data.updated_by

        if updated:
            doc.updated_at = datetime.utcnow()
            await doc.save()
            logger.info("Updated rule config '%s' (v%s)", doc.name, doc.version)

        return await _serialize_config(doc)

    @staticmethod
    async def clone_config(config_id: str, data: RuleConfigClone) -> RuleConfigResponse:
        """Clone an existing config with new name and additional overrides."""
        original = await RuleConfigDocument.get(_to_object_id(config_id))
        if original is None:
            raise ValueError("Config not found")

        # Check new name uniqueness
        existing = await RuleConfigDocument.find_one(
            RuleConfigDocument.name == data.new_name
        )
        if existing:
            raise ValueError(f"Config name '{data.new_name}' already exists")

        # Merge parameter overrides
        merged_overrides = dict(original.parameter_overrides)
        merged_overrides.update(data.parameter_overrides)

        # Increment version based on original
        version = _increment_version(original.version)

        # Determine source
        source = f"user:{data.created_by}" if data.created_by else "user:unknown"

        now = datetime.utcnow()
        cloned = RuleConfigDocument(
            name=data.new_name,
            base_rule=original.base_rule,
            description=data.description or original.description,
            version=version,
            template_id=str(original.id),  # Track clone source
            source=source,
            parameter_overrides=merged_overrides,
            tags=original.tags,
            created_by=data.created_by,
            updated_by=data.created_by,
            created_at=now,
            updated_at=now,
        )
        await cloned.insert()
        logger.info("Cloned config '%s' to '%s' (v%s, source=%s)", 
                   original.name, cloned.name, cloned.version, cloned.source)
        return await _serialize_config(cloned)

    @staticmethod
    async def archive_config(config_id: str, data: RuleConfigArchive | None = None) -> RuleConfigResponse:
        """Archive a rule configuration (soft delete - rules cannot be deleted)."""
        doc = await RuleConfigDocument.get(_to_object_id(config_id))
        if doc is None:
            raise ValueError("Config not found")
        
        # Don't allow archiving system rules
        if doc.source == "system":
            raise ValueError("Cannot archive system rules")
        
        doc.is_archived = True
        doc.is_active = False
        doc.updated_at = datetime.utcnow()
        if data and data.updated_by:
            doc.updated_by = data.updated_by
        await doc.save()
        logger.info("Archived rule config '%s'", doc.name)
        return await _serialize_config(doc)

    @staticmethod
    async def delete_config(config_id: str) -> None:
        """Delete is replaced by archive - this method now archives instead."""
        doc = await RuleConfigDocument.get(_to_object_id(config_id))
        if doc is None:
            return
        
        # Don't allow deleting system rules
        if doc.source == "system":
            raise ValueError("Cannot delete system rules, use archive instead")
        
        # Archive instead of delete
        doc.is_archived = True
        doc.is_active = False
        doc.updated_at = datetime.utcnow()
        await doc.save()
        logger.info("Archived (soft-deleted) rule config '%s'", doc.name)

    # ===== Binding management =====

    @staticmethod
    async def create_binding(data: RuleBindingCreate) -> RuleBindingResponse:
        """Create a binding between a rule and an entity."""
        # Validate rule exists in registry
        rule_meta = get_rule_metadata(data.rule_id)  # rule_id is now rule_name
        if rule_meta is None:
            raise ValueError(f"Rule '{data.rule_id}' not found in registry")

        rule_name = rule_meta["name"]

        # Validate rule_config_id if provided
        if data.rule_config_id:
            config = await RuleConfigDocument.get(_to_object_id(data.rule_config_id))
            if config is None:
                raise ValueError(f"Rule config '{data.rule_config_id}' not found")
            if config.base_rule != rule_name:
                raise ValueError(f"Config '{config.name}' is for rule '{config.base_rule}', not '{rule_name}'")

        existing = await RuleBindingDocument.find_one(
            RuleBindingDocument.rule_name == rule_name,
            RuleBindingDocument.entity_id == data.entity_id,
        )
        if existing:
            raise ValueError("Binding already exists for this rule and entity")

        now = datetime.utcnow()
        binding = RuleBindingDocument(
            rule_id=rule_name,  # Store rule name as rule_id for compatibility
            rule_name=rule_name,
            rule_config_id=data.rule_config_id,
            entity_type=data.entity_type.value,
            entity_id=data.entity_id,
            ad_account_id=data.ad_account_id,
            campaign_id=data.campaign_id,
            adset_id=data.adset_id,
            ad_id=data.ad_id,
            source=data.source.value,
            created_at=now,
            updated_at=now,
        )
        await binding.insert()
        logger.info("Created binding %s for rule '%s' on entity %s", binding.id, rule_name, data.entity_id)
        return _serialize_binding(binding)

    @staticmethod
    async def create_binding_by_name(
        rule_name: str,
        entity_type: str,
        entity_id: str,
        ad_account_id: str,
        campaign_id: str | None = None,
        adset_id: str | None = None,
        ad_id: str | None = None,
        rule_config_id: str | None = None,
        source: str = "manual",
    ) -> RuleBindingResponse:
        """Create a binding using rule name directly."""
        rule_meta = get_rule_metadata(rule_name)
        if rule_meta is None:
            raise ValueError(f"Rule '{rule_name}' not found in registry")

        existing = await RuleBindingDocument.find_one(
            RuleBindingDocument.rule_name == rule_name,
            RuleBindingDocument.entity_id == entity_id,
        )
        if existing:
            raise ValueError("Binding already exists for this rule and entity")

        now = datetime.utcnow()
        binding = RuleBindingDocument(
            rule_id=rule_name,
            rule_name=rule_name,
            rule_config_id=rule_config_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ad_account_id=ad_account_id,
            campaign_id=campaign_id,
            adset_id=adset_id,
            ad_id=ad_id,
            source=source,
            created_at=now,
            updated_at=now,
        )
        await binding.insert()
        logger.info("Created binding %s for rule '%s'", binding.id, rule_name)
        return _serialize_binding(binding)

    @staticmethod
    async def list_bindings(
        rule_name: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[RuleBindingResponse]:
        filters: list[Any] = []
        if rule_name:
            filters.append(RuleBindingDocument.rule_name == rule_name)
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

        if data.rule_config_id is not None:
            # Validate config exists and matches the rule
            if data.rule_config_id:  # Non-empty string
                config = await RuleConfigDocument.get(_to_object_id(data.rule_config_id))
                if config is None:
                    raise ValueError(f"Rule config '{data.rule_config_id}' not found")
                if config.base_rule != binding.rule_name:
                    raise ValueError(f"Config '{config.name}' is for rule '{config.base_rule}', not '{binding.rule_name}'")
            binding.rule_config_id = data.rule_config_id if data.rule_config_id else None
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
        """
        Execute a rule using the new registry-based system.

        The rule class is loaded from the registry, instantiated with binding and params,
        and executed directly (no sandbox).
        """
        binding: RuleBindingDocument | None = None
        rule_name: str

        if request.binding_id:
            binding = await RuleBindingDocument.get(_to_object_id(request.binding_id))
            if binding is None:
                raise ValueError("Binding not found")
            rule_name = binding.rule_name
        elif request.rule_id:
            # rule_id is now interpreted as rule_name
            rule_name = request.rule_id
        else:
            raise ValueError("Either rule_id or binding_id must be provided")

        # Get rule class from registry
        try:
            rule_class = get_rule_class(rule_name)
        except ValueError as exc:
            raise ValueError(f"Rule not found: {exc}") from exc

        # Merge params: rule config overrides + request params
        params = {}
        if binding and binding.rule_config_id:
            # Load parameter overrides from rule config
            config = await RuleConfigDocument.get(_to_object_id(binding.rule_config_id))
            if config and config.parameter_overrides:
                params.update(config.parameter_overrides)
        if request.params:
            params.update(request.params)

        # Instantiate and execute rule
        rule_instance = rule_class(binding=binding, params=params)

        start_time = datetime.utcnow()
        result = await rule_instance.execute()
        completed_at = datetime.utcnow()
        duration_ms = int((completed_at - start_time).total_seconds() * 1000)

        # Determine status
        if result.decision == "error":
            status = RuleExecutionStatus.FAILED
            error_message = "; ".join(result.reasons) if result.reasons else "Unknown error"
        else:
            status = RuleExecutionStatus.SUCCESS
            error_message = None

        # Build context snapshot for logging
        context_snapshot = {
            "params": params,
            "decision": result.decision,
        }
        if binding:
            context_snapshot["entity_type"] = binding.entity_type
            context_snapshot["entity_id"] = binding.entity_id
            context_snapshot["ad_account_id"] = binding.ad_account_id
            context_snapshot["rule_config_id"] = binding.rule_config_id

        # Save execution log
        log_doc = RuleExecutionLogDocument(
            rule_name=rule_name,
            rule_id=rule_name,
            rule_version=rule_class.version,
            binding=binding,
            entity_type=binding.entity_type if binding else None,
            entity_id=binding.entity_id if binding else None,
            trigger=request.trigger.value,
            scheduled_run_time=scheduled_run_time,
            actual_start_time=start_time,
            completed_at=completed_at,
            status=status.value,
            actions=result.actions,
            reasons=result.reasons,
            metrics=result.metrics,
            context_snapshot=context_snapshot,
            error_message=error_message,
            execution_duration_ms=duration_ms,
            execution_logs=result.logs,
        )
        await log_doc.insert()

        # Update binding last_executed_at
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
    async def list_binding_executions(
        binding_id: str, limit: int = 50
    ) -> RuleExecutionListResponse:
        """List execution history for a specific binding."""
        from bson.dbref import DBRef

        binding_obj_id = _to_object_id(binding_id)
        binding_ref = DBRef(collection="rule_bindings", id=binding_obj_id)

        docs = (
            await RuleExecutionLogDocument.find({"binding": binding_ref})
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
        """Run all active bindings."""
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
            except Exception as exc:
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
        """Placeholder for ad naming parser integration."""
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
