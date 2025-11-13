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
        if value is None:
            return value
        pattern = r"\d{2}:\d{2}:\d{2}"
        if re.fullmatch(pattern, value):
            return value
        raise ValueError(
            "cache_window_hint must follow dd:hh:mm format, for example '12:14:30'."
        )


class InsightsResponse(BaseModel):
    """Response model for insights data."""

    insights: list[InsightRecord] = Field(..., description="List of insight records")
    total_records: int = Field(..., description="Total number of insight records")
    date_range: dict[str, str] = Field(
        ..., description="Date range of the data (since, until)"
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
    """Response payload for the sync entity names endpoint."""

    synced: int = Field(..., description="Number of entities successfully synced")
    failed: int = Field(..., description="Number of entities that failed to sync")
    total: int = Field(..., description="Total entity count in the request")
    rate_limited: int = Field(..., description="Number of rate limit events detected")
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
