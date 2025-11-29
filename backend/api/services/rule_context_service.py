"""
Utility service to build execution context with real advertising data.
Fetches insights metrics from MongoDB+Redis hybrid cache for fast, realtime execution.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from facebook_business.adobjects.ad import Ad

from utils.db import RuleBindingDocument, AdEntityNamesDocument

logger = logging.getLogger(__name__)


class RuleContextService:
    """Builds contextual data for rule execution."""

    LAST_N_DAYS = 14  # Default fallback

    @staticmethod
    async def build_context(
        binding: RuleBindingDocument | None,
        params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if binding is None:
            return {}

        if binding.entity_type == "ad":
            return await RuleContextService._build_ad_context(binding, params)

        return {
            "rule_name": binding.rule_name,
            "entity_id": binding.entity_id,
            "entity_type": binding.entity_type,
            "metadata": binding.metadata,
            "notes": ["No specialised context builder for this entity type."],
        }

    @staticmethod
    async def _build_ad_context(
        binding: RuleBindingDocument,
        params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Build context for ad entity using MongoDB+Redis hybrid insights.
        Fast and realtime - combines historical (MongoDB) + recent (Redis) data.
        """
        from api.services.insights_service import InsightsService

        ad_account_id = binding.metadata.get("ad_account_id")
        if not ad_account_id:
            raise ValueError(
                "Rule binding metadata must include 'ad_account_id' for ad entities"
            )

        ad_id = binding.entity_id
        fetch_errors: list[str] = []

        # Use lookback_days from params if provided, otherwise use default
        lookback_days = RuleContextService.LAST_N_DAYS
        if params and "lookback_days" in params:
            lookback_days = int(params["lookback_days"])

        # Support evaluation_date for historical simulation
        reference_date = datetime.utcnow()
        if params and params.get("evaluation_date"):
            try:
                from datetime import datetime as dt
                evaluation_date_str = params["evaluation_date"]
                reference_date = dt.strptime(evaluation_date_str, "%Y-%m-%d")
                logger.info(
                    "Using evaluation_date=%s for historical simulation",
                    evaluation_date_str
                )
            except Exception as exc:
                logger.warning(
                    "Invalid evaluation_date format '%s', using current date: %s",
                    params.get("evaluation_date"),
                    exc
                )

        # Query ad entity metadata from MongoDB
        ad_entity = await AdEntityNamesDocument.find_one(
            AdEntityNamesDocument.account_id == ad_account_id,
            AdEntityNamesDocument.entity_type == "ad",
            AdEntityNamesDocument.entity_id == ad_id
        )

        ad_details: dict[str, Any] = {
            "ad_id": ad_id,
            "name": ad_entity.entity_name if ad_entity else None,
            "account_id": ad_account_id,
            "configured_status": ad_entity.configured_status if ad_entity else None,
            "effective_status": ad_entity.effective_status if ad_entity else None,
        }

        # Query insights from MongoDB+Redis hybrid (last N days from reference_date)
        since = reference_date - timedelta(days=lookback_days)
        until = reference_date

        since_str = since.strftime("%Y-%m-%d")
        until_str = until.strftime("%Y-%m-%d")

        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since_str,
                until=until_str,
                level="ad",
                time_increment=1,
                object_level="ad",
                object_ids=[ad_id],
                mask_ad_ids=False,
            )

            # Extract insights records
            insights_records = insights_data.get("insights", [])

            if not insights_records:
                logger.warning(
                    "No insights data found for ad_id=%s in last %d days",
                    ad_id,
                    lookback_days
                )
                fetch_errors.append(
                    f"No insights data found for ad {ad_id}"
                )

        except Exception as exc:
            logger.error(
                "Failed to fetch insights for ad %s: %s", ad_id, exc, exc_info=True
            )
            fetch_errors.append(f"Failed to fetch insights: {exc}")
            insights_records = []

        # Transform to daily samples format
        insights_rows: list[dict[str, Any]] = []
        for record in insights_records:
            metrics = record.get("metrics", {})
            insights_rows.append({
                "spend": metrics.get("spend", 0),
                "clicks": metrics.get("clicks", 0),
                "impressions": metrics.get("impressions", 0),
                "reach": metrics.get("reach", 0),
                "inline_link_clicks": metrics.get("inline_link_clicks", 0),
                "outbound_clicks": metrics.get("outbound_clicks", 0),
                "landing_page_view": metrics.get("landing_page_view", 0),
                "onsite_web_purchase": metrics.get("onsite_web_purchase", 0),
                "onsite_web_purchase_value": metrics.get("onsite_web_purchase_value", 0),
                "date_start": record.get("date"),
                "date_stop": record.get("date"),
            })

        # Aggregate metrics
        total_spend = sum(row["spend"] for row in insights_rows)
        total_clicks = sum(row["clicks"] for row in insights_rows)
        total_impressions = sum(row["impressions"] for row in insights_rows)

        ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
        cpc = (total_spend / total_clicks) if total_clicks else None

        # Try to get targeting info from metadata or Facebook API (lightweight call)
        targeting_countries: list[str] = []
        try:
            from utils.fb_api_flyweight_factory import get_api
            api = await get_api(ad_account_id)
            ad = Ad(ad_id, api=api)

            def _fetch_targeting() -> list[str]:
                ad_data = ad.api_get(fields=[Ad.Field.targeting])
                targeting = ad_data.get(Ad.Field.targeting) or {}
                countries = (
                    targeting.get("geo_locations", {}).get("countries")
                    if isinstance(targeting, dict)
                    else None
                )
                return list(countries or [])

            targeting_countries = await asyncio.to_thread(_fetch_targeting)
        except Exception as exc:
            logger.warning(
                "Failed to fetch targeting for ad %s: %s", ad_id, exc
            )
            # Don't add to fetch_errors since this is optional

        return {
            "rule_name": binding.rule_name,
            "entity_type": binding.entity_type,
            "entity_id": binding.entity_id,
            "metadata": binding.metadata,
            "ad": ad_details,
            "targeting": {
                "countries": targeting_countries,
            },
            "performance": {
                "spend": total_spend,
                "clicks": total_clicks,
                "impressions": total_impressions,
                "ctr": ctr,
                "ctr_unit": "percent",
                "cpc": cpc,
                "currency": "USD",
                "window": {
                    "since": insights_rows[0]["date_start"] if insights_rows else None,
                    "until": insights_rows[-1]["date_stop"] if insights_rows else None,
                    "days": lookback_days,
                },
                "daily_samples": insights_rows,
            },
            "fetch_errors": fetch_errors,
        }
