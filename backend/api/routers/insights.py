"""
Insights data endpoints.
Provides API for fetching Facebook Ads Insights data (sync and async).
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from api.dependencies.auth import get_current_user
from api.models.insights import (
    AsyncJobCreateResponse,
    AsyncJobStatus,
    AsyncJobStatusResponse,
    EntityNamesSyncRequest,
    EntityNamesSyncResult,
    EntityTimelineResponse,
    InsightAccountSyncStatus,
    InsightRecord,
    InsightsAccountSyncResponse,
    InsightsFromLastRequest,
    InsightsHybridRequest,
    InsightsRequest,
    InsightsResponse,
    InsightsSyncRequest,
    InsightsSyncTriggerRequest,
    InsightsSyncTriggerResponse,
    SyncHistoryListResponse,
    SyncHistoryRecord,
    SyncOverviewItem,
    SyncOverviewResponse,
    SyncStatus,
)
from api.models.responses import SuccessResponse
from api.services.insights_service import InsightsService
from api.services.insights_sync_service import InsightsSyncService
from api.services.entity_names_sync_service import EntityNamesSyncService
from api.services.sync_history_service import SyncHistoryService
from utils.account_id import normalize_account_id

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
    object_ids: Annotated[
        list[str] | None,
        Query(
            description="Optional entity IDs to filter within the selected account",
            examples=[["123", "456"]],
        ),
    ] = None,
    object_level: Annotated[
        str | None,
        Query(
            alias="obj_level",
            description="Level for the provided object_ids (ad, adset, campaign)",
            examples=["campaign"],
        ),
    ] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query Facebook Ads Insights data from MongoDB + Redis hybrid cache.
    Automatically splits date range: MongoDB for historical data (> 3 days ago), Redis for recent data (last 3 days).
    This endpoint does NOT call Facebook API - it returns cached data only.

    Supports aggregation by level:
    - level="ad": Returns ad-level data (no aggregation)
    - level="adset": Aggregates ad data by adset_id and date
    - level="campaign": Aggregates ad data by campaign_id and date

    Use this for viewing recent + historical data with fast performance. Use /insights/query or /insights/jobs for fetching new data from Facebook.

    Args:
        ad_account_id: Ad account ID (with or without act_ prefix)
        since: Start date in YYYY-MM-DD format
        until: End date in YYYY-MM-DD format
        level: Aggregation level (ad, adset, or campaign)
        time_increment: Time increment (1=daily, currently only daily is supported)
        breakdowns: Breakdown dimensions (currently not supported)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data from hybrid cache (MongoDB + Redis)

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
        result = await InsightsService.query_insights_mongo_redis(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=True,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or ad_account_id,
                    ad_id=insight.get("ad_id") if level == "ad" else None,
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
            last_synced_date=result.get("last_synced_date"),
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


# ===== Database Query Endpoints =====


@router.get("/query/mongo", response_model=SuccessResponse[InsightsResponse])
async def query_insights_mongo_only(
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
    object_ids: Annotated[
        list[str] | None,
        Query(
            description="Optional entity IDs to filter within the selected account",
            examples=[["123", "456"]],
        ),
    ] = None,
    object_level: Annotated[
        str | None,
        Query(
            alias="obj_level",
            description="Level for the provided object_ids (ad, adset, campaign)",
            examples=["campaign"],
        ),
    ] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query Facebook Ads Insights data from MongoDB only (pure historical data).
    No Redis cache, no Facebook API calls.

    Returns:
        SuccessResponse containing insights data from MongoDB
    """
    try:
        result = await InsightsService.query_insights_mongo_only(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=True,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or ad_account_id,
                    ad_id=insight.get("ad_id") if level == "ad" else None,
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
            last_synced_date=result.get("last_synced_date"),
        )

        return SuccessResponse(
            data=insights_data,
            message=f"Successfully queried {result['total_records']} insight records from MongoDB",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query insights from MongoDB: {str(e)}",
        )


@router.get("/query/mongo_redis", response_model=SuccessResponse[InsightsResponse])
async def query_insights_mongo_redis_hybrid(
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
    object_ids: Annotated[
        list[str] | None,
        Query(
            description="Optional entity IDs to filter within the selected account",
            examples=[["123", "456"]],
        ),
    ] = None,
    object_level: Annotated[
        str | None,
        Query(
            alias="obj_level",
            description="Level for the provided object_ids (ad, adset, campaign)",
            examples=["campaign"],
        ),
    ] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query Facebook Ads Insights data from MongoDB + Redis hybrid cache.
    Automatically splits date range: MongoDB for historical (> 3 days ago), Redis for recent (last 3 days).

    Returns:
        SuccessResponse containing insights data from hybrid cache
    """
    try:
        result = await InsightsService.query_insights_mongo_redis(
            ad_account_id=ad_account_id,
            since=since,
            until=until,
            level=level,
            time_increment=time_increment,
            breakdowns=breakdowns,
            object_level=object_level,
            object_ids=object_ids,
            mask_ad_ids=True,
        )

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or ad_account_id,
                    ad_id=insight.get("ad_id") if level == "ad" else None,
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
            last_synced_date=result.get("last_synced_date"),
        )

        return SuccessResponse(
            data=insights_data,
            message=f"Successfully queried {result['total_records']} insight records from hybrid cache",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query insights from hybrid cache: {str(e)}",
        )


# ===== Realtime Query Endpoints =====


@router.post("/query", response_model=SuccessResponse[InsightsResponse])
async def query_insights_realtime(
    request: InsightsSyncRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query Facebook Ads Insights data by merging cached (DB) and realtime (API) windows.
    Returns data immediately (may timeout for large date ranges).

    Args:
        request: Payload describing the desired insights range/aggregation
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing insights data with metrics and metadata

    Example:
        ```
        POST /insights/query
        {
            "ad_account_id": "act_123",
            "since": "2025-01-01",
            "until": "2025-01-31",
            "time_increment": 1
        }
        ```
    """
    try:
        result = await InsightsService.query_insights_realtime(
            ad_account_id=request.ad_account_id,
            since=request.since,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
            fields=request.fields,
            object_level=request.object_level,
            object_ids=request.object_ids,
        )

        response_level = request.level or "ad"

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or request.ad_account_id,
                    ad_id=insight.get("ad_id") if response_level == "ad" else None,
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
                    configured_status=insight.get("configured_status"),
                    effective_status=insight.get("effective_status"),
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


@router.post("/query/mongo_from-last", response_model=SuccessResponse[InsightsResponse])
async def query_insights_mongo_from_last_hybrid(
    request: InsightsHybridRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Query MongoDB + Facebook API from-last gap fill in a single round-trip.
    Fetches cached data from MongoDB, then fills missing recent data using Facebook API from_last.
    Preferred replacement for calling /query/mongo + /query/from-last separately.
    """
    try:
        result = await InsightsService.query_insights_hybrid(
            ad_account_id=request.ad_account_id,
            since=request.since,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
            fields=request.fields,
            object_level=request.object_level,
            object_ids=request.object_ids,
            cache_window_hint=request.cache_window_hint,
        )

        response_level = request.level or "ad"
        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or request.ad_account_id,
                    ad_id=insight.get("ad_id") if response_level == "ad" else None,
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
                    configured_status=insight.get("configured_status"),
                    effective_status=insight.get("effective_status"),
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
            message=f"Successfully fetched {result['total_records']} hybrid insight records",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch hybrid insights: {str(e)}",
        )


def _apply_cache_control(response: Response, seconds: int = 60) -> None:
    response.headers["Cache-Control"] = f"public, max-age={seconds}"


async def _execute_query_from_last(
    request: InsightsFromLastRequest,
) -> SuccessResponse[InsightsResponse]:
    try:
        result = await InsightsService.query_insights_from_last_gap(
            ad_account_id=request.ad_account_id,
            until=request.until,
            level=request.level,
            time_increment=request.time_increment,
            breakdowns=request.breakdowns,
            fields=request.fields,
            object_level=request.object_level,
            object_ids=request.object_ids,
            cache_window_hint=request.cache_window_hint,
        )

        response_level = request.level or "ad"

        insights_data = InsightsResponse(
            insights=[
                InsightRecord(
                    ad_account_id=insight.get("ad_account_id") or ad_account_id,
                    ad_id=insight.get("ad_id") if response_level == "ad" else None,
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
                    configured_status=insight.get("configured_status"),
                    effective_status=insight.get("effective_status"),
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


@router.get("/query/from-last", response_model=SuccessResponse[InsightsResponse])
async def query_insights_from_last_gap_get(
    request: Annotated[InsightsFromLastRequest, Depends()],
    response: Response,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    Fetch insights by automatically filling the realtime window using
    the account's last synced date (until + 1 day) up to the requested until date.
    """
    _apply_cache_control(response)
    return await _execute_query_from_last(request)


@router.post("/query/from-last", response_model=SuccessResponse[InsightsResponse])
async def query_insights_from_last_gap_post(
    request: InsightsFromLastRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsResponse]:
    """
    POST-compatible variant for legacy callers. Prefer GET /insights/query/from-last.
    """
    return await _execute_query_from_last(request)


@router.get("/sync/overview", response_model=SuccessResponse[SyncOverviewResponse])
async def get_sync_overview(
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[SyncOverviewResponse]:
    """
    Get sync overview for all ad accounts.
    Shows current sync status, data coverage, and last sync information.

    Returns:
        SuccessResponse containing sync overview for all accounts
    """
    try:
        items_data = await SyncHistoryService.get_sync_overview()

        items = [SyncOverviewItem(**item) for item in items_data]

        return SuccessResponse(
            data=SyncOverviewResponse(
                items=items,
                total_accounts=len(items),
            ),
            message=f"Retrieved sync overview for {len(items)} accounts",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync overview: {str(e)}",
        )


@router.get("/sync/history", response_model=SuccessResponse[SyncHistoryListResponse])
async def get_sync_history(
    account_id: Annotated[
        str | None,
        Query(description="Filter by account ID (optional)"),
    ] = None,
    sync_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by status (pending/running/success/failed)",
        ),
    ] = None,
    trigger_type: Annotated[
        str | None,
        Query(description="Filter by trigger type (manual/auto/retry)"),
    ] = None,
    data_target: Annotated[
        str | None,
        Query(description="Filter by data target (mongodb/redis/hybrid)"),
    ] = None,
    page: Annotated[int, Query(description="Page number (1-indexed)", ge=1)] = 1,
    page_size: Annotated[
        int, Query(description="Records per page", ge=1, le=100)
    ] = 50,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[SyncHistoryListResponse]:
    """
    Get paginated sync history records with optional filters.

    Args:
        account_id: Filter by account ID
        sync_status: Filter by status
        trigger_type: Filter by trigger type
        data_target: Filter by data target (mongodb/redis/hybrid)
        page: Page number (1-indexed)
        page_size: Records per page (max 100)
        user_id: Current user ID

    Returns:
        SuccessResponse containing paginated sync history
    """
    try:
        items_data, total = await SyncHistoryService.get_history_list(
            account_id=account_id,
            status=sync_status,
            trigger_type=trigger_type,
            data_target=data_target,
            page=page,
            page_size=page_size,
        )

        items = [SyncHistoryRecord(**item) for item in items_data]

        return SuccessResponse(
            data=SyncHistoryListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
            ),
            message=f"Retrieved {len(items)} sync history records (page {page}/{(total + page_size - 1) // page_size})",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync history: {str(e)}",
        )


@router.get("/sync/history/{history_id}", response_model=SuccessResponse[SyncHistoryRecord])
async def get_sync_history_detail(
    history_id: str,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[SyncHistoryRecord]:
    """
    Get detailed information for a single sync history record.

    Args:
        history_id: Sync history record ID
        user_id: Current user ID

    Returns:
        SuccessResponse containing sync history details
    """
    try:
        history_data = await SyncHistoryService.get_history_by_id(history_id)

        if not history_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sync history record {history_id} not found",
            )

        return SuccessResponse(
            data=SyncHistoryRecord(**history_data),
            message="Retrieved sync history details",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync history details: {str(e)}",
        )


@router.post("/sync/trigger", response_model=SuccessResponse[InsightsSyncTriggerResponse])
async def trigger_sync(
    request: InsightsSyncTriggerRequest,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[InsightsSyncTriggerResponse]:
    """
    Manually trigger insights synchronization for selected accounts.
    Creates sync history records and initiates the sync process.

    Args:
        request: Sync trigger request with account_ids, since, until
        user_id: Current user ID

    Returns:
        SuccessResponse with trigger result summary
    """
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


@router.post("/sync/trigger-account/{account_id}", response_model=SuccessResponse[dict])
async def trigger_account_sync(
    account_id: str,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[dict]:
    """
    Trigger sync for a single account with default time range (last 30 days).
    DEPRECATED: Use /sync/trigger-mongodb or /sync/trigger-redis instead.

    Args:
        account_id: Account ID to sync (with or without act_ prefix)
        user_id: Current user ID

    Returns:
        SuccessResponse with trigger result
    """
    # Use default time range: last 30 days
    today = datetime.utcnow().date()
    since_date = today - timedelta(days=30)

    try:
        result = await InsightsSyncService.trigger_manual_sync(
            account_ids=[account_id],
            since=since_date,
            until=today,
            triggered_by=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Check if the account was processed or failed
    if account_id in result.failed_accounts:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {result.failed_accounts[account_id]}"
        )

    return SuccessResponse(
        data={
            "account_id": account_id,
            "since": since_date.isoformat(),
            "until": today.isoformat(),
            "triggered": True
        },
        message=f"Successfully triggered sync for {account_id}"
    )


@router.post("/sync/trigger-mongodb/{account_id}", response_model=SuccessResponse[dict])
async def trigger_mongodb_sync(
    account_id: str,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[dict]:
    """
    Trigger MongoDB sync for a single account with default strategy:
    - From last_synced_date + 1 day to (today - 3 days)
    - If no last_synced_date, sync from 37 months ago
    - Mode: Async for large ranges (>3 days), sync for small ranges

    Args:
        account_id: Account ID to sync (with or without act_ prefix)
        user_id: Current user ID

    Returns:
        SuccessResponse with trigger result
    """
    from utils.db import get_all_ad_account_documents, InsightsSyncStateDocument

    # Get the account
    normalized_id = normalize_account_id(account_id)
    accounts = await get_all_ad_account_documents(fetch_links=True)
    account = next((acc for acc in accounts if normalize_account_id(acc.id) == normalized_id), None)

    if not account:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    today = datetime.utcnow().date()
    # Target date: 3 days ago (to avoid realtime data instability)
    until_date = today - timedelta(days=3)

    # Use a placeholder since date, will be overridden by respect_last_synced logic
    # But provide a reasonable fallback in case there's no last_synced_date
    since_date = until_date - timedelta(days=1)

    try:
        # Get states
        states = await InsightsSyncStateDocument.find_all().to_list()
        state_map = {state.account_id: state for state in states}

        # Call sync_range with respect_last_synced=True
        result = await InsightsSyncService.sync_range(
            since=since_date,
            until=until_date,
            mode="manual",
            triggered_by=user_id,
            accounts=[account],
            state_map=state_map,
            respect_last_synced=True,  # This will use last_synced_date + 1 if available
        )

        if normalized_id in result.failed_accounts:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger MongoDB sync: {result.failed_accounts[normalized_id]}"
            )

        return SuccessResponse(
            data={
                "account_id": account_id,
                "data_target": "mongodb",
                "triggered": True,
                "processed": len(result.processed_accounts) > 0
            },
            message=f"Successfully triggered MongoDB sync for {account_id}"
        )

    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger MongoDB sync: {str(exc)}"
        ) from exc


@router.post("/sync/trigger-redis/{account_id}", response_model=SuccessResponse[dict])
async def trigger_redis_sync(
    account_id: str,
    user_id: Annotated[str, Depends(get_current_user)] = None,
) -> SuccessResponse[dict]:
    """
    Trigger Redis cache sync for a single account with default strategy:
    - From last_synced_date + 1 day to today (max 7 days lookback)
    - Mode: Sync to Redis cache

    Args:
        account_id: Account ID to sync (with or without act_ prefix)
        user_id: Current user ID

    Returns:
        SuccessResponse with trigger result
    """
    from api.services.realtime_cache_scheduler import sync_redis_for_account
    from utils.db import get_all_ad_account_documents

    # Get the account
    normalized_id = normalize_account_id(account_id)
    accounts = await get_all_ad_account_documents(fetch_links=True)
    account = next((acc for acc in accounts if normalize_account_id(acc.id) == normalized_id), None)

    if not account:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    try:
        synced_records, error_msg = await sync_redis_for_account(
            account,
            trigger_type="manual",
            triggered_by=user_id,
        )

        if error_msg:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger Redis sync: {error_msg}"
            )

        if synced_records == 0:
            return SuccessResponse(
                data={
                    "account_id": account_id,
                    "data_target": "redis",
                    "triggered": False,
                    "reason": "already_up_to_date"
                },
                message=f"Redis cache for {account_id} is already up to date"
            )

        return SuccessResponse(
            data={
                "account_id": account_id,
                "data_target": "redis",
                "records_synced": synced_records,
                "triggered": True
            },
            message=f"Successfully synced {synced_records} records to Redis for {account_id}"
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger Redis sync: {str(exc)}"
        ) from exc


# ===== DEPRECATED: Old sync endpoint for backward compatibility =====

@router.get("/sync/runs", deprecated=True, response_model=SuccessResponse[InsightsAccountSyncResponse])
async def list_sync_runs(
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


# ===== DEPRECATED: Old sync endpoint - use /sync/trigger instead =====

@router.post("/sync/runs", deprecated=True, response_model=SuccessResponse[InsightsSyncTriggerResponse])
async def trigger_sync_run(
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
                    ad_account_id=insight.get("ad_account_id") or ad_account_id,
                    ad_id=insight.get("ad_id"),
                    adset_id=insight.get("adset_id"),
                    campaign_id=insight.get("campaign_id"),
                    ad_name=insight.get("ad_name"),
                    adset_name=insight.get("adset_name"),
                    campaign_name=insight.get("campaign_name"),
                    configured_status=insight.get("configured_status"),
                    effective_status=insight.get("effective_status"),
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

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync entity names: {str(e)}",
        )


@router.get("/entity-timeline", response_model=SuccessResponse[EntityTimelineResponse])
async def get_entity_timeline(
    ad_account_id: Annotated[str, Query(description="Ad account ID")],
    entity_id: Annotated[str, Query(description="Entity ID (ad/adset/campaign)")],
    entity_type: Annotated[str, Query(description="Entity type")] = "ad",
    _current_user: str = Depends(get_current_user),
) -> SuccessResponse[EntityTimelineResponse]:
    """
    Get timeline data for a specific entity.

    Returns daily metrics (spend, clicks, impressions) for the entity,
    with date range extended by ±1 day for better visualization context.
    Used by the frontend's date selector to show a timeline chart.

    Args:
        ad_account_id: Ad account ID
        entity_id: Entity ID
        entity_type: Type of entity (ad, adset, or campaign)

    Returns:
        Timeline data with daily metrics
    """
    try:
        if entity_type not in ["ad", "adset", "campaign"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity_type: {entity_type}. Must be ad, adset, or campaign",
            )

        result = await InsightsService.get_entity_timeline(
            ad_account_id=normalize_account_id(ad_account_id),
            entity_id=entity_id,
            entity_type=entity_type,
        )

        return SuccessResponse(
            data=EntityTimelineResponse(**result),
            message=f"Successfully fetched timeline for {entity_type} {entity_id}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch entity timeline: {str(e)}",
        )

