"""
Request and response models for Insights endpoints.
"""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AsyncJobStatus(str, Enum):
    """Async job status enum."""

    PENDING = "Job Not Started"
    IN_PROGRESS = "Job Running"
    COMPLETED = "Job Completed"
    FAILED = "Job Failed"
    SKIPPED = "Job Skipped"


class InsightMetrics(BaseModel):
    """Individual insight metrics."""

    spend: float = Field(..., description="Total spend")
    impressions: int = Field(..., description="Number of impressions")
    reach: int = Field(..., description="Number of unique users reached")
    clicks: int = Field(..., description="Total clicks")
    inline_link_clicks: int = Field(..., description="Inline link clicks")
    outbound_clicks: int = Field(..., description="Outbound clicks")
    landing_page_view: int = Field(..., description="Landing page views")
    onsite_web_checkout: int = Field(..., description="On-site checkout events")
    onsite_web_add_to_cart: int = Field(..., description="Add to cart events")
    onsite_web_purchase: int = Field(..., description="Purchase events")
    onsite_web_checkout_value: float = Field(..., description="Checkout value")
    onsite_web_add_to_cart_value: float = Field(..., description="Add to cart value")
    onsite_web_purchase_value: float = Field(..., description="Purchase value")


class InsightRecord(BaseModel):
    """Single insight data record."""

    ad_account_id: str = Field(
        ...,
        description="Ad account ID (with act_ prefix)",
    )
    ad_id: str | None = Field(
        default=None,
        description="Ad ID when level=ad, otherwise null",
    )
    adset_id: str | None = Field(
        None, description="AdSet ID (populated when level=adset)"
    )
    campaign_id: str | None = Field(
        None, description="Campaign ID (populated when level=campaign)"
    )
    # Entity names for better readability
    ad_name: str | None = Field(
        None, description="Ad name (if available)"
    )
    adset_name: str | None = Field(
        None, description="AdSet name (populated when level=adset, if available)"
    )
    campaign_name: str | None = Field(
        None, description="Campaign name (populated when level=campaign, if available)"
    )
    configured_status: str | None = Field(
        None, description="Configured status for the entity at the requested level"
    )
    effective_status: str | None = Field(
        None, description="Effective status for the entity at the requested level"
    )
    date: str = Field(..., description="Date of the insight (YYYY-MM-DD or datetime)")
    metrics: InsightMetrics = Field(..., description="Insight metrics")


# Keep DailyInsight as alias for backward compatibility
DailyInsight = InsightRecord


class InsightsRequest(BaseModel):
    """Base request model for fetching insights data."""

    ad_account_id: str = Field(
        ...,
        description="Ad account ID (with or without act_ prefix)",
        examples=["act_123456789", "123456789"],
    )
    since: str = Field(
        ...,
        description="Start date (YYYY-MM-DD)",
        examples=["2025-01-01"],
    )
    until: str = Field(
        ...,
        description="End date (YYYY-MM-DD)",
        examples=["2025-01-31"],
    )
    level: str = Field(
        default="ad",
        description="Aggregation level: ad, adset, or campaign",
        examples=["ad", "adset", "campaign"],
    )
    time_increment: int | None = Field(
        default=None,
        description="Time increment: 1=daily, None=aggregate all",
        examples=[1, None],
    )
    breakdowns: str | None = Field(
        default=None,
        description="Comma-separated breakdown dimensions (e.g., 'country', 'hourly_stats_aggregated_by_advertiser_time_zone')",
        examples=["country", "hourly_stats_aggregated_by_advertiser_time_zone"],
    )
    object_ids: list[str] | None = Field(
        default=None,
        description="Optional entity IDs to filter within the selected account",
        examples=[["123", "456"]],
    )
    object_level: Literal["ad", "adset", "campaign"] | None = Field(
        default=None,
        alias="obj_level",
        description="Level of the provided object_ids (ad, adset, or campaign)",
    )


class InsightsSyncRequest(InsightsRequest):
    """Request payload for synchronous insights fetch."""

    fields: list[str] | None = Field(
        default=None,
        description="Additional fields to request from Facebook (e.g., ['ad_name','adset_name'])",
    )


def _validate_cache_hint_value(value: str | None) -> str | None:
    if value is None:
        return value
    pattern = r"\d{2}:\d{2}:\d{2}"
    if re.fullmatch(pattern, value):
        return value
    raise ValueError(
        "cache_window_hint must follow dd:hh:mm format, for example '12:14:30'."
    )


class InsightsFromLastRequest(BaseModel):
    """Request payload for filling realtime window using last sync metadata."""

    ad_account_id: str = Field(
        ...,
        description="Ad account ID (with or without act_ prefix)",
        examples=["act_123456789", "123456789"],
    )
    until: str = Field(
        ...,
        description="End date (YYYY-MM-DD)",
        examples=["2025-01-31"],
    )
    level: str = Field(
        default="ad",
        description="Aggregation level: ad, adset, or campaign",
        examples=["ad", "adset", "campaign"],
    )
    time_increment: int | None = Field(
        default=None,
        description="Time increment: 1=daily, None=aggregate all",
        examples=[1, None],
    )
    breakdowns: str | None = Field(
        default=None,
        description="Comma-separated breakdown dimensions (e.g., 'country', 'hourly_stats_aggregated_by_advertiser_time_zone')",
        examples=["country", "hourly_stats_aggregated_by_advertiser_time_zone"],
    )
    fields: list[str] | None = Field(
        default=None,
        description="Additional fields to request from Facebook (e.g., ['ad_name','adset_name'])",
    )
    object_ids: list[str] | None = Field(
        default=None,
        description="Optional entity IDs to limit realtime backfill scope",
        examples=[["123", "456"]],
    )
    object_level: Literal["ad", "adset", "campaign"] | None = Field(
        default=None,
        alias="obj_level",
        description="Level of the provided object_ids (ad, adset, or campaign)",
    )
    cache_window_hint: str | None = Field(
        default=None,
        description="Minute-level cache hint in dd:hh:mm format (e.g., '12:14:30').",
        examples=["12:14:30"],
    )

    @field_validator("fields", mode="before")
    @classmethod
    def _normalize_fields(cls, value: Any) -> list[str] | None:
        if value is None or value == "":
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            normalized = [item for item in items if item]
            return normalized or None
        raise TypeError("fields must be a list of strings or a comma-separated string")

    @field_validator("cache_window_hint")
    @classmethod
    def _validate_cache_hint(cls, value: str | None) -> str | None:
        return _validate_cache_hint_value(value)


class InsightsHybridRequest(InsightsSyncRequest):
    """Request payload for hybrid (database + realtime gap) queries."""

    cache_window_hint: str | None = Field(
        default=None,
        description="Optional dd:hh:mm hint so gateway caches hybrid realtime window responses.",
        examples=["12:14:30"],
    )

    @field_validator("cache_window_hint")
    @classmethod
    def _validate_cache_hint(cls, value: str | None) -> str | None:
        return _validate_cache_hint_value(value)


class InsightsResponse(BaseModel):
    """Response model for insights data."""

    insights: list[InsightRecord] = Field(..., description="List of insight records")
    total_records: int = Field(..., description="Total number of insight records")
    date_range: dict[str, str] = Field(
        ..., description="Date range of the data (since, until)"
    )
    last_synced_date: str | None = Field(
        default=None, description="Last synced date for this account (YYYY-MM-DD)"
    )


class AsyncJobCreateResponse(BaseModel):
    """Response model for async job creation."""

    job_id: str = Field(..., description="Facebook Async Job ID")
    ad_account_id: str = Field(..., description="Ad account ID")
    status: AsyncJobStatus = Field(..., description="Initial job status")
    created_at: str = Field(..., description="Job creation timestamp")


class AsyncJobStatusResponse(BaseModel):
    """Response model for async job status check."""

    job_id: str = Field(..., description="Facebook Async Job ID")
    ad_account_id: str = Field(..., description="Ad account ID")
    status: AsyncJobStatus = Field(..., description="Current job status")
    percent_complete: int = Field(
        ..., description="Job completion percentage (0-100)", ge=0, le=100
    )
    created_at: str | None = Field(None, description="Job creation timestamp")
    updated_at: str | None = Field(None, description="Last update timestamp")


class SyncStatus(str, Enum):
    """Status enum for historical insights sync."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TriggerType(str, Enum):
    """Trigger type for sync operations."""

    MANUAL = "manual"
    AUTO = "auto"
    RETRY = "retry"


class SyncMode(str, Enum):
    """Sync execution mode."""

    SYNC = "sync"
    ASYNC = "async"


class DataTarget(str, Enum):
    """Data storage target."""

    MONGODB = "mongodb"
    REDIS = "redis"
    HYBRID = "hybrid"


class SyncHistoryRecord(BaseModel):
    """Single sync history record."""

    id: str = Field(..., description="Sync history record ID")
    account_id: str = Field(..., description="Ad account ID")
    account_name: str | None = Field(None, description="Ad account display name")
    trigger_type: TriggerType = Field(..., description="How the sync was triggered")
    triggered_by: str | None = Field(None, description="User ID who triggered the sync")
    since: str = Field(..., description="Sync start date (YYYY-MM-DD)")
    until: str = Field(..., description="Sync end date (YYYY-MM-DD)")
    mode: SyncMode = Field(..., description="Execution mode (sync or async)")
    data_target: DataTarget = Field(..., description="Data storage target (mongodb/redis/hybrid)")
    status: SyncStatus = Field(..., description="Current sync status")
    started_at: str = Field(..., description="When the sync started")
    completed_at: str | None = Field(None, description="When the sync completed")
    records_count: int = Field(..., description="Number of records synced")
    error_message: str | None = Field(None, description="Error message if failed")
    duration_seconds: float | None = Field(None, description="Duration in seconds")
    percent_complete: int = Field(
        ..., description="Progress percentage (0-100)", ge=0, le=100
    )
    total_days: int = Field(..., description="Total number of days to sync")
    processed_days: int = Field(..., description="Number of days processed")


class SyncHistoryListResponse(BaseModel):
    """Response for sync history list."""

    items: list[SyncHistoryRecord] = Field(..., description="List of sync history records")
    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Records per page")


class SyncProgress(BaseModel):
    """Current sync progress for an account."""

    account_id: str = Field(..., description="Ad account ID")
    account_name: str | None = Field(None, description="Ad account display name")
    status: SyncStatus = Field(..., description="Current sync status")
    percent_complete: int = Field(
        ..., description="Progress percentage (0-100)", ge=0, le=100
    )
    current_date: str | None = Field(None, description="Currently processing date")
    total_days: int = Field(..., description="Total number of days to sync")
    processed_days: int = Field(..., description="Number of days processed")
    estimated_remaining_seconds: float | None = Field(
        None, description="Estimated remaining time in seconds"
    )
    last_updated: str = Field(..., description="Last update timestamp")


class SyncOverviewItem(BaseModel):
    """Sync overview item for a single account."""

    account_id: str = Field(..., description="Ad account ID")
    account_name: str | None = Field(None, description="Ad account display name")

    # MongoDB 同步状态
    mongodb_status: SyncStatus = Field(..., description="MongoDB sync status")
    mongodb_is_running: bool = Field(..., description="Whether MongoDB sync is running")
    mongodb_last_synced_at: str | None = Field(None, description="Last successful MongoDB sync timestamp")

    # MongoDB 数据覆盖范围
    mongodb_coverage_since: str | None = Field(
        None, description="MongoDB earliest available data date (YYYY-MM-DD)"
    )
    mongodb_coverage_until: str | None = Field(
        None, description="MongoDB latest available data date (YYYY-MM-DD)"
    )
    mongodb_last_error: str | None = Field(None, description="Last MongoDB sync error message if any")
    mongodb_last_history_id: str | None = Field(None, description="ID of the most recent MongoDB sync history")

    # Redis 同步状态
    redis_status: SyncStatus = Field(..., description="Redis cache sync status")
    redis_is_running: bool = Field(..., description="Whether Redis cache sync is running")
    redis_last_synced_at: str | None = Field(None, description="Last successful Redis sync timestamp")

    # Redis 缓存覆盖范围
    redis_cache_since: str | None = Field(
        None, description="Redis cache earliest available data date (YYYY-MM-DD)"
    )
    redis_cache_until: str | None = Field(
        None, description="Redis cache latest available data date (YYYY-MM-DD)"
    )
    redis_last_error: str | None = Field(None, description="Last Redis sync error message if any")
    redis_last_history_id: str | None = Field(None, description="ID of the most recent Redis sync history")


class SyncOverviewResponse(BaseModel):
    """Response for sync overview."""

    items: list[SyncOverviewItem] = Field(..., description="List of account sync overviews")
    total_accounts: int = Field(..., description="Total number of accounts")


class InsightAccountSyncStatus(BaseModel):
    """Per-account insights sync state."""

    account_id: str = Field(..., description="Ad account ID")
    account_name: str | None = Field(None, description="Ad account display name")
    status: SyncStatus = Field(..., description="Latest sync status")
    since: str | None = Field(None, description="Earliest date that data is available (YYYY-MM-DD)")
    until: str | None = Field(None, description="Latest date synced (YYYY-MM-DD)")
    obs_since: str | None = Field(
        None,
        description="Earliest since parameter observed in scheduler history (YYYY-MM-DD)",
    )
    obs_until: str | None = Field(
        None,
        description="Latest until parameter observed in scheduler history (YYYY-MM-DD)",
    )
    last_synced_at: str | None = Field(None, description="Timestamp when sync last succeeded")
    last_error: str | None = Field(None, description="Most recent error message")
    range_since: str | None = Field(None, description="Current/last sync start date")
    range_until: str | None = Field(None, description="Current/last sync end date")
    mode: str | None = Field(None, description="Sync strategy, e.g., sync or async")
    trigger: str | None = Field(None, description="Trigger origin such as auto or manual")
    triggered_by: str | None = Field(None, description="User or system identifier that initiated the sync")
    updated_at: str | None = Field(None, description="Last time the state was updated")


class InsightsAccountSyncResponse(BaseModel):
    """Response containing per-account sync states."""

    items: list[InsightAccountSyncStatus] = Field(
        ..., description="List of account sync statuses"
    )


class InsightsSyncTriggerRequest(BaseModel):
    """Request payload to trigger manual sync for specific accounts and date range."""

    account_ids: list[str] | None = Field(
        default=None,
        description="Specific account IDs to sync. If omitted, apply to all accounts.",
    )
    since: str = Field(..., description="Start date (YYYY-MM-DD)")
    until: str = Field(..., description="End date (YYYY-MM-DD)")


class InsightsSyncTriggerResponse(BaseModel):
    """Response payload summarizing manual sync invocation."""

    total_accounts: int = Field(..., description="Total accounts considered for this sync request")
    processed_accounts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-account sync summary for successful executions",
    )
    failed_accounts: dict[str, str] = Field(
        default_factory=dict,
        description="Per-account error messages for failed executions",
    )


class SyncedEntityName(BaseModel):
    """Details for a single synced entity name entry."""

    entity_id: str = Field(..., description="Entity ID that was synced")
    entity_name: str | None = Field(None, description="Latest fetched entity name")
    configured_status: str | None = Field(
        None, description="Configured status returned by Facebook API"
    )
    effective_status: str | None = Field(
        None, description="Effective status returned by Facebook API"
    )
    entity_type: str = Field(..., description="Entity type (ad, adset, campaign)")
    account_id: str = Field(..., description="Ad account ID without act_ prefix")


class EntityNamesSyncResult(BaseModel):
    """Response payload for the sync entity names endpoint with debouncing support."""

    synced: int = Field(..., description="Number of entities successfully synced")
    failed: int = Field(..., description="Number of entities that failed to sync")
    total: int = Field(..., description="Total entity count in the request")
    rate_limited: int = Field(..., description="Number of rate limit events detected")
    skipped: int = Field(default=0, description="Number of entities skipped (already syncing)")
    status: str = Field(default="completed", description="Overall sync status: completed, partial, or skipped")
    entities: list[SyncedEntityName] = Field(
        default_factory=list, description="Details for entities whose names were synced"
    )
    failed_entities: list[str] = Field(
        default_factory=list, description="IDs of entities that failed to sync"
    )


class EntityNamesSyncRequest(BaseModel):
    """Request payload for syncing entity names."""

    ad_account_id: str = Field(
        ...,
        description="Ad account ID (with or without act_ prefix)",
        examples=["act_123456789", "123456789"],
    )
    entity_ids: list[str] = Field(
        ...,
        description="List of entity IDs to sync",
        min_length=1,
        examples=[["123", "456", "789"]],
    )
    entity_type: str = Field(
        ...,
        description="Entity type (ad, adset, or campaign)",
        examples=["ad"],
    )


# ===== Prediction Models =====


class PredictionRequest(BaseModel):
    """Request model for ad performance prediction."""

    ad_account_ids: list[str] | None = Field(
        default=None,
        description="List of ad account IDs to evaluate. If None, evaluate all accounts.",
        examples=[["act_123456789", "act_987654321"]],
    )
    lookback_days: int = Field(
        default=10,
        description="Number of days to look back for feature calculation",
        ge=7,
        le=30,
    )
    model_path: str | None = Field(
        default=None,
        description="Optional custom model path. Defaults to 'models/model.feather'",
        examples=["models/model.feather"],
    )


class PredictionRecord(BaseModel):
    """Single prediction record with ad information and stop probability."""

    ad_account_name: str = Field(..., description="Ad account name")
    ad_id: str = Field(..., description="Ad ID")
    date: str = Field(..., description="Date of the prediction (YYYY-MM-DD)")
    pred_proba: float = Field(
        ...,
        description="Probability that the ad should be stopped (0-1)",
        ge=0.0,
        le=1.0,
    )
    features: dict[str, float | int | None] = Field(
        ..., description="Computed features used for prediction"
    )


class PredictionResponse(BaseModel):
    """Response model for prediction results."""

    predictions: list[PredictionRecord] = Field(
        ..., description="List of prediction records"
    )
    total_records: int = Field(..., description="Total number of prediction records")
    date_range: dict[str, str] = Field(
        ..., description="Date range of the data used (since, until)"
    )
    evaluation_date: str = Field(
        ..., description="Date of evaluation (typically yesterday, YYYY-MM-DD)"
    )


class EntityTimelineDataPoint(BaseModel):
    """Single data point in entity timeline."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    spend: float = Field(..., description="Total spend for this date")
    clicks: int = Field(..., description="Total clicks for this date")
    impressions: int = Field(..., description="Total impressions for this date")


class EntityTimelineResponse(BaseModel):
    """Response model for entity timeline data."""

    entity_type: str = Field(..., description="Entity type (ad/adset/campaign)")
    entity_id: str = Field(..., description="Entity ID")
    date_range: dict[str, str] = Field(
        ..., description="Available date range (since, until) with ±1 day padding"
    )
    daily_data: list[EntityTimelineDataPoint] = Field(
        ..., description="Daily metrics for the entity"
    )
    total_days: int = Field(..., description="Total number of days with data")


# ===== New Simplified Insights API Models =====


class InsightsOverviewRequest(BaseModel):
    """Request model for account-level overview (initial page load)."""

    account_ids: list[str] = Field(
        ...,
        description="List of ad account IDs to query (user must have permission)",
        examples=[["act_123456789", "act_987654321"]],
        min_length=1,
    )
    since: str = Field(
        ...,
        description="Start date (YYYY-MM-DD)",
        examples=["2025-01-01"],
    )
    until: str = Field(
        ...,
        description="End date (YYYY-MM-DD)",
        examples=["2025-01-31"],
    )
    source: Literal["mongo", "redis", "mongo_redis"] = Field(
        default="mongo_redis",
        description="Data source: mongo (historical), redis (recent), mongo_redis (hybrid)",
    )


class AccountOverviewItem(BaseModel):
    """Single account overview record with aggregated metrics."""

    account_id: str = Field(..., description="Ad account ID (with act_ prefix)")
    account_name: str | None = Field(None, description="Ad account display name")
    metrics: InsightMetrics = Field(..., description="Aggregated metrics for the account")
    date_count: int = Field(..., description="Number of days with data")
    start_date: str | None = Field(None, description="First date with data")
    end_date: str | None = Field(None, description="Last date with data")


class InsightsOverviewResponse(BaseModel):
    """Response model for account-level overview."""

    items: list[AccountOverviewItem] = Field(..., description="Per-account overview data")
    totals: InsightMetrics | None = Field(None, description="Aggregated totals across all accounts")
    date_range: dict[str, str] = Field(..., description="Queried date range (since, until)")


class EntitySelection(BaseModel):
    """Single entity selection path for drilldown queries."""

    account_id: str = Field(..., description="Ad account ID (required)")
    campaign_id: str | None = Field(None, description="Campaign ID (null = aggregate all campaigns)")
    adset_id: str | None = Field(None, description="AdSet ID (null = aggregate all adsets)")
    ad_id: str | None = Field(None, description="Ad ID (null = aggregate all ads)")

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("account_id is required")
        return v.strip()


class InsightsDrilldownRequest(BaseModel):
    """Request model for entity drilldown queries."""

    selections: list[EntitySelection] = Field(
        ...,
        description="List of entity selection paths for filtering.",
        examples=[[
            {"account_id": "act_123", "campaign_id": "camp_456", "adset_id": None, "ad_id": None}
        ]],
        min_length=1,
    )
    level: Literal["campaign", "adset", "ad"] = Field(
        ...,
        description="Target aggregation level: campaign, adset, or ad",
        examples=["ad"],
    )
    since: str = Field(
        ...,
        description="Start date (YYYY-MM-DD)",
        examples=["2025-01-01"],
    )
    until: str = Field(
        ...,
        description="End date (YYYY-MM-DD)",
        examples=["2025-01-31"],
    )
    source: Literal["mongo", "redis", "mongo_redis"] = Field(
        default="mongo_redis",
        description="Data source: mongo (historical), redis (recent), mongo_redis (hybrid)",
    )
