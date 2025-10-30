"""
Service layer for Insights data operations.
Encapsulates business logic for fetching and processing Facebook Ads Insights.
"""

from datetime import datetime
from typing import Any

from facebook_business.adobjects.adreportrun import AdReportRun

from baseline.get_data import insight_to_df
from utils.fb_api_flyweight_factory import get_ad_object, get_api
from utils.insight_tool import ATOMIC_FIELDS, get_insight


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

        # Fetch insights from Facebook API (synchronous)
        try:
            insights = get_insight(
                adobject=ad_object,
                fields=fields,
                level=level,
                since=since,
                until=until,
                time_increment=time_increment,
                breakdowns=breakdowns or "",
                is_async=False,
            )

            # Convert to DataFrame for processing
            df = insight_to_df(insights)

            # Convert DataFrame to list of dictionaries
            insights_list = InsightsService._df_to_insights_list(df)

            return {
                "insights": insights_list,
                "total_records": len(insights_list),
                "date_range": {"since": since, "until": until},
            }

        except Exception as e:
            print(f"Error fetching insights for account {account_id}: {e}")
            raise Exception(f"Failed to fetch insights: {str(e)}") from e

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
