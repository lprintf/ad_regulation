"""
Insights data endpoints.
Provides API for fetching Facebook Ads Insights data (sync and async).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies.auth import get_current_user
from api.models.insights import (
    AsyncJobCreateResponse,
    AsyncJobStatus,
    AsyncJobStatusResponse,
    InsightRecord,
    InsightsRequest,
    InsightsResponse,
)
from api.models.responses import SuccessResponse
from api.services.insights_service import InsightsService

router = APIRouter(prefix="/insights", tags=["Insights"])


# ===== Synchronous Endpoint =====


@router.get("/sync", response_model=SuccessResponse[InsightsResponse])
async def fetch_insights_sync(
    ad_account_id: Annotated[
        str,
        Query(
            description="Ad account ID (with or without act_ prefix)",
            examples=["act_123456789"],
        ),
    ],
    since: Annotated[
        str,
        Query(
            description="Start date in YYYY-MM-DD format",
            examples=["2025-01-01"],
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    until: Annotated[
        str,
        Query(
            description="End date in YYYY-MM-DD format",
            examples=["2025-01-31"],
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    level: Annotated[
        str,
        Query(
            description="Aggregation level: ad, adset, or campaign",
            examples=["ad"],
        ),
    ] = "ad",
    time_increment: Annotated[
        int | None,
        Query(
            description="Time increment: 1=daily, null=aggregate all",
            examples=[1, None],
        ),
    ] = None,
    breakdowns: Annotated[
        str | None,
        Query(
            description="Comma-separated breakdown dimensions (e.g., 'country', 'hourly_stats_aggregated_by_advertiser_time_zone')",
            examples=["country", "hourly_stats_aggregated_by_advertiser_time_zone"],
        ),
    ] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Synchronously fetch Facebook Ads Insights data.
    Returns data immediately (may timeout for large date ranges).

    Args:
        ad_account_id: Ad account ID (with or without act_ prefix)
        since: Start date in YYYY-MM-DD format
        until: End date in YYYY-MM-DD format
        level: Aggregation level (ad, adset, or campaign), defaults to "ad"
        time_increment: Time increment (1=daily, None=aggregate all)
        breakdowns: Breakdown dimensions (comma-separated)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data with metrics and metadata

    Example:
        ```
        GET /insights/sync?ad_account_id=act_123&since=2025-01-01&until=2025-01-31&time_increment=1
        ```
    """
    try:
        result = await InsightsService.fetch_insights_sync(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_id=insight["ad_id"],
                    date=insight["date"],
                    metrics=insight["metrics"],
                )
                for insight in result["insights"]
            ],
            total_records=result["total_records"],
            date_range=result["date_range"],
        )

        return SuccessResponse(
            data=insights_data,
            message=f"Successfully fetched {result['total_records']} insight records",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch insights: {str(e)}",
        )


# ===== Asynchronous Endpoints =====


@router.post("/async", response_model=SuccessResponse[AsyncJobCreateResponse])
async def create_async_job(
    request: InsightsRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[AsyncJobCreateResponse]:
    """
    Create an async Facebook Ads Insights job.
    Returns job_id immediately; use GET /insights/async/{job_id} to check status.

    Args:
        request: Insights request parameters
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing job_id and initial status

    Example:
        Request:
        ```json
        {
            "ad_account_id": "act_123456789",
            "since": "2025-01-01",
            "until": "2025-12-31",
            "level": "ad",
            "time_increment": 1,
            "breakdowns": "country"
        }
        ```

        Response:
        ```json
        {
            "success": true,
            "data": {
                "job_id": "12345678",
                "ad_account_id": "act_123456789",
                "status": "Job Running",
                "created_at": "2025-01-01T12:00:00"
            }
        }
        ```
    """
    try:
        result = await InsightsService.create_async_job(
            ad_account_id=request.ad_account_id,
            since=request.since,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
        )

        job_data = AsyncJobCreateResponse(
            job_id=result["job_id"],
            ad_account_id=result["ad_account_id"],
            status=AsyncJobStatus(result["status"]),
            created_at=result["created_at"],
        )

        return SuccessResponse(
            data=job_data,
            message=f"Async job created successfully. Job ID: {result['job_id']}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create async job: {str(e)}",
        )


@router.get(
    "/async/{job_id}", response_model=SuccessResponse[AsyncJobStatusResponse]
)
async def check_job_status(
    job_id: str,
    ad_account_id: Annotated[
        str,
        Query(
            description="Ad account ID (with or without act_ prefix)",
            examples=["act_123456789"],
        ),
    ],
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[AsyncJobStatusResponse]:
    """
    Check the status of an async insights job.

    Args:
        job_id: Facebook async job ID
        ad_account_id: Ad account ID (with or without act_ prefix)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing job status and progress

    Example:
        ```
        GET /insights/async/12345678?ad_account_id=act_123456789
        ```

        Response:
        ```json
        {
            "success": true,
            "data": {
                "job_id": "12345678",
                "ad_account_id": "act_123456789",
                "status": "Job Completed",
                "percent_complete": 100,
                "created_at": "2025-01-01T12:00:00",
                "updated_at": "2025-01-01T12:05:00"
            }
        }
        ```
    """
    try:
        result = await InsightsService.check_job_status(
            ad_account_id=ad_account_id,
            job_id=job_id,
        )

        print(f"[DEBUG ROUTER] Service returned: {result}")

        status_data = AsyncJobStatusResponse(
            job_id=result["job_id"],
            ad_account_id=result["ad_account_id"],
            status=AsyncJobStatus(result["status"]),
            percent_complete=result["percent_complete"],
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
        )

        print(f"[DEBUG ROUTER] Status data created: {status_data}")

        return SuccessResponse(
            data=status_data,
            message=f"Job status: {result['status']} ({result['percent_complete']}%)",
        )

    except ValueError as e:
        # Job not found
        print(f"[DEBUG ROUTER] ValueError caught: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check job status: {str(e)}",
        )


@router.get(
    "/async/{job_id}/result", response_model=SuccessResponse[InsightsResponse]
)
async def get_job_result(
    job_id: str,
    ad_account_id: Annotated[
        str,
        Query(
            description="Ad account ID (with or without act_ prefix)",
            examples=["act_123456789"],
        ),
    ],
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Get the result of a completed async insights job.

    Args:
        job_id: Facebook async job ID
        ad_account_id: Ad account ID (with or without act_ prefix)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data

    Raises:
        HTTPException: If job is not completed or failed

    Example:
        ```
        GET /insights/async/12345678/result?ad_account_id=act_123456789
        ```

        Response:
        ```json
        {
            "success": true,
            "data": {
                "insights": [...],
                "total_records": 1000,
                "date_range": {"since": "2025-01-01", "until": "2025-12-31"}
            }
        }
        ```
    """
    try:
        result = await InsightsService.get_job_result(
            ad_account_id=ad_account_id,
            job_id=job_id,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_id=insight["ad_id"],
                    date=insight["date"],
                    metrics=insight["metrics"],
                )
                for insight in result["insights"]
            ],
            total_records=result["total_records"],
            date_range=result["date_range"],
        )

        return SuccessResponse(
            data=insights_data,
            message=f"Successfully retrieved {result['total_records']} insight records",
        )

    except ValueError as e:
        # Job not completed yet
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job result: {str(e)}",
        )
