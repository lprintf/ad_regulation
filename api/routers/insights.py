"""
Insights data endpoints.
Provides API for fetching Facebook Ads Insights data (sync and async).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies.auth import get_current_user
from api.models.insights import (
    AsyncJobCreateResponse,
    AsyncJobStatus,
    AsyncJobStatusResponse,
    EntityNamesSyncRequest,
    EntityNamesSyncResult,
    InsightAccountSyncStatus,
    InsightRecord,
    InsightsAccountSyncResponse,
    InsightsFromLastRequest,
    InsightsRequest,
    InsightsResponse,
    InsightsSyncRequest,
    InsightsSyncTriggerRequest,
    InsightsSyncTriggerResponse,
    SyncStatus,
)
from api.models.responses import SuccessResponse
from api.services.insights_service import InsightsService
from api.services.insights_sync_service import InsightsSyncService
from api.services.entity_names_sync_service import EntityNamesSyncService

router = APIRouter(prefix="/insights", tags=["Insights"])


# ===== Database Query Endpoint =====


@router.get("", response_model=SuccessResponse[InsightsResponse])
async def query_insights_from_database(
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
            examples=["2024-01-01"],
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    until: Annotated[
        str,
        Query(
            description="End date in YYYY-MM-DD format",
            examples=["2024-01-31"],
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    level: Annotated[
        str,
        Query(
            description="Aggregation level: ad, adset, or campaign",
            examples=["ad", "adset", "campaign"],
        ),
    ] = "ad",
    time_increment: Annotated[
        int | None,
        Query(
            description="Time increment: 1=daily, null=aggregate (currently only daily supported)",
            examples=[1],
        ),
    ] = 1,
    breakdowns: Annotated[
        str | None,
        Query(
            description="Breakdowns (currently not supported, must be empty)",
            examples=[""],
        ),
    ] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query Facebook Ads Insights data from MongoDB database only.
    This endpoint does NOT call Facebook API - it only returns data that has been previously synced.

    Supports aggregation by level:
    - level="ad": Returns ad-level data (no aggregation)
    - level="adset": Aggregates ad data by adset_id and date
    - level="campaign": Aggregates ad data by campaign_id and date

    Use this for viewing historical data. Use /insights/sync or /insights/jobs for fetching new data from Facebook.

    Args:
        ad_account_id: Ad account ID (with or without act_ prefix)
        since: Start date in YYYY-MM-DD format
        until: End date in YYYY-MM-DD format
        level: Aggregation level (ad, adset, or campaign)
        time_increment: Time increment (1=daily, currently only daily is supported)
        breakdowns: Breakdown dimensions (currently not supported)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data from database

    Example:
        ```
        # Ad-level query
        GET /insights?ad_account_id=act_123&since=2024-01-01&until=2024-01-31&level=ad&time_increment=1

        # AdSet-level query (aggregates ads by adset)
        GET /insights?ad_account_id=act_123&since=2024-01-01&until=2024-01-31&level=adset&time_increment=1

        # Campaign-level query (aggregates ads by campaign)
        GET /insights?ad_account_id=act_123&since=2024-01-01&until=2024-01-31&level=campaign&time_increment=1
        ```
    """
    try:
        result = await InsightsService.query_insights_from_db(
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
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
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
            message=f"Successfully queried {result['total_records']} insight records from database",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query insights from database: {str(e)}",
        )


# ===== Synchronous Endpoint =====


@router.post("/sync", response_model=SuccessResponse[InsightsResponse])
async def fetch_insights_sync(
    request: InsightsSyncRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Synchronously fetch Facebook Ads Insights data.
    Returns data immediately (may timeout for large date ranges).

    Args:
        request: Payload describing the desired insights range/aggregation
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data with metrics and metadata

    Example:
        ```
        POST /insights/sync
        {
            "ad_account_id": "act_123",
            "since": "2025-01-01",
            "until": "2025-01-31",
            "time_increment": 1
        }
        ```
    """
    try:
        result = await InsightsService.fetch_insights_sync(
            ad_account_id=request.ad_account_id,
            since=request.since,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
            fields=request.fields,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_id=insight["ad_id"],
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
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


@router.post("/sync/from-last", response_model=SuccessResponse[InsightsResponse])
async def fetch_insights_from_last_sync(
    request: InsightsFromLastRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Fetch insights by automatically filling the realtime window using
    the account's last synced date (until + 1 day) up to the requested until date.
    """
    try:
        result = await InsightsService.fetch_insights_from_last_sync(
            ad_account_id=request.ad_account_id,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
            fields=request.fields,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_id=insight["ad_id"],
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
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
            detail=f"Failed to fetch insights from last sync: {str(e)}",
        )


@router.get(
    "/sync/status",
    response_model=SuccessResponse[InsightsAccountSyncResponse],
)
async def list_account_sync_status(
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsAccountSyncResponse]:
    """
    Retrieve per-account insights sync status.
    """
    states = await InsightsSyncService.get_account_sync_status()
    allowed_statuses = {status.value for status in SyncStatus}
    items: list[InsightAccountSyncStatus] = []
    for state in states:
        raw_status = state.get("status", SyncStatus.PENDING.value)
        if raw_status not in allowed_statuses:
            raw_status = SyncStatus.PENDING.value
        items.append(
            InsightAccountSyncStatus(
                account_id=state["account_id"],
                account_name=state.get("account_name"),
                status=SyncStatus(raw_status),
                since=state.get("since"),
                until=state.get("until"),
                obs_since=state.get("obs_since"),
                obs_until=state.get("obs_until"),
                last_synced_at=state.get("last_synced_at"),
                last_error=state.get("last_error"),
                range_since=state.get("range_since"),
                range_until=state.get("range_until"),
                mode=state.get("mode"),
                trigger=state.get("trigger"),
                triggered_by=state.get("triggered_by"),
                updated_at=state.get("updated_at"),
            )
        )
    return SuccessResponse(
        data=InsightsAccountSyncResponse(items=items),
        message=f"Fetched {len(items)} account sync records",
    )


@router.post(
    "/sync/manual",
    response_model=SuccessResponse[InsightsSyncTriggerResponse],
)
async def trigger_insights_sync(
    request: InsightsSyncTriggerRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsSyncTriggerResponse]:
    """Manually trigger insights synchronization for selected accounts within a date range."""
    try:
        since_date = datetime.strptime(request.since, "%Y-%m-%d").date()
        until_date = datetime.strptime(request.until, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Expect YYYY-MM-DD.",
        ) from exc

    try:
        result = await InsightsSyncService.trigger_manual_sync(
            account_ids=request.account_ids,
            since=since_date,
            until=until_date,
            triggered_by=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response = InsightsSyncTriggerResponse(
        total_accounts=result.total_accounts,
        processed_accounts=result.processed_accounts,
        failed_accounts=result.failed_accounts,
    )
    message = (
        f"Triggered sync for {result.total_accounts} account(s): "
        f"processed {len(result.processed_accounts)}, "
        f"failed {len(result.failed_accounts)}"
    )
    return SuccessResponse(data=response, message=message)


# ===== Asynchronous Endpoints =====


@router.post("/jobs", response_model=SuccessResponse[AsyncJobCreateResponse])
async def create_async_job(
    request: InsightsRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[AsyncJobCreateResponse]:
    """
    Create an async Facebook Ads Insights job.
    Returns job_id immediately; use GET /insights/jobs/{job_id} to check status.

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
    "/jobs/{job_id}", response_model=SuccessResponse[AsyncJobStatusResponse]
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
        GET /insights/jobs/12345678?ad_account_id=act_123456789
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
    "/jobs/{job_id}/result", response_model=SuccessResponse[InsightsResponse]
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
        GET /insights/jobs/12345678/result?ad_account_id=act_123456789
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
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
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



# ===== Entity Names Sync Endpoint =====


@router.post(
    "/entity-name-syncs",
    response_model=SuccessResponse[EntityNamesSyncResult],
)
async def sync_entity_names(
    request: EntityNamesSyncRequest,
    _current_user: str = Depends(get_current_user),
) -> SuccessResponse[EntityNamesSyncResult]:
    """
    Sync entity names for the specified entity IDs on demand.
    
    This endpoint fetches entity names from Facebook API and stores them in the database.
    It is called by the frontend when viewing insights data with unnamed entities.
    
    Args:
        ad_account_id: Ad account ID
        entity_ids: List of entity IDs that need names
        entity_type: Type of entities (ad, adset, or campaign)
        
    Returns:
        Sync result with statistics
    """
    try:
        if request.entity_type not in ["ad", "adset", "campaign"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity_type: {request.entity_type}. Must be ad, adset, or campaign",
            )

        result = await EntityNamesSyncService.sync_entity_names(
            account_id=request.ad_account_id,
            entity_ids=request.entity_ids,
            entity_type=request.entity_type,
        )

        return SuccessResponse(
            data=EntityNamesSyncResult(**result),
            message=f"Successfully synced {result['synced']} entity names",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync entity names: {str(e)}",
        )

