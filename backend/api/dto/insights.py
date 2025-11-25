"""
DTOs for Insights domain (service layer internal data structures).

These DTOs are used for type-safe data transfer between service methods
and routers. They are separate from API models which define external contracts.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateRangeDTO:
    """Date range representation."""

    since: str  # YYYY-MM-DD format
    until: str  # YYYY-MM-DD format


@dataclass
class InsightMetricsDTO:
    """Metrics for a single insight record."""

    spend: float
    impressions: int
    reach: int
    clicks: int
    inline_link_clicks: int
    outbound_clicks: int
    landing_page_view: int
    onsite_web_checkout: int
    onsite_web_add_to_cart: int
    onsite_web_purchase: int
    onsite_web_checkout_value: float
    onsite_web_add_to_cart_value: float
    onsite_web_purchase_value: float

    def to_dict(self) -> dict[str, float | int]:
        """Convert to dictionary format."""
        return {
            "spend": self.spend,
            "impressions": self.impressions,
            "reach": self.reach,
            "clicks": self.clicks,
            "inline_link_clicks": self.inline_link_clicks,
            "outbound_clicks": self.outbound_clicks,
            "landing_page_view": self.landing_page_view,
            "onsite_web_checkout": self.onsite_web_checkout,
            "onsite_web_add_to_cart": self.onsite_web_add_to_cart,
            "onsite_web_purchase": self.onsite_web_purchase,
            "onsite_web_checkout_value": self.onsite_web_checkout_value,
            "onsite_web_add_to_cart_value": self.onsite_web_add_to_cart_value,
            "onsite_web_purchase_value": self.onsite_web_purchase_value,
        }


@dataclass
class InsightRecordDTO:
    """Single insight record with all entity information and metrics."""

    ad_account_id: str
    ad_id: str | None
    adset_id: str | None
    campaign_id: str | None
    ad_name: str | None
    adset_name: str | None
    campaign_name: str | None
    configured_status: str | None
    effective_status: str | None
    date: str  # YYYY-MM-DD format
    metrics: InsightMetricsDTO

    def to_dict(self) -> dict:
        """Convert to dictionary format for API responses."""
        return {
            "ad_account_id": self.ad_account_id,
            "ad_id": self.ad_id,
            "adset_id": self.adset_id,
            "campaign_id": self.campaign_id,
            "ad_name": self.ad_name,
            "adset_name": self.adset_name,
            "campaign_name": self.campaign_name,
            "configured_status": self.configured_status,
            "effective_status": self.effective_status,
            "date": self.date,
            "metrics": self.metrics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InsightRecordDTO":
        """Create DTO from dictionary (typically from service layer dicts)."""
        metrics_data = data.get("metrics", {})
        metrics = InsightMetricsDTO(
            spend=float(metrics_data.get("spend", 0.0)),
            impressions=int(metrics_data.get("impressions", 0)),
            reach=int(metrics_data.get("reach", 0)),
            clicks=int(metrics_data.get("clicks", 0)),
            inline_link_clicks=int(metrics_data.get("inline_link_clicks", 0)),
            outbound_clicks=int(metrics_data.get("outbound_clicks", 0)),
            landing_page_view=int(metrics_data.get("landing_page_view", 0)),
            onsite_web_checkout=int(metrics_data.get("onsite_web_checkout", 0)),
            onsite_web_add_to_cart=int(metrics_data.get("onsite_web_add_to_cart", 0)),
            onsite_web_purchase=int(metrics_data.get("onsite_web_purchase", 0)),
            onsite_web_checkout_value=float(metrics_data.get("onsite_web_checkout_value", 0.0)),
            onsite_web_add_to_cart_value=float(metrics_data.get("onsite_web_add_to_cart_value", 0.0)),
            onsite_web_purchase_value=float(metrics_data.get("onsite_web_purchase_value", 0.0)),
        )

        return cls(
            ad_account_id=data.get("ad_account_id", ""),
            ad_id=data.get("ad_id"),
            adset_id=data.get("adset_id"),
            campaign_id=data.get("campaign_id"),
            ad_name=data.get("ad_name"),
            adset_name=data.get("adset_name"),
            campaign_name=data.get("campaign_name"),
            configured_status=data.get("configured_status"),
            effective_status=data.get("effective_status"),
            date=data.get("date", ""),
            metrics=metrics,
        )


@dataclass
class InsightsResultDTO:
    """
    Complete insights query result from service layer.

    This DTO represents the full response from insights services,
    ready to be converted to API response models.
    """

    insights: list[InsightRecordDTO]
    date_range: DateRangeDTO
    last_synced_date: str | None = None

    @property
    def total_records(self) -> int:
        """Total number of insight records."""
        return len(self.insights)

    def to_dict(self) -> dict:
        """Convert to dictionary format for API responses."""
        return {
            "insights": [insight.to_dict() for insight in self.insights],
            "total_records": self.total_records,
            "date_range": {
                "since": self.date_range.since,
                "until": self.date_range.until,
            },
            "last_synced_date": self.last_synced_date,
        }

    @classmethod
    def from_service_dict(cls, data: dict) -> "InsightsResultDTO":
        """
        Create DTO from service layer dictionary response.

        This is a bridge method to transition from dict-based services
        to DTO-based services.
        """
        insights_list = data.get("insights", [])
        date_range_data = data.get("date_range", {})

        return cls(
            insights=[InsightRecordDTO.from_dict(insight) for insight in insights_list],
            date_range=DateRangeDTO(
                since=date_range_data.get("since", ""),
                until=date_range_data.get("until", ""),
            ),
            last_synced_date=data.get("last_synced_date"),
        )
