"""
Pydantic models for rule engine domain.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RuleStatus(str, Enum):
    """Lifecycle status of a rule definition."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class RuleTrigger(str, Enum):
    """How a rule execution was triggered."""

    MANUAL = "manual"
    SCHEDULER = "scheduler"
    AUTO_UNBIND = "auto_unbind"
    TEST = "test"


class BindingSource(str, Enum):
    """Source of a rule binding."""

    MANUAL = "manual"
    AUTO = "auto"
    NAMING_PARSER = "naming_parser"


class BindingEntityType(str, Enum):
    """Object types that rules can bind to."""

    AD = "ad"
    ADSET = "adset"
    CAMPAIGN = "campaign"
    ACCOUNT = "account"


class RuleDefinitionBase(BaseModel):
    name: str = Field(..., description="Unique rule identifier")
    description: str | None = Field(
        default=None, description="Human readable description"
    )
    version: str = Field(default="1.0.0", description="Semantic version of the rule")
    code: str = Field(..., description="Python script implementing the rule")
    parameters_schema: dict[str, Any] = Field(
        default_factory=dict, description="Optional parameter definitions"
    )
    tags: list[str] = Field(default_factory=list, description="Categorisation tags")
    status: RuleStatus = Field(default=RuleStatus.DRAFT)
    is_active: bool = Field(default=False)


class RuleDefinitionCreate(BaseModel):
    name: str
    description: str | None = None
    code: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = Field(default=None, description="Operator user id")


class RuleDefinitionUpdate(BaseModel):
    description: str | None = None
    code: str | None = None
    parameters_schema: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: RuleStatus | None = None
    is_active: bool | None = None
    version: str | None = None
    updated_by: str | None = Field(default=None, description="Operator user id")


class RuleDefinitionClone(BaseModel):
    """Clone an existing rule with modified parameters and version."""

    new_name: str = Field(..., description="Name for the cloned rule")
    new_version: str = Field(default="1.0.0", description="Version for the cloned rule")
    parameter_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Override default values in parameters_schema"
    )
    description: str | None = Field(
        default=None,
        description="Optional new description (uses original if not provided)"
    )
    created_by: str | None = Field(default=None, description="Operator user id")


class RuleDefinitionResponse(RuleDefinitionBase):
    id: str = Field(..., description="Document id")
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class RuleBindingBase(BaseModel):
    rule_id: str = Field(..., description="Rule definition id")
    rule_name: str = Field(..., description="Rule definition name")
    entity_type: BindingEntityType
    entity_id: str = Field(..., description="ID of the target object")
    source: BindingSource = Field(default=BindingSource.MANUAL)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class RuleBindingCreate(BaseModel):
    rule_id: str
    entity_type: BindingEntityType
    entity_id: str
    source: BindingSource = BindingSource.MANUAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleBindingUpdate(BaseModel):
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class RuleBindingResponse(RuleBindingBase):
    id: str
    created_at: datetime
    updated_at: datetime
    last_executed_at: datetime | None = None


class RuleExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class RuleExecutionRequest(BaseModel):
    rule_id: str | None = Field(default=None, description="Rule definition id")
    binding_id: str | None = Field(
        default=None, description="Specific binding to execute"
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional execution context override (for testing)",
    )
    params: dict[str, Any] | None = Field(
        default=None, description="Optional parameter overrides"
    )
    trigger: RuleTrigger = RuleTrigger.MANUAL


class RuleExecutionLogResponse(BaseModel):
    id: str
    rule_id: str | None = None
    rule_name: str
    rule_version: str | None = None
    binding_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    trigger: RuleTrigger
    scheduled_run_time: datetime | None = None
    actual_start_time: datetime
    completed_at: datetime | None = None
    status: RuleExecutionStatus
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    execution_duration_ms: int | None = None
    execution_logs: list[str] = Field(default_factory=list)


class RuleExecutionListResponse(BaseModel):
    executions: list[RuleExecutionLogResponse]
    total: int

