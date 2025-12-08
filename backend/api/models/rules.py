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
    rule_id: str = Field(..., description="Rule name (registry key)")
    rule_name: str = Field(..., description="Rule display name")
    rule_config_id: str | None = Field(default=None, description="Optional config ID for parameter overrides")
    entity_type: BindingEntityType
    entity_id: str = Field(..., description="ID of the target object")

    # Ad hierarchy for indexing
    ad_account_id: str = Field(..., description="Ad account ID (required)")
    campaign_id: str | None = Field(default=None, description="Campaign ID")
    adset_id: str | None = Field(default=None, description="AdSet ID")
    ad_id: str | None = Field(default=None, description="Ad ID")

    source: BindingSource = Field(default=BindingSource.MANUAL)
    is_active: bool = True


class RuleBindingCreate(BaseModel):
    """Create a rule binding with full ad hierarchy for indexing."""
    rule_id: str = Field(..., description="Rule name from registry")
    rule_config_id: str | None = Field(default=None, description="Optional config ID for custom parameters")
    entity_type: BindingEntityType
    entity_id: str

    # Ad hierarchy fields - required for proper indexing
    ad_account_id: str = Field(..., description="Ad account ID (always required)")
    campaign_id: str | None = Field(default=None, description="Campaign ID (required if entity_type >= campaign)")
    adset_id: str | None = Field(default=None, description="AdSet ID (required if entity_type >= adset)")
    ad_id: str | None = Field(default=None, description="Ad ID (required if entity_type = ad)")

    source: BindingSource = BindingSource.MANUAL


class RuleBindingUpdate(BaseModel):
    """Update binding - only allow toggling active status and config."""
    rule_config_id: str | None = None
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


# ===== Rule Config Models (Unified rule model) =====


class RuleSource(str, Enum):
    """来源类型"""
    SYSTEM = "system"  # 基础规则（来自代码注册表）
    # 用户自定义规则使用 "user:{user_id}" 格式


class RuleConfigCreate(BaseModel):
    """Create a new rule configuration (clone from base rule or another config)
    
    命名规则: {base_rule}:{user_id}:{suffix}
    - 从系统规则复制: ml_auto_stop:user123:conservative
    - 从用户规则复制: ml_auto_stop:user456:aggressive (只修改user_id和suffix)
    """
    suffix: str = Field(..., description="User-defined suffix for the rule name")
    base_rule: str = Field(..., description="Base rule name from registry")
    template_id: str | None = Field(default=None, description="Template rule ID to clone from")
    description: str | None = None
    parameter_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Override default values in parameters_schema (evaluation_date will be excluded)"
    )
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None


class RuleConfigUpdate(BaseModel):
    """Update an existing rule configuration"""
    description: str | None = None
    parameter_overrides: dict[str, Any] | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    updated_by: str | None = None


class RuleConfigArchive(BaseModel):
    """Archive a rule configuration (instead of delete)"""
    updated_by: str | None = None


class RuleConfigResponse(BaseModel):
    """Rule configuration response - unified model for base and custom rules"""
    id: str
    name: str
    base_rule: str  # ID of the base system rule
    base_rule_name: str | None = None  # Name of the base system rule (for display)
    description: str | None = None
    version: str
    
    # Source tracking
    template_id: str | None = None  # None = base rule, otherwise = cloned from
    source: str = "system"  # "system" or "user:{user_id}"
    
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    # Merged parameters_schema (base + overrides)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    
    is_active: bool = True
    is_archived: bool = False  # Archived rules are hidden but not deleted
    
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class RuleConfigClone(BaseModel):
    """Clone an existing rule config with new parameters"""
    new_name: str = Field(..., description="Name for the cloned config")
    parameter_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameter overrides (merged with source)"
    )
    description: str | None = None
    created_by: str | None = None
