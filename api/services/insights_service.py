"""
Service layer for Insights data operations.
Encapsulates business logic for fetching and processing Facebook Ads Insights.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Tuple

from facebook_business.adobjects.adreportrun import AdReportRun
from beanie.operators import In

from baseline.get_data import insight_to_df
from api.services.insights_sync_service import REALTIME_LOOKBACK_DAYS
from utils.db import InsightsDailyDocument, AdEntityNamesDocument
from utils.fb_api_flyweight_factory import get_ad_object, get_api
from utils.insight_tool import ATOMIC_FIELDS, get_insight


class InsightsService:
    """Service for fetching and processing Facebook Ads Insights data."""

    @staticmethod
    def _normalize_account_id(account_id: str) -> str:
        """
        Ensure the ad account ID uses the act_ prefix expected by the Facebook SDK.

        Args:
            account_id: Raw ad account ID provided by caller

        Returns:
            Normalized account ID starting with act_
        """
        if not account_id:
            raise ValueError("ad_account_id is required")
        stripped = account_id.strip()
        return stripped if stripped.startswith("act_") else f"act_{stripped.lstrip('act_')}"

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
    async def fetch_insights_sync(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
    ) -> dict[str, Any]:
        """
        Synchronously fetch insights data from Facebook API.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (ad, adset, or campaign)
            time_increment: Time increment (1=daily, None=aggregate)
            breakdowns: Comma-separated breakdown dimensions

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If parameters are invalid
            Exception: If Facebook API call fails
        """
        # Normalize account ID
        account_id = InsightsService._normalize_account_id(ad_account_id)
        # Remove act_ prefix for database query (DB stores account_id without prefix)
        account_id_without_prefix = account_id.replace("act_", "") if account_id.startswith("act_") else account_id

        # Validate dates
        since_date = InsightsService._parse_date(since, "since date")
        until_date = InsightsService._parse_date(until, "until date")
        if since_date > until_date:
            raise ValueError("since date must be on or before until date")

        # Validate level
        valid_levels = ["ad", "adset", "campaign"]
        if level not in valid_levels:
            raise ValueError(
                f"Invalid level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )

        should_use_historical = (
            level == "ad"
            and time_increment == 1
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
                # Query database using account_id without act_ prefix
                docs = await InsightsDailyDocument.find(
                    InsightsDailyDocument.account_id == account_id_without_prefix,
                    InsightsDailyDocument.date_start
                    >= datetime.combine(since_date, datetime.min.time()),
                    InsightsDailyDocument.date_start
                    <= datetime.combine(historical_until, datetime.min.time()),
                ).to_list()

                for doc in docs:
                    insight_record = InsightsService._document_to_insight(doc)
                    historical_records[
                        InsightsService._key_for_insight(insight_record)
                    ] = insight_record

                realtime_since = historical_until + timedelta(days=1)

        api_records: list[dict[str, Any]] = []
        if realtime_since <= until_date:
            ad_object = await get_ad_object(account_id, account_id)
            fields = ["ad_id", *ATOMIC_FIELDS]

            try:
                insights = get_insight(
                    adobject=ad_object,
                    fields=fields,
                    level=level,
                    since=realtime_since.strftime("%Y-%m-%d"),
                    until=until_date.strftime("%Y-%m-%d"),
                    time_increment=time_increment,
                    breakdowns=breakdowns or "",
                    is_async=False,
                )

                df = insight_to_df(insights)
                api_records = InsightsService._df_to_insights_list(df)
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

        return {
            "insights": insights_list,
            "total_records": len(insights_list),
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
        account_id = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )

        # Validate dates
        InsightsService._validate_date(since, "since date")
        InsightsService._validate_date(until, "until date")

        # Validate level
        valid_levels = ["ad", "adset", "campaign"]
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
        account_id = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )

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
        account_id = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )

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
        for _, row in df.iterrows():
            insight_record = {
                "ad_id": str(row["ad_id"]),
                "date": str(row["date_start"]),
                "metrics": {
                    "spend": float(row["spend"]),
                    "impressions": int(row["impressions"]),
                    "reach": int(row["reach"]),
                    "clicks": int(row["clicks"]),
                    "inline_link_clicks": int(row["inline_link_clicks"]),
                    "outbound_clicks": int(row["outbound_clicks"]),
                    "landing_page_view": int(row["landing_page_view"]),
                    "onsite_web_checkout": int(row["onsite_web_checkout"]),
                    "onsite_web_add_to_cart": int(row["onsite_web_add_to_cart"]),
                    "onsite_web_purchase": int(row["onsite_web_purchase"]),
                    "onsite_web_checkout_value": float(
                        row["onsite_web_checkout_value"]
                    ),
                    "onsite_web_add_to_cart_value": float(
                        row["onsite_web_add_to_cart_value"]
                    ),
                    "onsite_web_purchase_value": float(
                        row["onsite_web_purchase_value"]
                    ),
                },
            }
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
    def _document_to_insight(doc: InsightsDailyDocument) -> dict[str, Any]:
        """Convert InsightsDailyDocument to insight dictionary."""
        return {
            "ad_id": doc.ad_id,
            "adset_id": None,  # Not populated for ad-level queries
            "campaign_id": None,  # Not populated for ad-level queries
            "ad_name": None,  # Will be populated by _attach_entity_names
            "adset_name": None,  # Will be populated by _attach_entity_names
            "campaign_name": None,  # Will be populated by _attach_entity_names
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
        entity_names_map: Dict[Tuple[str, str], str] = {}

        # Fetch ad names
        if ad_ids and level == "ad":
            ad_name_docs = await AdEntityNamesDocument.find(
                AdEntityNamesDocument.account_id == account_id,
                AdEntityNamesDocument.entity_type == "ad",
                In(AdEntityNamesDocument.entity_id, list(ad_ids)),
            ).to_list()
            for doc in ad_name_docs:
                entity_names_map[("ad", doc.entity_id)] = doc.entity_name

        # Fetch adset names
        if adset_ids and level == "adset":
            adset_name_docs = await AdEntityNamesDocument.find(
                AdEntityNamesDocument.account_id == account_id,
                AdEntityNamesDocument.entity_type == "adset",
                In(AdEntityNamesDocument.entity_id, list(adset_ids)),
            ).to_list()
            for doc in adset_name_docs:
                entity_names_map[("adset", doc.entity_id)] = doc.entity_name

        # Fetch campaign names
        if campaign_ids and level == "campaign":
            campaign_name_docs = await AdEntityNamesDocument.find(
                AdEntityNamesDocument.account_id == account_id,
                AdEntityNamesDocument.entity_type == "campaign",
                In(AdEntityNamesDocument.entity_id, list(campaign_ids)),
            ).to_list()
            for doc in campaign_name_docs:
                entity_names_map[("campaign", doc.entity_id)] = doc.entity_name

        # Attach names to insights
        for idx, insight in enumerate(insights_list):
            if level == "ad" and insight.get("ad_id"):
                ad_id = insight["ad_id"]
                ad_name = entity_names_map.get(("ad", ad_id), None)
                insight["ad_name"] = ad_name
                if not ad_name:
                    insight["adset_name"] = None
                    insight["campaign_name"] = None
            elif level == "adset" and insight.get("adset_id"):
                insight["ad_name"] = None
                insight["adset_name"] = entity_names_map.get(
                    ("adset", insight["adset_id"]), None
                )
                insight["campaign_name"] = None
            elif level == "campaign" and insight.get("campaign_id"):
                insight["ad_name"] = None
                insight["adset_name"] = None
                insight["campaign_name"] = entity_names_map.get(
                    ("campaign", insight["campaign_id"]), None
                )
            else:
                # Fallback: set all names to None
                insight["ad_name"] = None
                insight["adset_name"] = None
                insight["campaign_name"] = None

        return insights_list

    @staticmethod
    async def query_insights_from_db(
        ad_account_id: str,
        since: str,
        until: str,
        level: str = "ad",
        time_increment: int | None = None,
        breakdowns: str | None = None,
    ) -> dict[str, Any]:
        """
        Query insights data from MongoDB database only (no Facebook API calls).
        This is used for viewing historical data that has already been synced.

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            since: Start date in YYYY-MM-DD format
            until: End date in YYYY-MM-DD format
            level: Aggregation level (ad, adset, or campaign) - currently only 'ad' is supported
            time_increment: Time increment (1=daily, None=aggregate) - currently only daily is supported
            breakdowns: Comma-separated breakdown dimensions - currently not supported

        Returns:
            Dictionary containing insights data with metrics and metadata

        Raises:
            ValueError: If parameters are invalid or unsupported features are requested
        """
        # Normalize account ID and remove act_ prefix for database query
        # Database stores account_id without act_ prefix (e.g., "1244295750378353")
        account_id = InsightsService._normalize_account_id(ad_account_id)
        # Remove act_ prefix for database query
        account_id_without_prefix = account_id.replace("act_", "") if account_id.startswith("act_") else account_id

        # Validate dates
        since_date = InsightsService._parse_date(since, "since date")
        until_date = InsightsService._parse_date(until, "until date")
        if since_date > until_date:
            raise ValueError("since date must be on or before until date")

        # Validate parameters
        valid_levels = ["ad", "adset", "campaign"]
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

        # Query database based on level
        if level == "ad":
            # Ad-level: direct query, no aggregation needed
            docs = await InsightsDailyDocument.find(
                InsightsDailyDocument.account_id == account_id_without_prefix,
                InsightsDailyDocument.date_start
                >= datetime.combine(since_date, datetime.min.time()),
                InsightsDailyDocument.date_start
                <= datetime.combine(until_date, datetime.min.time()),
            ).to_list()

            # Convert documents to insights list
            insights_list = [
                InsightsService._document_to_insight(doc) for doc in docs
            ]
        else:
            # Campaign or AdSet level: use aggregation
            from utils.db import get_document_collection

            collection = get_document_collection(InsightsDailyDocument)

            # Determine group field based on level
            group_field = "campaign_id" if level == "campaign" else "adset_id"

            # Build aggregation pipeline
            pipeline = [
                {
                    "$match": {
                        "account_id": account_id_without_prefix,
                        "date_start": {
                            "$gte": datetime.combine(since_date, datetime.min.time()),
                            "$lte": datetime.combine(until_date, datetime.min.time()),
                        },
                    }
                },
                {
                    "$group": {
                        "_id": {
                            group_field: f"${group_field}",
                            "date_start": "$date_start",
                        },
                        "spend": {"$sum": "$spend"},
                        "impressions": {"$sum": "$impressions"},
                        "reach": {"$sum": "$reach"},
                        "clicks": {"$sum": "$clicks"},
                        "inline_link_clicks": {"$sum": "$inline_link_clicks"},
                        "outbound_clicks": {"$sum": "$outbound_clicks"},
                        "landing_page_view": {"$sum": "$landing_page_view"},
                        "onsite_web_checkout": {"$sum": "$onsite_web_checkout"},
                        "onsite_web_add_to_cart": {"$sum": "$onsite_web_add_to_cart"},
                        "onsite_web_purchase": {"$sum": "$onsite_web_purchase"},
                        "onsite_web_checkout_value": {"$sum": "$onsite_web_checkout_value"},
                        "onsite_web_add_to_cart_value": {"$sum": "$onsite_web_add_to_cart_value"},
                        "onsite_web_purchase_value": {"$sum": "$onsite_web_purchase_value"},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "entity_id": f"$_id.{group_field}",
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
                },
                {"$sort": {"date_start": 1, "entity_id": 1}},
            ]

            # Execute aggregation using Beanie's aggregate method
            results = await InsightsDailyDocument.aggregate(pipeline).to_list()

            # Convert aggregation results to insights list
            insights_list = [
                {
                    "ad_id": str(result["entity_id"]),  # Still use ad_id for backward compatibility
                    "adset_id": str(result["entity_id"]) if level == "adset" else None,
                    "campaign_id": str(result["entity_id"]) if level == "campaign" else None,
                    "ad_name": None,  # Will be populated by _attach_entity_names
                    "adset_name": None,  # Will be populated by _attach_entity_names
                    "campaign_name": None,  # Will be populated by _attach_entity_names
                    "date": result["date_start"].strftime("%Y-%m-%d"),
                    "metrics": {
                        "spend": float(result["spend"]),
                        "impressions": int(result["impressions"]),
                        "reach": int(result["reach"]),
                        "clicks": int(result["clicks"]),
                        "inline_link_clicks": int(result["inline_link_clicks"]),
                        "outbound_clicks": int(result["outbound_clicks"]),
                        "landing_page_view": int(result["landing_page_view"]),
                        "onsite_web_checkout": int(result["onsite_web_checkout"]),
                        "onsite_web_add_to_cart": int(result["onsite_web_add_to_cart"]),
                        "onsite_web_purchase": int(result["onsite_web_purchase"]),
                        "onsite_web_checkout_value": float(result["onsite_web_checkout_value"]),
                        "onsite_web_add_to_cart_value": float(result["onsite_web_add_to_cart_value"]),
                        "onsite_web_purchase_value": float(result["onsite_web_purchase_value"]),
                    },
                }
                for result in results
            ]

        # Sort by date and ad_id
        insights_list = sorted(
            insights_list,
            key=lambda item: (item["date"], item["ad_id"]),
        )

        # Fetch entity names from database and attach to insights
        insights_list = await InsightsService._attach_entity_names(
            insights_list, level, account_id_without_prefix
        )


        return {
            "insights": insights_list,
            "total_records": len(insights_list),
            "date_range": {"since": since, "until": until},
        }
