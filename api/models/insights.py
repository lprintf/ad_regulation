"""
Request and response models for Insights endpoints.
"""

from enum import Enum

from pydantic import BaseModel, Field


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

    ad_id: str = Field(..., description="Ad ID")
    date: str = Field(..., description="Date of the insight (YYYY-MM-DD or datetime)")
    metrics: InsightMetrics = Field(..., description="Insight metrics")


# Keep DailyInsight as alias for backward compatibility
DailyInsight = InsightRecord


class InsightsRequest(BaseModel):
    """Request model for fetching insights (used for POST async endpoint)."""

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
