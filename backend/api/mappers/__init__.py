"""
Mappers to convert between DTOs (internal) and API models (external contracts).

These mappers provide clean separation between service layer data structures
and API response models, making it easier to change either independently.
"""

from api.dto.insights import InsightsResultDTO, InsightRecordDTO, InsightMetricsDTO
from api.models.insights import InsightsResponse, InsightRecord, InsightMetrics


def insights_result_dto_to_response(dto: InsightsResultDTO) -> dict:
    """
    Convert InsightsResultDTO to API response dictionary.

    This mapper converts internal DTO to the format expected by
    the API response model (InsightsResponse).

    Args:
        dto: Internal insights result DTO from service layer

    Returns:
        Dictionary matching InsightsResponse structure
    """
    return {
        "insights": [_insight_record_dto_to_dict(record) for record in dto.insights],
        "total_records": dto.total_records,
        "date_range": {
            "since": dto.date_range.since,
            "until": dto.date_range.until,
        },
        "last_synced_date": dto.last_synced_date,
    }


def _insight_record_dto_to_dict(dto: InsightRecordDTO) -> dict:
    """Convert InsightRecordDTO to dictionary matching InsightRecord model."""
    return {
        "ad_account_id": dto.ad_account_id,
        "ad_id": dto.ad_id,
        "adset_id": dto.adset_id,
        "campaign_id": dto.campaign_id,
        "ad_name": dto.ad_name,
        "adset_name": dto.adset_name,
        "campaign_name": dto.campaign_name,
        "configured_status": dto.configured_status,
        "effective_status": dto.effective_status,
        "date": dto.date,
        "metrics": _metrics_dto_to_dict(dto.metrics),
    }


def _metrics_dto_to_dict(dto: InsightMetricsDTO) -> dict:
    """Convert InsightMetricsDTO to dictionary matching InsightMetrics model."""
    return {
        "spend": dto.spend,
        "impressions": dto.impressions,
        "reach": dto.reach,
        "clicks": dto.clicks,
        "inline_link_clicks": dto.inline_link_clicks,
        "outbound_clicks": dto.outbound_clicks,
        "landing_page_view": dto.landing_page_view,
        "onsite_web_checkout": dto.onsite_web_checkout,
        "onsite_web_add_to_cart": dto.onsite_web_add_to_cart,
        "onsite_web_purchase": dto.onsite_web_purchase,
        "onsite_web_checkout_value": dto.onsite_web_checkout_value,
        "onsite_web_add_to_cart_value": dto.onsite_web_add_to_cart_value,
        "onsite_web_purchase_value": dto.onsite_web_purchase_value,
    }
