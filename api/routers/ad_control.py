"""
Ad Control Router - API endpoints for ad operations
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies.auth import get_current_user
from api.models.ad_control import (
    ActivitiesResponse,
    AdOperationRequest,
    AdOperationResponse,
    AdSetBudgetOperationResponse,
    AdSetBudgetResponse,
    AdStatusResponse,
    UpdateAdNameRequest,
    UpdateAdSetBudgetRequest,
)
from api.models.responses import SuccessResponse
from api.services.ad_control_service import AdControlService

router = APIRouter(prefix="/ad-control", tags=["Ad Control"])


@router.get(
    "/status",
    response_model=SuccessResponse[AdStatusResponse],
    summary="Get Ad Status",
    description="Get current status and details of an ad",
)
async def get_ad_status(
    ad_account_id: str, ad_id: str, user_id: str = Depends(get_current_user)
):
    """
    Get ad status and details

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **ad_id**: Ad ID to query
    """
    try:
        result = await AdControlService.get_ad_status(ad_account_id, ad_id)
        return SuccessResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/start",
    response_model=SuccessResponse[AdOperationResponse],
    summary="Start Ad",
    description="Activate (start) an ad",
)
async def start_ad(
    request: AdOperationRequest, user_id: str = Depends(get_current_user)
):
    """
    Start (activate) an ad

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **ad_id**: Ad ID to start
    """
    try:
        result = await AdControlService.start_ad(request.ad_account_id, request.ad_id)
        return SuccessResponse(data=result, message="Ad started successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/stop",
    response_model=SuccessResponse[AdOperationResponse],
    summary="Stop Ad",
    description="Pause (stop) an ad",
)
async def stop_ad(
    request: AdOperationRequest, user_id: str = Depends(get_current_user)
):
    """
    Stop (pause) an ad

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **ad_id**: Ad ID to stop
    """
    try:
        result = await AdControlService.stop_ad(request.ad_account_id, request.ad_id)
        return SuccessResponse(data=result, message="Ad stopped successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/update-name",
    response_model=SuccessResponse[AdOperationResponse],
    summary="Update Ad Name",
    description="Update the name of an ad",
)
async def update_ad_name(
    request: UpdateAdNameRequest, user_id: str = Depends(get_current_user)
):
    """
    Update ad name

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **ad_id**: Ad ID to update
    - **new_name**: New name for the ad
    """
    try:
        result = await AdControlService.update_ad_name(
            request.ad_account_id, request.ad_id, request.new_name
        )
        return SuccessResponse(data=result, message="Ad name updated successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/adset/budget",
    response_model=SuccessResponse[AdSetBudgetResponse],
    summary="Get AdSet Budget",
    description="Get budget information for an AdSet (budget is set at AdSet level)",
)
async def get_adset_budget(
    ad_account_id: str, adset_id: str, user_id: str = Depends(get_current_user)
):
    """
    Get AdSet budget information

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **adset_id**: AdSet ID to query
    """
    try:
        result = await AdControlService.get_adset_budget(ad_account_id, adset_id)
        return SuccessResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post(
    "/adset/update-budget",
    response_model=SuccessResponse[AdSetBudgetOperationResponse],
    summary="Update AdSet Budget",
    description="Update budget for an AdSet (budget is set at AdSet level, not Ad level)",
)
async def update_adset_budget(
    request: UpdateAdSetBudgetRequest, user_id: str = Depends(get_current_user)
):
    """
    Update AdSet budget

    Note: Budget values are in cents (e.g., 10000 = $100.00)

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **adset_id**: AdSet ID to update
    - **daily_budget**: Daily budget in cents (optional)
    - **lifetime_budget**: Lifetime budget in cents (optional)
    """
    try:
        result = await AdControlService.update_adset_budget(
            request.ad_account_id,
            request.adset_id,
            request.daily_budget,
            request.lifetime_budget,
        )
        return SuccessResponse(data=result, message="AdSet budget updated successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/activities",
    response_model=SuccessResponse[ActivitiesResponse],
    summary="Get Account Activities",
    description="Get historical modification records (activity log) for an ad account",
)
async def get_account_activities(
    ad_account_id: str,
    object_id: Optional[str] = None,
    limit: int = 100,
    user_id: str = Depends(get_current_user),
):
    """
    Get account activities (operation history/audit log)

    This endpoint retrieves the modification history for all objects in an ad account,
    or for a specific object if object_id is provided.

    - **ad_account_id**: Ad account ID (with or without act_ prefix)
    - **object_id**: Optional filter by specific object ID (ad, adset, or campaign)
    - **limit**: Maximum number of activities to retrieve (default: 100, max: 10000)

    Returns a list of activities with information about:
    - Who made the change (actor_name)
    - When the change was made (event_time)
    - What type of change (event_type)
    - What object was changed (object_type, object_id, object_name)
    - Additional details (extra_data)
    """
    try:
        result = await AdControlService.get_account_activities(
            ad_account_id, object_id, limit
        )
        return SuccessResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
