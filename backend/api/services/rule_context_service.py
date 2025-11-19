"""
Utility service to build execution context with real advertising data.
Fetches ad metadata and insights metrics without mutating delivery status.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adsinsights import AdsInsights

from utils.db import RuleBindingDocument
from utils.fb_api_flyweight_factory import get_api


class RuleContextService:
    """Builds contextual data for rule execution."""

    LAST_N_DAYS = 14

    @staticmethod
    async def build_context(binding: RuleBindingDocument | None) -> dict[str, Any]:
        if binding is None:
            return {}

        if binding.entity_type == "ad":
            return await RuleContextService._build_ad_context(binding)

        return {
            "rule_name": binding.rule_name,
            "entity_id": binding.entity_id,
            "entity_type": binding.entity_type,
            "metadata": binding.metadata,
            "notes": ["No specialised context builder for this entity type."],
        }

    @staticmethod
    async def _build_ad_context(binding: RuleBindingDocument) -> dict[str, Any]:
        ad_account_id = binding.metadata.get("ad_account_id")
        if not ad_account_id:
            raise ValueError(
                "Rule binding metadata must include 'ad_account_id' for ad entities"
            )

        api = await get_api(ad_account_id)
        ad = Ad(binding.entity_id, api=api)

        fetch_errors: list[str] = []
        ad_details: dict[str, Any] = {}
        targeting_countries: list[str] = []

        async def _fetch_ad_details() -> tuple[dict[str, Any], list[str]]:
            fields = [
                Ad.Field.id,
                Ad.Field.name,
                Ad.Field.account_id,
                Ad.Field.configured_status,
                Ad.Field.effective_status,
                Ad.Field.created_time,
                Ad.Field.updated_time,
                Ad.Field.targeting,
            ]

            def _call() -> dict[str, Any]:
                return ad.api_get(fields=fields)

            raw_details = await asyncio.to_thread(_call)
            details = {
                "ad_id": raw_details.get(Ad.Field.id),
                "name": raw_details.get(Ad.Field.name),
                "account_id": raw_details.get(Ad.Field.account_id),
                "configured_status": raw_details.get(Ad.Field.configured_status),
                "effective_status": raw_details.get(Ad.Field.effective_status),
                "created_time": raw_details.get(Ad.Field.created_time),
                "updated_time": raw_details.get(Ad.Field.updated_time),
            }

            targeting = raw_details.get(Ad.Field.targeting) or {}
            countries = (
                targeting.get("geo_locations", {}).get("countries")
                if isinstance(targeting, dict)
                else None
            )
            return details, list(countries or [])

        async def _fetch_insights() -> list[dict[str, Any]]:
            since = (
                datetime.utcnow() - timedelta(days=RuleContextService.LAST_N_DAYS)
            ).strftime("%Y-%m-%d")
            until = datetime.utcnow().strftime("%Y-%m-%d")

            fields = [
                AdsInsights.Field.spend,
                AdsInsights.Field.clicks,
                AdsInsights.Field.impressions,
            ]

            def _call() -> list[dict[str, Any]]:
                results = ad.get_insights(
                    fields=fields,
                    params={
                        "time_range": {"since": since, "until": until},
                        "time_increment": 1,
                    },
                )
                rows: list[dict[str, Any]] = []
                for item in results:
                    rows.append(
                        {
                            "spend": float(item.get(AdsInsights.Field.spend, 0) or 0),
                            "clicks": int(item.get(AdsInsights.Field.clicks, 0) or 0),
                            "impressions": int(
                                item.get(AdsInsights.Field.impressions, 0) or 0
                            ),
                            "date_start": item.get("date_start"),
                            "date_stop": item.get("date_stop"),
                        }
                    )
                return rows

            return await asyncio.to_thread(_call)

        details_result, insights_result = await asyncio.gather(
            _fetch_ad_details(), _fetch_insights(), return_exceptions=True
        )

        if isinstance(details_result, Exception):
            fetch_errors.append(f"Ad details fetch error: {details_result}")
        else:
            ad_details, targeting_countries = details_result

        if isinstance(insights_result, Exception):
            fetch_errors.append(f"Ad insights fetch error: {insights_result}")
            insights_rows = []
        else:
            insights_rows = insights_result

        # Aggregate metrics
        total_spend = sum(row["spend"] for row in insights_rows)
        total_clicks = sum(row["clicks"] for row in insights_rows)
        total_impressions = sum(row["impressions"] for row in insights_rows)

        ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
        cpc = (total_spend / total_clicks) if total_clicks else None

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
                "currency": "USD",  # Facebook insights normalised currency
                "window": {
                    "since": insights_rows[0]["date_start"] if insights_rows else None,
                    "until": insights_rows[-1]["date_stop"] if insights_rows else None,
                    "days": RuleContextService.LAST_N_DAYS,
                },
                "daily_samples": insights_rows,
            },
            "fetch_errors": fetch_errors,
        }
