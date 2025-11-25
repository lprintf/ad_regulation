"""
Service layer for Insights data operations.
Encapsulates business logic for fetching and processing Facebook Ads Insights.
"""

import asyncio
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Literal, Tuple

from facebook_business.adobjects.adreportrun import AdReportRun
from beanie.operators import In

from baseline.get_data import insight_to_df
from api.services.insights_sync_service import REALTIME_LOOKBACK_DAYS
from utils.db import (
    InsightsDailyDocument,
    AdEntityNamesDocument,
    InsightsSyncStateDocument,
    get_document_collection
)
from utils.account_id import normalize_account_id, remove_account_id_prefix
from utils.fb_api_flyweight_factory import get_ad_object, get_api
from utils.insight_tool import ATOMIC_FIELDS, get_insight
from utils.redis_client import get_insights_from_cache

logger = logging.getLogger(__name__)


FROM_LAST_CACHE_TTL_SECONDS = 60
_from_last_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_from_last_cache_lock = asyncio.Lock()

OBJECT_LEVEL_TO_FIELD: dict[str, str] = {
    "ad": "ad_id",
    "adset": "adset_id",
    "campaign": "campaign_id",
}

UNSUPPORTED_GRAPH_FIELDS: set[str] = {
    "configured_status",
    "effective_status",
}


def _normalize_cache_key_fields(fields: list[str] | None) -> str:
    if not fields:
        return ""
    return ",".join(sorted(fields))


def _normalize_filter_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized = []
    for value in values:
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _resolve_object_filter(
    object_level: str | None, object_ids: list[str] | None
) -> tuple[str, list[str]] | None:
    if not object_level or not object_ids:
        return None
    field_name = OBJECT_LEVEL_TO_FIELD.get(object_level)
    if not field_name:
        return None
    normalized_ids = _normalize_filter_ids(object_ids)
    if not normalized_ids:
        return None
    return field_name, normalized_ids


def _filter_insights_by_objects(
    insights_list: list[dict[str, Any]],
    object_level: str | None,
    object_ids: list[str] | None,
) -> list[dict[str, Any]]:
    resolved = _resolve_object_filter(object_level, object_ids)
    if not resolved:
        return insights_list
    field_name, normalized_ids = resolved
    normalized_set = set(normalized_ids)
    filtered = [
        insight
        for insight in insights_list
        if str(insight.get(field_name) or "").strip() in normalized_set
    ]
    return filtered


def _sum_numeric_expression(field: str) -> dict[str, Any]:
    """
    Build an aggregation expression that safely sums numeric values stored
    either as numbers or numeric strings.
    """
    return {
        "$sum": {
            "$toDouble": {
                "$ifNull": [f"${field}", 0]
            }
        }
    }



def _build_from_last_cache_key(
    *,
    ad_account_id: str,
    until: str,
    level: str,
    time_increment: int | None,
    breakdowns: str | None,
    fields: list[str] | None,
    object_level: str | None,
    object_ids: list[str] | None,
    cache_window_hint: str | None,
) -> str:
    parts = [
        ad_account_id.lower(),
        until,
        level,
        str(time_increment) if time_increment is not None else "null",
        breakdowns or "",
        _normalize_cache_key_fields(fields),
        object_level or "",
        ",".join(_normalize_filter_ids(object_ids)) if object_ids else "",
        cache_window_hint or "",
    ]
    return "|".join(parts)


async def _get_from_last_cache(key: str) -> dict[str, Any] | None:
    if not key:
        return None
    async with _from_last_cache_lock:
        entry = _from_last_cache.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        now = asyncio.get_running_loop().time()
        if expires_at <= now:
            _from_last_cache.pop(key, None)
            return None
        return payload


async def _set_from_last_cache(key: str, payload: dict[str, Any]) -> None:
    if not key:
        return
    ttl = FROM_LAST_CACHE_TTL_SECONDS
    async with _from_last_cache_lock:
        _from_last_cache[key] = (
            asyncio.get_running_loop().time() + ttl,
            payload,
        )


async def _get_insights_from_redis_range(
    account_id: str,
    since_date: date,
    until_date: date,
) -> list[dict[str, Any]]:
    """
    Get insights data from Redis cache for a date range.

    Args:
        account_id: Ad account ID (normalized with act_ prefix)
        since_date: Start date
        until_date: End date

    Returns:
        List of insight records from Redis cache (normalized to match DB format)
    """
    insights_list = []
    current_date = since_date

    while current_date <= until_date:
        date_str = current_date.isoformat()
        try:
            daily_insights = await get_insights_from_cache(account_id, date_str)
            # Normalize Redis data format to match DB format
            # Redis data now comes pre-formatted from cache_insights_for_date with:
            # - 'date' field (and also 'date_start' for compatibility)
            # - metrics wrapped in 'metrics' dict
            for insight in daily_insights:
                # Ensure date field exists (should already be there from cache_insights_for_date)
                if "date" not in insight and "date_start" in insight:
                    date_value = insight["date_start"]
                    if isinstance(date_value, str):
                        insight["date"] = date_value
                    elif isinstance(date_value, date):
                        insight["date"] = date_value.strftime("%Y-%m-%d")
                    else:
                        insight["date"] = date_str
                # Ensure ad_account_id is present
                if "ad_account_id" not in insight and "account_id" in insight:
                    insight["ad_account_id"] = normalize_account_id(insight["account_id"])
            insights_list.extend(daily_insights)
            logger.debug(f"Retrieved {len(daily_insights)} insights from Redis for {account_id} on {date_str}")
        except Exception as exc:
            logger.warning(f"Failed to get insights from Redis for {account_id} on {date_str}: {exc}")

        current_date += timedelta(days=1)

    return insights_list


class InsightsService:
    """Service for fetching and processing Facebook Ads Insights data."""

    @staticmethod
    def _validate_date(date_str: str, field_name: str) -> None:
        """
        Validate date string format and value.

        Args:
            date_str: Date string in YYYY-MM-DD format
            field_name: Name of the field for error messages

        Raises:
            ValueError: If date is invalid
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(
                f"Invalid {field_name}: '{date_str}'. Must be a valid date in YYYY-MM-DD format. Error: {e}"
            )

    @staticmethod
    async def query_insights_realtime(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Query insights data by combining cached (DB) and realtime Facebook API data.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (ad, adset, or campaign)
            time_increment: Time increment (1=daily, None=aggregate)
            breakdowns: Comma-separated breakdown dimensions
            fields: Additional fields requested from Facebook API (e.g., entity names)
            object_level: Level of object_ids filter (ad, adset, campaign)
            object_ids: Specific entity IDs to limit the query scope

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If parameters are invalid
            Exception: If Facebook API call fails
        """
        # Normalize account ID
        account_id = normalize_account_id(ad_account_id)
        # Remove act_ prefix for database query (DB stores account_id without prefix)
        account_id_without_prefix = remove_account_id_prefix(account_id)

        # Validate dates
        since_date = InsightsService._parse_date(since, "since date")
        until_date = InsightsService._parse_date(until, "until date")
        if since_date > until_date:
            raise ValueError("since date must be on or before until date")

        # Validate level
        valid_levels = ["ad", "adset", "campaign", "account"]
        if level not in valid_levels:
            raise ValueError(
                f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )

        object_filter = _resolve_object_filter(object_level, object_ids)

        needs_aggregation = level in {"account", "campaign", "adset"}
        fetch_level = "ad" if needs_aggregation else level

        should_use_historical = (
            time_increment == 1
            and (not breakdowns or not breakdowns.strip())
        )

        historical_records: Dict[Tuple[str, str], dict[str, Any]] = {}
        realtime_since = since_date

        if should_use_historical:
            realtime_cutoff = datetime.utcnow().date() - timedelta(
                days=REALTIME_LOOKBACK_DAYS
            )
            historical_until = min(until_date, realtime_cutoff)

            if since_date <= historical_until:
                historical_payload = await InsightsService.query_insights_mongo_only(
                    ad_account_id=account_id,
                    since=since_date.strftime("%Y-%m-%d"),
                    until=historical_until.strftime("%Y-%m-%d"),
                    level=level,
                    time_increment=time_increment,
                    breakdowns=breakdowns,
                    object_level=object_level,
                    object_ids=object_ids,
                )

                for insight_record in historical_payload["insights"]:
                    historical_records[
                        InsightsService._key_for_insight(insight_record)
                    ] = insight_record

                realtime_since = historical_until + timedelta(days=1)

        requested_fields = [
            field
            for field in (fields or [])
            if field not in UNSUPPORTED_GRAPH_FIELDS
        ]
        base_fields = ["ad_id", "account_id", *ATOMIC_FIELDS]
        required_fields = []
        if fetch_level == "ad":
            required_fields.extend(["adset_id", "campaign_id"])
        api_fields: list[str] = list(
            dict.fromkeys(base_fields + requested_fields + required_fields)
        )
        non_metric_fields = {
            "adset_id",
            "campaign_id",
            "ad_name",
            "adset_name",
            "campaign_name",
            "configured_status",
            "effective_status",
        }
        extra_fields_for_df = [
            field for field in api_fields if field in non_metric_fields
        ]

        api_records: list[dict[str, Any]] = []
        if realtime_since <= until_date:
            ad_object = await get_ad_object(account_id, account_id)

            try:
                insights = get_insight(
                    adobject=ad_object,
                    fields=api_fields,
                    level=fetch_level,
                    since=realtime_since.strftime("%Y-%m-%d"),
                    until=until_date.strftime("%Y-%m-%d"),
                    time_increment=time_increment,
                    breakdowns=breakdowns or "",
                    is_async=False,
                )

                df = insight_to_df(insights, extra_fields=extra_fields_for_df)
                api_records = InsightsService._df_to_insights_list(df)
                for record in api_records:
                    if not record.get("ad_account_id"):
                        record["ad_account_id"] = account_id
                if needs_aggregation:
                    api_records = InsightsService._aggregate_records_for_level(
                        api_records,
                        target_level=level,
                        account_id=account_id_without_prefix,
                    )
            except Exception as exc:
                if historical_records:
                    print(
                        f"Error fetching realtime insights for account {account_id}: {exc}. Returning historical data only."
                    )
                else:
                    raise Exception(f"Failed to fetch insights: {str(exc)}") from exc

        combined: Dict[Tuple[str, str], dict[str, Any]] = dict(historical_records)
        for record in api_records:
            combined[InsightsService._key_for_insight(record)] = record

        insights_list = sorted(
            combined.values(),
            key=lambda item: (item["date"], item["ad_id"]),
        )

        insights_list = _filter_insights_by_objects(
            insights_list,
            object_level,
            object_ids,
        )

        insights_list = await InsightsService._attach_entity_names(
            insights_list, level, account_id_without_prefix
        )

        if level != "ad":
            insights_list = [
                {**insight, "ad_id": None}
                for insight in insights_list
            ]

        return {
            "insights": insights_list,
            "total_records": len(insights_list),
            "date_range": {"since": since, "until": until},
        }

    @staticmethod
    async def query_insights_from_last_gap(
        ad_account_id: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        cache_window_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch insights by automatically setting the realtime window to
        (last_synced_until + 1 day) → requested until.
        """
        account_id = normalize_account_id(ad_account_id)
        account_id_without_prefix = remove_account_id_prefix(account_id)

        until_date = InsightsService._parse_date(until, "until date")
        state = await InsightsSyncStateDocument.find_one(
            InsightsSyncStateDocument.account_id == account_id_without_prefix
        )

        last_synced_date: date | None = None
        if state:
            last_synced_source = (
                state.last_synced_date
                or state.range_until
                or state.obs_until
            )
            last_synced_date = InsightsService._normalize_state_date(last_synced_source)

        cache_key: str | None = None
        if cache_window_hint:
            cache_key = _build_from_last_cache_key(
                ad_account_id=account_id,
                until=until,
                level=level,
                time_increment=time_increment,
                breakdowns=breakdowns,
                fields=fields,
                object_level=object_level,
                object_ids=object_ids,
                cache_window_hint=cache_window_hint,
            )
            cached_result = await _get_from_last_cache(cache_key)
            if cached_result:
                return cached_result

        if not last_synced_date:
            last_synced_date = await _resolve_latest_synced_date(
                account_id_without_prefix
            )

        if last_synced_date:
            realtime_since_date = last_synced_date + timedelta(days=1)
            if realtime_since_date > until_date:
                return {
                    "insights": [],
                    "total_records": 0,
                    "date_range": {
                        "since": until_date.strftime("%Y-%m-%d"),
                        "until": until_date.strftime("%Y-%m-%d"),
                    },
                }
        else:
            fallback_window = max(REALTIME_LOOKBACK_DAYS, 1)
            realtime_since_date = until_date - timedelta(days=fallback_window)
            if realtime_since_date < until_date - timedelta(days=90):
                realtime_since_date = until_date - timedelta(days=90)
            if realtime_since_date > until_date:
                realtime_since_date = until_date

        since_str = realtime_since_date.strftime("%Y-%m-%d")
        result = await InsightsService.query_insights_realtime(
            ad_account_id=account_id,
            since=since_str,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            fields=fields,
            object_level=object_level,
            object_ids=object_ids,
        )
        if cache_key:
            await _set_from_last_cache(cache_key, result)
        return result

    @staticmethod
    async def query_insights_hybrid(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        fields: list[str] | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        cache_window_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Combine database data with realtime gap fill in a single response.
        This mirrors the old frontend hybrid merge while keeping deduplication server-side.
        """

        account_id = normalize_account_id(ad_account_id)

        db_task = InsightsService.query_insights_mongo_only(
            ad_account_id=account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=False,
        )
        realtime_task = InsightsService.query_insights_from_last_gap(
            ad_account_id=account_id,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            fields=fields,
            object_level=object_level,
            object_ids=object_ids,
            cache_window_hint=cache_window_hint,
        )

        db_result, realtime_result = await asyncio.gather(db_task, realtime_task)

        def _record_key(record: dict[str, Any]) -> str:
            entity_value = (
                record.get("ad_id")
                or record.get("adset_id")
                or record.get("campaign_id")
                or record.get("ad_account_id")
                or ""
            )
            return f"{record.get('date')}|{entity_value}"

        merged: dict[str, dict[str, Any]] = {}
        for insight in db_result["insights"]:
            merged[_record_key(insight)] = insight
        for insight in realtime_result["insights"]:
            merged[_record_key(insight)] = insight

        merged_list = sorted(
            merged.values(),
            key=lambda item: (
                item.get("date"),
                item.get("ad_id")
                or item.get("adset_id")
                or item.get("campaign_id")
                or item.get("ad_account_id"),
            ),
        )

        filtered_list = _filter_insights_by_objects(
            merged_list,
            object_level,
            object_ids,
        )

        return {
            "insights": filtered_list,
            "total_records": len(filtered_list),
            "date_range": {"since": since, "until": until},
        }

    @staticmethod
    async def create_async_job(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an async insights job in Facebook API.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (ad, adset, or campaign)
            time_increment: Time increment (1=daily, None=aggregate)
            breakdowns: Comma-separated breakdown dimensions

        Returns:
            Dictionary with job_id, status, and metadata

        Raises:
            ValueError: If parameters are invalid
            Exception: If Facebook API call fails
        """
        # Normalize account ID
        account_id = normalize_account_id(ad_account_id)

        # Validate dates
        InsightsService._validate_date(since, "since date")
        InsightsService._validate_date(until, "until date")

        # Validate level
        valid_levels = ["account", "campaign", "adset", "ad"]
        if level not in valid_levels:
            raise ValueError(
                f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )

        # Get ad object
        ad_object = await get_ad_object(account_id, account_id)

        # Prepare fields
        fields = ["ad_id", *ATOMIC_FIELDS]

        try:
            # Create async job
            async_job = get_insight(
                adobject=ad_object,
                fields=fields,
                level=level,
                since=since,
                until=until,
                time_increment=time_increment,
                breakdowns=breakdowns or "",
                is_async=True,
            )

            # Refresh the job object to get initial status
            async_job.api_get()

            # Extract job info
            job_id = async_job.get(AdReportRun.Field.id) or async_job.get(
                "report_run_id"
            )

            # Get status after refresh
            status = async_job.get(AdReportRun.Field.async_status, "Job Not Started")

            return {
                "job_id": job_id,
                "ad_account_id": account_id,
                "status": status,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"Error creating async job for account {account_id}: {e}")
            raise Exception(f"Failed to create async job: {str(e)}") from e

    @staticmethod
    async def check_job_status(ad_account_id: str, job_id: str) -> dict[str, Any]:
        """
        Check the status of an async insights job.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            job_id: Facebook async job ID

        Returns:
            Dictionary with job status and progress

        Raises:
            Exception: If Facebook API call fails
        """
        # Normalize account ID
        account_id = normalize_account_id(ad_account_id)

        try:
            # Get API instance for this ad account
            print(f"[DEBUG] Getting API for account_id: {account_id}, job_id: {job_id}")
            api = await get_api(account_id)
            print(f"[DEBUG] API instance obtained: {api}")

            # Create and fetch AdReportRun status
            print(f"[DEBUG] Creating AdReportRun for job_id: {job_id}")
            async_job = AdReportRun(job_id, api=api)
            async_job.api_get()
            print("[DEBUG] AdReportRun fetched successfully")
            job_dict = {**async_job}
            print(f"[DEBUG] Job Details: {job_dict}")

            # Safely get status fields
            status = async_job.get(AdReportRun.Field.async_status, "Unknown")
            percent_complete = int(
                async_job.get(AdReportRun.Field.async_percent_completion, 0)
            )

            # Convert time_ref (Unix timestamp) to ISO format string
            time_ref = async_job.get(AdReportRun.Field.time_ref)
            created_at = (
                datetime.fromtimestamp(time_ref).isoformat() if time_ref else None
            )

            return {
                "job_id": job_id,
                "ad_account_id": account_id,
                "status": status,
                "percent_complete": percent_complete,
                "created_at": created_at,
                "updated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            error_msg = str(e)
            print(f"Error checking job status for job {job_id}: {error_msg}")

            # Check if it's a "does not exist" error
            if "does not exist" in error_msg or "cannot be loaded" in error_msg:
                raise ValueError(f"Job {job_id} not found or inaccessible") from e

            raise Exception(f"Failed to check job status: {error_msg}") from e

    @staticmethod
    async def get_job_result(ad_account_id: str, job_id: str) -> dict[str, Any]:
        """
        Get the result of a completed async insights job.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            job_id: Facebook async job ID

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If job is not completed
            Exception: If Facebook API call fails
        """
        # Normalize account ID
        account_id = normalize_account_id(ad_account_id)

        try:
            # Get API instance for this ad account
            api = await get_api(account_id)

            # Create and fetch AdReportRun results
            async_job = AdReportRun(job_id, api=api)
            async_job.api_get()

            status = async_job.get(AdReportRun.Field.async_status, "Unknown")

            # Check if job is completed
            if status != "Job Completed":
                raise ValueError(f"Job is not completed yet. Current status: {status}")

            # Get insights from completed job
            insights_cursor = async_job.get_insights()
            df = insight_to_df(insights_cursor)

            # Convert DataFrame to list of dictionaries
            insights_list = InsightsService._df_to_insights_list(df)

            # Extract date range from job metadata
            date_start = async_job.get(AdReportRun.Field.date_start, "")
            date_stop = async_job.get(AdReportRun.Field.date_stop, "")

            return {
                "insights": insights_list,
                "total_records": len(insights_list),
                "date_range": {"since": date_start, "until": date_stop},
            }

        except ValueError:
            raise
        except Exception as e:
            print(f"Error getting job result for job {job_id}: {e}")
            raise Exception(f"Failed to get job result: {str(e)}") from e

    @staticmethod
    def _df_to_insights_list(df) -> list[dict[str, Any]]:
        """Convert DataFrame to list of insight dictionaries."""
        insights_list = []
        columns = set(df.columns)
        has_account_id = "account_id" in columns
        has_adset_id = "adset_id" in columns
        has_campaign_id = "campaign_id" in columns
        has_ad_name = "ad_name" in columns
        has_adset_name = "adset_name" in columns
        has_campaign_name = "campaign_name" in columns
        has_configured_status = "configured_status" in columns
        has_effective_status = "effective_status" in columns

        def _normalize_optional(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, float) and math.isnan(value):
                return None
            text = str(value).strip()
            return text or None

        def _safe_get_metric(row, field: str, default: float | int, as_type: type):
            """Safely get metric value from row with fallback to default."""
            if field not in columns:
                return as_type(default)
            value = row.get(field, default)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                return as_type(default)
            return as_type(value)

        for _, row in df.iterrows():
            insight_record = {
                "ad_account_id": normalize_account_id(
                    str(row["account_id"])
                )
                if has_account_id and row.get("account_id") is not None
                else None,
                "ad_id": str(row["ad_id"]),
                "adset_id": None,
                "campaign_id": None,
                "ad_name": None,
                "adset_name": None,
                "campaign_name": None,
                "configured_status": None,
                "effective_status": None,
                "date": str(row["date_start"]),
                "metrics": {
                    "spend": _safe_get_metric(row, "spend", 0.0, float),
                    "impressions": _safe_get_metric(row, "impressions", 0, int),
                    "reach": _safe_get_metric(row, "reach", 0, int),
                    "clicks": _safe_get_metric(row, "clicks", 0, int),
                    "inline_link_clicks": _safe_get_metric(row, "inline_link_clicks", 0, int),
                    "outbound_clicks": _safe_get_metric(row, "outbound_clicks", 0, int),
                    "landing_page_view": _safe_get_metric(row, "landing_page_view", 0, int),
                    "onsite_web_checkout": _safe_get_metric(row, "onsite_web_checkout", 0, int),
                    "onsite_web_add_to_cart": _safe_get_metric(row, "onsite_web_add_to_cart", 0, int),
                    "onsite_web_purchase": _safe_get_metric(row, "onsite_web_purchase", 0, int),
                    "onsite_web_checkout_value": _safe_get_metric(row, "onsite_web_checkout_value", 0.0, float),
                    "onsite_web_add_to_cart_value": _safe_get_metric(row, "onsite_web_add_to_cart_value", 0.0, float),
                    "onsite_web_purchase_value": _safe_get_metric(row, "onsite_web_purchase_value", 0.0, float),
                },
            }

            if has_adset_id:
                insight_record["adset_id"] = _normalize_optional(row["adset_id"])
            if has_campaign_id:
                insight_record["campaign_id"] = _normalize_optional(row["campaign_id"])
            if has_ad_name:
                insight_record["ad_name"] = _normalize_optional(row["ad_name"])
            if has_adset_name:
                insight_record["adset_name"] = _normalize_optional(row["adset_name"])
            if has_campaign_name:
                insight_record["campaign_name"] = _normalize_optional(
                    row["campaign_name"]
                )
            if has_configured_status:
                insight_record["configured_status"] = _normalize_optional(
                    row["configured_status"]
                )
            if has_effective_status:
                insight_record["effective_status"] = _normalize_optional(
                    row["effective_status"]
                )

            insights_list.append(insight_record)
        return insights_list

    @staticmethod
    def _parse_date(date_str: str, field_name: str) -> date:
        """
        Parse date string and return date object.

        Args:
            date_str: Date string in YYYY-MM-DD format
            field_name: Name of the field for error messages

        Returns:
            date object

        Raises:
            ValueError: If date is invalid
        """
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(
                f"Invalid {field_name}: '{date_str}'. Must be a valid date in YYYY-MM-DD format. Error: {e}"
            )

    @staticmethod
    def _normalize_state_date(value: datetime | date | str | None) -> date | None:
        """Normalize various date inputs from sync state into a date object."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _document_to_insight(doc: InsightsDailyDocument) -> dict[str, Any]:
        """Convert InsightsDailyDocument to insight dictionary."""
        account_id = normalize_account_id(doc.account_id)
        return {
            "ad_account_id": account_id,
            "ad_id": doc.ad_id,
            "adset_id": doc.adset_id,
            "campaign_id": doc.campaign_id,
            "ad_name": None,  # Will be populated by _attach_entity_names
            "adset_name": None,  # Will be populated by _attach_entity_names
            "campaign_name": None,  # Will be populated by _attach_entity_names
            "configured_status": None,
            "effective_status": None,
            "date": doc.date_start.strftime("%Y-%m-%d"),
            "metrics": {
                "spend": float(doc.spend),
                "impressions": int(doc.impressions),
                "reach": int(doc.reach),
                "clicks": int(doc.clicks),
                "inline_link_clicks": int(doc.inline_link_clicks),
                "outbound_clicks": int(doc.outbound_clicks),
                "landing_page_view": int(doc.landing_page_view),
                "onsite_web_checkout": int(doc.onsite_web_checkout),
                "onsite_web_add_to_cart": int(doc.onsite_web_add_to_cart),
                "onsite_web_purchase": int(doc.onsite_web_purchase),
                "onsite_web_checkout_value": float(doc.onsite_web_checkout_value),
                "onsite_web_add_to_cart_value": float(doc.onsite_web_add_to_cart_value),
                "onsite_web_purchase_value": float(doc.onsite_web_purchase_value),
            },
        }

    @staticmethod
    def _key_for_insight(insight: dict[str, Any]) -> Tuple[str, str]:
        """Generate unique key for an insight record (ad_id, date)."""
        return (insight["ad_id"], insight["date"])

    @staticmethod
    def _aggregate_records_for_level(
        records: list[dict[str, Any]],
        target_level: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        if target_level not in {"account", "campaign", "adset"}:
            return records
        if not records:
            return records

        normalized_account_id = normalize_account_id(account_id)
        group_field_map = {
            "account": None,
            "campaign": "campaign_id",
            "adset": "adset_id",
        }
        group_field = group_field_map[target_level]

        aggregated: Dict[Tuple[str, str], dict[str, Any]] = {}

        for record in records:
            metrics = record.get("metrics", {})
            configured_status = record.get("configured_status")
            effective_status = record.get("effective_status")
            ad_name = record.get("ad_name")
            adset_name = record.get("adset_name")
            campaign_name = record.get("campaign_name")
            if target_level == "account":
                entity_value = account_id
            else:
                entity_value = record.get(group_field) if group_field else None
            if not entity_value:
                continue

            key = (str(entity_value), record["date"])
            bucket = aggregated.get(key)
            if not bucket:
                metric_template = {metric_key: 0 for metric_key in metrics.keys()}
                bucket = {
                    "ad_account_id": normalized_account_id,
                    "ad_id": str(entity_value),
                    "adset_id": str(entity_value) if target_level == "adset" else None,
                    "campaign_id": str(entity_value)
                    if target_level == "campaign"
                    else (record.get("campaign_id") if target_level == "adset" else None),
                    "ad_name": None,
                    "adset_name": None,
                    "campaign_name": None,
                    "configured_status": None,
                    "effective_status": None,
                    "date": record["date"],
                    "metrics": metric_template,
                }
                aggregated[key] = bucket

            if target_level == "adset" and not bucket.get("campaign_id"):
                bucket["campaign_id"] = record.get("campaign_id")
            if configured_status and not bucket.get("configured_status"):
                bucket["configured_status"] = configured_status
            if effective_status and not bucket.get("effective_status"):
                bucket["effective_status"] = effective_status
            if target_level == "campaign" and campaign_name and not bucket.get("campaign_name"):
                bucket["campaign_name"] = campaign_name
            if target_level == "adset":
                if adset_name and not bucket.get("adset_name"):
                    bucket["adset_name"] = adset_name
                if campaign_name and not bucket.get("campaign_name"):
                    bucket["campaign_name"] = campaign_name

            bucket_metrics = bucket["metrics"]
            for metric_key, value in metrics.items():
                if metric_key not in bucket_metrics:
                    bucket_metrics[metric_key] = 0
                bucket_metrics[metric_key] += value or 0

        return sorted(
            aggregated.values(),
            key=lambda item: (item["date"], item["ad_id"]),
        )

    @staticmethod
    async def _attach_entity_names(
        insights_list: list[dict[str, Any]], level: str, account_id: str
    ) -> list[dict[str, Any]]:
        """
        Fetch entity names from database and attach to insights records.

        Args:
            insights_list: List of insight dictionaries
            level: Query level (ad, adset, campaign)
            account_id: Ad account ID (without act_ prefix) for filtering

        Returns:
            insights_list with entity names attached
        """
        if not insights_list:
            return insights_list

        # Collect all unique entity IDs from insights
        ad_ids = set()
        adset_ids = set()
        campaign_ids = set()

        for insight in insights_list:
            if insight.get("ad_id"):
                ad_ids.add(insight["ad_id"])
            if insight.get("adset_id"):
                adset_ids.add(insight["adset_id"])
            if insight.get("campaign_id"):
                campaign_ids.add(insight["campaign_id"])


        # Query entity names from database
        entity_details_map: Dict[Tuple[str, str], dict[str, Any]] = {}

        async def _load_names(
            entity_type: Literal["ad", "adset", "campaign"], ids: set[str]
        ) -> None:
            if not ids:
                return
            docs = await AdEntityNamesDocument.find(
                AdEntityNamesDocument.account_id == account_id,
                AdEntityNamesDocument.entity_type == entity_type,
                In(AdEntityNamesDocument.entity_id, list(ids)),
            ).to_list()
            for doc in docs:
                entity_details_map[(entity_type, doc.entity_id)] = {
                    "name": doc.entity_name,
                    "configured_status": doc.configured_status,
                    "effective_status": doc.effective_status,
                }

        if level == "ad":
            await _load_names("ad", ad_ids)
            await _load_names("adset", adset_ids)
            await _load_names("campaign", campaign_ids)
        elif level == "adset":
            await _load_names("adset", adset_ids)
        elif level == "campaign":
            await _load_names("campaign", campaign_ids)

        # Attach names to insights (without overwriting existing values)
        for insight in insights_list:
            if level == "ad" and insight.get("ad_id"):
                ad_id = insight["ad_id"]
                details = entity_details_map.get(("ad", ad_id))
                if details:
                    if not insight.get("ad_name"):
                        insight["ad_name"] = details.get("name") or insight.get("ad_name")
                    if not insight.get("configured_status"):
                        insight["configured_status"] = details.get("configured_status")
                    if not insight.get("effective_status"):
                        insight["effective_status"] = details.get("effective_status")

            if level in {"ad", "adset"} and insight.get("adset_id"):
                adset_id = insight["adset_id"]
                details = entity_details_map.get(("adset", adset_id))
                if details:
                    if not insight.get("adset_name"):
                        insight["adset_name"] = details.get("name") or insight.get("adset_name")
                    if level == "adset" and not insight.get("configured_status"):
                        insight["configured_status"] = details.get("configured_status")
                    if level == "adset" and not insight.get("effective_status"):
                        insight["effective_status"] = details.get("effective_status")

            if level in {"ad", "campaign"} and insight.get("campaign_id"):
                campaign_id = insight["campaign_id"]
                details = entity_details_map.get(("campaign", campaign_id))
                if details:
                    if not insight.get("campaign_name"):
                        insight["campaign_name"] = details.get("name") or insight.get("campaign_name")
                    if level == "campaign" and not insight.get("configured_status"):
                        insight["configured_status"] = details.get("configured_status")
                    if level == "campaign" and not insight.get("effective_status"):
                        insight["effective_status"] = details.get("effective_status")

        return insights_list

    @staticmethod
    async def query_insights_mongo_only(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        mask_ad_ids: bool = False,
    ) -> dict[str, Any]:
        """
        Query insights data from MongoDB database only (no Redis, no Facebook API calls).
        This is used for viewing pure historical data that has been synced to MongoDB.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (account, campaign, adset, or ad)
            time_increment: Time increment (1=daily, None=aggregate) - currently only daily is supported
            breakdowns: Comma-separated breakdown dimensions - currently not supported
            object_level: Optional parent level for filtering (ad, adset, campaign)
            object_ids: Optional list of entity IDs to limit the query scope

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If parameters are invalid or unsupported features are requested
        """
        # Normalize account ID and remove act_ prefix for database query
        # Database stores account_id without act_ prefix (e.g., "1244295750378353")
        account_id = normalize_account_id(ad_account_id)
        # Remove act_ prefix for database query
        account_id_without_prefix = remove_account_id_prefix(account_id)

        # Validate dates
        since_date = InsightsService._parse_date(since, "since date")
        until_date = InsightsService._parse_date(until, "until date")
        if since_date > until_date:
            raise ValueError("since date must be on or before until date")

        # Validate parameters
        valid_levels = ["account", "campaign", "adset", "ad"]
        if level not in valid_levels:
            raise ValueError(
                f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )
        if time_increment not in (1, None):
            raise ValueError(
                f"Database query currently only supports time_increment=1 (daily) or None, got {time_increment}"
            )
        if breakdowns and breakdowns.strip():
            raise ValueError(
                f"Database query currently does not support breakdowns, got '{breakdowns}'"
            )

        object_filter = _resolve_object_filter(object_level, object_ids)

        # MongoDB only - no Redis
        logger.debug(
            f"MongoDB-only query for {account_id}: since={since_date}, until={until_date}"
        )

        # Initialize insights list
        insights_list: list[dict[str, Any]] = []

        # Query database based on level
        if level == "ad":
            # Ad-level: direct query, no aggregation needed

            # Query MongoDB
            if since_date and until_date:
                date_lower = datetime.combine(since_date, datetime.min.time())
                date_upper = datetime.combine(until_date, datetime.min.time())
                filters = [
                    InsightsDailyDocument.account_id == account_id_without_prefix,
                    InsightsDailyDocument.date_start >= date_lower,
                    InsightsDailyDocument.date_start <= date_upper,
                ]
                if object_filter:
                    field_name, normalized_ids = object_filter
                    field = getattr(InsightsDailyDocument, field_name)
                    filters.append(In(field, normalized_ids))

                docs = await InsightsDailyDocument.find(*filters).to_list()
                mongo_insights = [InsightsService._document_to_insight(doc) for doc in docs]
                insights_list.extend(mongo_insights)
                logger.debug(f"Retrieved {len(mongo_insights)} insights from MongoDB")

        else:
            # Campaign or AdSet level: use aggregation
            from utils.db import get_document_collection
            import pandas as pd

            collection = get_document_collection(InsightsDailyDocument)

            # Determine group field based on level
            if level == "campaign":
                group_field = "campaign_id"
            elif level == "adset":
                group_field = "adset_id"
            else:
                group_field = "account_id"

            # Query MongoDB with aggregation
            if since_date and until_date:
                date_lower = datetime.combine(since_date, datetime.min.time())
                date_upper = datetime.combine(until_date, datetime.min.time())
                match_stage: dict[str, Any] = {
                    "account_id": account_id_without_prefix,
                    "date_start": {
                        "$gte": date_lower,
                        "$lte": date_upper,
                    },
                }
                if object_filter:
                    field_name, normalized_ids = object_filter
                    match_stage[field_name] = {"$in": normalized_ids}

                group_stage: dict[str, Any] = {
                    "_id": {
                        group_field: f"${group_field}",
                        "date_start": "$date_start",
                    },
                    "spend": _sum_numeric_expression("spend"),
                    "impressions": _sum_numeric_expression("impressions"),
                    "reach": _sum_numeric_expression("reach"),
                    "clicks": _sum_numeric_expression("clicks"),
                    "inline_link_clicks": _sum_numeric_expression("inline_link_clicks"),
                    "outbound_clicks": _sum_numeric_expression("outbound_clicks"),
                    "landing_page_view": _sum_numeric_expression("landing_page_view"),
                    "onsite_web_checkout": _sum_numeric_expression("onsite_web_checkout"),
                    "onsite_web_add_to_cart": _sum_numeric_expression("onsite_web_add_to_cart"),
                    "onsite_web_purchase": _sum_numeric_expression("onsite_web_purchase"),
                    "onsite_web_checkout_value": _sum_numeric_expression("onsite_web_checkout_value"),
                    "onsite_web_add_to_cart_value": _sum_numeric_expression("onsite_web_add_to_cart_value"),
                    "onsite_web_purchase_value": _sum_numeric_expression("onsite_web_purchase_value"),
                }
                if level == "adset":
                    group_stage["campaign_id"] = {"$first": "$campaign_id"}

                project_stage: dict[str, Any] = {
                    "_id": 0,
                    "ad_id": f"$_id.{group_field}",
                    "date_start": "$_id.date_start",
                    "spend": 1,
                    "impressions": 1,
                    "reach": 1,
                    "clicks": 1,
                    "inline_link_clicks": 1,
                    "outbound_clicks": 1,
                    "landing_page_view": 1,
                    "onsite_web_checkout": 1,
                    "onsite_web_add_to_cart": 1,
                    "onsite_web_purchase": 1,
                    "onsite_web_checkout_value": 1,
                    "onsite_web_add_to_cart_value": 1,
                    "onsite_web_purchase_value": 1,
                }
                if level == "adset":
                    project_stage["campaign_id"] = "$campaign_id"

                # Build and execute aggregation pipeline for MongoDB
                pipeline = [
                    {"$match": match_stage},
                    {"$group": group_stage},
                    {"$project": project_stage},
                    {"$sort": {"date_start": 1, "ad_id": 1}},
                ]

                mongo_results = await InsightsDailyDocument.aggregate(pipeline).to_list()
                logger.debug(f"MongoDB aggregation returned {len(mongo_results)} results")

                # Convert MongoDB aggregation results to insights list
                for result in mongo_results:
                    entity_value = result.get("ad_id")
                    if not entity_value:
                        continue
                    campaign_value = result.get("campaign_id")

                    # Convert date_start to date string first
                    date_value = result.get("date_start")
                    if isinstance(date_value, datetime):
                        date_str = date_value.date().isoformat()
                    elif isinstance(date_value, date):
                        date_str = date_value.isoformat()
                    else:
                        date_str = str(date_value) if date_value else None

                    # Build metrics dict
                    metrics = {}
                    for metric in [
                        "spend", "impressions", "reach", "clicks",
                        "inline_link_clicks", "outbound_clicks", "landing_page_view",
                        "onsite_web_checkout", "onsite_web_add_to_cart", "onsite_web_purchase",
                        "onsite_web_checkout_value", "onsite_web_add_to_cart_value", "onsite_web_purchase_value",
                    ]:
                        metrics[metric] = result.get(metric, 0)

                    # Build record in standard format (same as _document_to_insight)
                    record: dict[str, Any] = {
                        "ad_account_id": account_id,
                        "ad_id": str(entity_value),
                        "adset_id": str(entity_value) if level == "adset" else None,
                        "campaign_id": (
                            str(entity_value)
                            if level == "campaign"
                            else (str(campaign_value) if campaign_value is not None else None)
                        ),
                        "ad_name": None,
                        "adset_name": None,
                        "campaign_name": None,
                        "configured_status": None,
                        "effective_status": None,
                        "date": date_str,
                        "metrics": metrics,
                    }

                    insights_list.append(record)

        # Sort by date and ad_id
        insights_list = sorted(
            insights_list,
            key=lambda item: (item["date"], item["ad_id"]),
        )

        insights_list = _filter_insights_by_objects(
            insights_list,
            object_level,
            object_ids,
        )

        # Fetch entity names from database and attach to insights
        insights_list = await InsightsService._attach_entity_names(
            insights_list, level, account_id_without_prefix
        )


        if mask_ad_ids and level != "ad":
            sanitized_list: list[dict[str, Any]] = []
            for insight in insights_list:
                sanitized = dict(insight)
                sanitized["ad_id"] = None
                sanitized_list.append(sanitized)
            insights_list = sanitized_list

        # Get last synced date for this account
        last_synced_date_str: str | None = None
        state = await InsightsSyncStateDocument.find_one(
            InsightsSyncStateDocument.account_id == account_id_without_prefix
        )
        if state:
            last_synced_source = (
                state.last_synced_date
                or state.range_until
                or state.obs_until
            )
            last_synced_date_obj = InsightsService._normalize_state_date(last_synced_source)
            if last_synced_date_obj:
                last_synced_date_str = last_synced_date_obj.strftime("%Y-%m-%d")

        return {
            "insights": insights_list,
            "total_records": len(insights_list),
            "date_range": {"since": since, "until": until},
            "last_synced_date": last_synced_date_str,
        }

    @staticmethod
    async def query_insights_mongo_redis(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
        object_level: str | None = None,
        object_ids: list[str] | None = None,
        mask_ad_ids: bool = False,
    ) -> dict[str, Any]:
        """
        Query insights data from MongoDB (historical) + Redis (recent 3 days) hybrid cache.
        Automatically splits date range between MongoDB and Redis based on REALTIME_LOOKBACK_DAYS boundary.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (account, campaign, adset, or ad)
            time_increment: Time increment (1=daily, None=aggregate) - currently only daily is supported
            breakdowns: Comma-separated breakdown dimensions - currently not supported
            object_level: Optional parent level for filtering (ad, adset, campaign)
            object_ids: Optional list of entity IDs to limit the query scope

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If parameters are invalid or unsupported features are requested
        """
        # Normalize account ID and remove act_ prefix for database query
        account_id = normalize_account_id(ad_account_id)
        account_id_without_prefix = remove_account_id_prefix(account_id)

        # Validate dates
        since_date = InsightsService._parse_date(since, "since date")
        until_date = InsightsService._parse_date(until, "until date")
        if since_date > until_date:
            raise ValueError("since date must be on or before until date")

        # Validate parameters
        valid_levels = ["account", "campaign", "adset", "ad"]
        if level not in valid_levels:
            raise ValueError(
                f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )
        if time_increment not in (1, None):
            raise ValueError(
                f"Database query currently only supports time_increment=1 (daily) or None, got {time_increment}"
            )
        if breakdowns and breakdowns.strip():
            raise ValueError(
                f"Database query currently does not support breakdowns, got '{breakdowns}'"
            )

        object_filter = _resolve_object_filter(object_level, object_ids)

        # Split date range into historical (MongoDB) and realtime (Redis) parts
        today = datetime.utcnow().date()
        realtime_boundary = today - timedelta(days=REALTIME_LOOKBACK_DAYS)  # 3 days ago

        # Determine which data source(s) to use
        mongo_since = None
        mongo_until = None
        redis_since = None
        redis_until = None

        if until_date < realtime_boundary:
            # All data is historical (MongoDB only)
            mongo_since = since_date
            mongo_until = until_date
        elif since_date >= realtime_boundary:
            # All data is realtime (Redis only)
            redis_since = since_date
            redis_until = until_date
        else:
            # Split: historical from MongoDB, realtime from Redis
            mongo_since = since_date
            mongo_until = realtime_boundary - timedelta(days=1)
            redis_since = realtime_boundary
            redis_until = until_date

        logger.debug(
            f"Hybrid query for {account_id}: "
            f"mongo=({mongo_since}, {mongo_until}), redis=({redis_since}, {redis_until})"
        )

        # Initialize insights list
        insights_list: list[dict[str, Any]] = []

        # Query database based on level
        if level == "ad":
            # Ad-level: direct query, no aggregation needed

            # Query MongoDB for historical data
            if mongo_since and mongo_until:
                date_lower = datetime.combine(mongo_since, datetime.min.time())
                date_upper = datetime.combine(mongo_until, datetime.min.time())
                filters = [
                    InsightsDailyDocument.account_id == account_id_without_prefix,
                    InsightsDailyDocument.date_start >= date_lower,
                    InsightsDailyDocument.date_start <= date_upper,
                ]
                if object_filter:
                    field_name, normalized_ids = object_filter
                    field = getattr(InsightsDailyDocument, field_name)
                    filters.append(In(field, normalized_ids))

                docs = await InsightsDailyDocument.find(*filters).to_list()
                mongo_insights = [InsightsService._document_to_insight(doc) for doc in docs]
                insights_list.extend(mongo_insights)
                logger.debug(f"Retrieved {len(mongo_insights)} insights from MongoDB")

            # Query Redis for realtime data
            if redis_since and redis_until:
                redis_insights = await _get_insights_from_redis_range(
                    account_id=account_id,
                    since_date=redis_since,
                    until_date=redis_until,
                )

                # Apply object filter if specified
                if object_filter:
                    redis_insights = _filter_insights_by_objects(
                        redis_insights, object_level, object_ids
                    )

                insights_list.extend(redis_insights)
                logger.debug(f"Retrieved {len(redis_insights)} insights from Redis")
        else:
            # Campaign or AdSet level: use aggregation
            from utils.db import get_document_collection
            import pandas as pd

            collection = get_document_collection(InsightsDailyDocument)

            # Determine group field based on level
            if level == "campaign":
                group_field = "campaign_id"
            elif level == "adset":
                group_field = "adset_id"
            else:
                group_field = "account_id"

            # Query MongoDB for historical data (with aggregation)
            if mongo_since and mongo_until:
                date_lower = datetime.combine(mongo_since, datetime.min.time())
                date_upper = datetime.combine(mongo_until, datetime.min.time())
                match_stage: dict[str, Any] = {
                    "account_id": account_id_without_prefix,
                    "date_start": {
                        "$gte": date_lower,
                        "$lte": date_upper,
                    },
                }
                if object_filter:
                    field_name, normalized_ids = object_filter
                    match_stage[field_name] = {"$in": normalized_ids}

                group_stage: dict[str, Any] = {
                    "_id": {
                        group_field: f"${group_field}",
                        "date_start": "$date_start",
                    },
                    "spend": _sum_numeric_expression("spend"),
                    "impressions": _sum_numeric_expression("impressions"),
                    "reach": _sum_numeric_expression("reach"),
                    "clicks": _sum_numeric_expression("clicks"),
                    "inline_link_clicks": _sum_numeric_expression("inline_link_clicks"),
                    "outbound_clicks": _sum_numeric_expression("outbound_clicks"),
                    "landing_page_view": _sum_numeric_expression("landing_page_view"),
                    "onsite_web_checkout": _sum_numeric_expression("onsite_web_checkout"),
                    "onsite_web_add_to_cart": _sum_numeric_expression("onsite_web_add_to_cart"),
                    "onsite_web_purchase": _sum_numeric_expression("onsite_web_purchase"),
                    "onsite_web_checkout_value": _sum_numeric_expression("onsite_web_checkout_value"),
                    "onsite_web_add_to_cart_value": _sum_numeric_expression("onsite_web_add_to_cart_value"),
                    "onsite_web_purchase_value": _sum_numeric_expression("onsite_web_purchase_value"),
                }
                if level == "adset":
                    group_stage["campaign_id"] = {"$first": "$campaign_id"}

                project_stage: dict[str, Any] = {
                    "_id": 0,
                    "ad_id": f"$_id.{group_field}",
                    "date_start": "$_id.date_start",
                    "spend": 1,
                    "impressions": 1,
                    "reach": 1,
                    "clicks": 1,
                    "inline_link_clicks": 1,
                    "outbound_clicks": 1,
                    "landing_page_view": 1,
                    "onsite_web_checkout": 1,
                    "onsite_web_add_to_cart": 1,
                    "onsite_web_purchase": 1,
                    "onsite_web_checkout_value": 1,
                    "onsite_web_add_to_cart_value": 1,
                    "onsite_web_purchase_value": 1,
                }
                if level == "adset":
                    project_stage["campaign_id"] = "$campaign_id"

                # Build and execute aggregation pipeline for MongoDB
                pipeline = [
                    {"$match": match_stage},
                    {"$group": group_stage},
                    {"$project": project_stage},
                    {"$sort": {"date_start": 1, "ad_id": 1}},
                ]

                mongo_results = await InsightsDailyDocument.aggregate(pipeline).to_list()
                logger.debug(f"MongoDB aggregation returned {len(mongo_results)} results")

                # Convert MongoDB aggregation results to insights list
                for result in mongo_results:
                    entity_value = result.get("ad_id")
                    if not entity_value:
                        continue
                    campaign_value = result.get("campaign_id")

                    # Convert date_start to date string first
                    date_value = result.get("date_start")
                    if isinstance(date_value, datetime):
                        date_str = date_value.date().isoformat()
                    elif isinstance(date_value, date):
                        date_str = date_value.isoformat()
                    else:
                        date_str = str(date_value) if date_value else None

                    # Build metrics dict
                    metrics = {}
                    for metric in [
                        "spend", "impressions", "reach", "clicks",
                        "inline_link_clicks", "outbound_clicks", "landing_page_view",
                        "onsite_web_checkout", "onsite_web_add_to_cart", "onsite_web_purchase",
                        "onsite_web_checkout_value", "onsite_web_add_to_cart_value", "onsite_web_purchase_value",
                    ]:
                        metrics[metric] = result.get(metric, 0)

                    # Build record in standard format (same as _document_to_insight)
                    record: dict[str, Any] = {
                        "ad_account_id": account_id,
                        "ad_id": str(entity_value),
                        "adset_id": str(entity_value) if level == "adset" else None,
                        "campaign_id": (
                            str(entity_value)
                            if level == "campaign"
                            else (str(campaign_value) if campaign_value is not None else None)
                        ),
                        "ad_name": None,
                        "adset_name": None,
                        "campaign_name": None,
                        "configured_status": None,
                        "effective_status": None,
                        "date": date_str,
                        "metrics": metrics,
                    }

                    insights_list.append(record)

            # Query Redis for realtime data and aggregate using pandas
            if redis_since and redis_until:
                redis_ad_data = await _get_insights_from_redis_range(
                    account_id=account_id,
                    since_date=redis_since,
                    until_date=redis_until,
                )

                if redis_ad_data:
                    # Apply object filter if specified
                    if object_filter:
                        redis_ad_data = _filter_insights_by_objects(
                            redis_ad_data, object_level, object_ids
                        )

                    # Flatten metrics dict for DataFrame creation
                    flattened_data = []
                    for record in redis_ad_data:
                        flat_record = {k: v for k, v in record.items() if k != "metrics"}
                        if "metrics" in record:
                            flat_record.update(record["metrics"])
                        # Also need date_start for groupby
                        if "date" in flat_record and "date_start" not in flat_record:
                            flat_record["date_start"] = flat_record["date"]
                        flattened_data.append(flat_record)

                    # Convert to pandas DataFrame for aggregation
                    df = pd.DataFrame(flattened_data)

                    # Ensure date_start is in correct format
                    if "date_start" in df.columns:
                        df["date_start"] = pd.to_datetime(df["date_start"]).dt.date

                    # Aggregate by group_field and date
                    agg_cols = [group_field, "date_start"]
                    if level == "adset":
                        agg_cols.append("campaign_id")

                    numeric_cols = [
                        "spend", "impressions", "reach", "clicks",
                        "inline_link_clicks", "outbound_clicks", "landing_page_view",
                        "onsite_web_checkout", "onsite_web_add_to_cart", "onsite_web_purchase",
                        "onsite_web_checkout_value", "onsite_web_add_to_cart_value", "onsite_web_purchase_value",
                    ]

                    # Convert numeric columns to float
                    for col in numeric_cols:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

                    # Group and aggregate
                    grouped = df.groupby(agg_cols, as_index=False)[numeric_cols].sum()

                    # Convert aggregated results to insights list (standard format)
                    for _, row in grouped.iterrows():
                        entity_value = row.get(group_field)
                        campaign_value = row.get("campaign_id") if level == "adset" else None

                        # Convert date_start to date string
                        date_str = row["date_start"].isoformat() if isinstance(row["date_start"], date) else str(row["date_start"])

                        # Build metrics dict
                        metrics = {}
                        for metric in numeric_cols:
                            metrics[metric] = float(row[metric]) if metric in row else 0.0

                        # Build record in standard format (same as MongoDB aggregation)
                        record: dict[str, Any] = {
                            "ad_account_id": account_id,
                            "ad_id": str(entity_value),
                            "adset_id": str(entity_value) if level == "adset" else None,
                            "campaign_id": (
                                str(entity_value)
                                if level == "campaign"
                                else (str(campaign_value) if campaign_value is not None else None)
                            ),
                            "ad_name": None,
                            "adset_name": None,
                            "campaign_name": None,
                            "configured_status": None,
                            "effective_status": None,
                            "date": date_str,
                            "metrics": metrics,
                        }

                        insights_list.append(record)

                    logger.debug(f"Redis aggregation added {len(grouped)} results")


        # Sort by date and ad_id
        insights_list = sorted(
            insights_list,
            key=lambda item: (item["date"], item["ad_id"]),
        )

        insights_list = _filter_insights_by_objects(
            insights_list,
            object_level,
            object_ids,
        )

        # Fetch entity names from database and attach to insights
        insights_list = await InsightsService._attach_entity_names(
            insights_list, level, account_id_without_prefix
        )

        if mask_ad_ids and level != "ad":
            sanitized_list = []
            for insight in insights_list:
                sanitized = dict(insight)
                sanitized["ad_id"] = None
                sanitized_list.append(sanitized)
            insights_list = sanitized_list

        # Get last synced date for this account
        last_synced_date_str: str | None = None
        state = await InsightsSyncStateDocument.find_one(
            InsightsSyncStateDocument.account_id == account_id_without_prefix
        )
        if state:
            last_synced_source = (
                state.last_synced_date
                or state.range_until
                or state.obs_until
            )
            last_synced_date_obj = InsightsService._normalize_state_date(last_synced_source)
            if last_synced_date_obj:
                last_synced_date_str = last_synced_date_obj.strftime("%Y-%m-%d")

        return {
            "insights": insights_list,
            "total_records": len(insights_list),
            "date_range": {"since": since, "until": until},
            "last_synced_date": last_synced_date_str,
        }
async def _resolve_latest_synced_date(account_id_without_prefix: str) -> date | None:
    docs = (
        await InsightsDailyDocument.find(
            InsightsDailyDocument.account_id == account_id_without_prefix
        )
        .sort(-InsightsDailyDocument.date_start)
        .to_list(1)
    )
    if not docs:
        return None
    return docs[0].date_start.date()
