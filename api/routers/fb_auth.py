"""
Router exposing Facebook credential onboarding endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.auth import get_current_user
from api.models.fb_auth import FbAppAuthSyncResult, FbAppSeedRequest
from api.models.responses import SuccessResponse
from api.services.fb_auth_service import (
    FacebookAuthError,
    list_fb_app_credentials,
    refresh_fb_app_token,
    resync_fb_app_accounts,
    sync_fb_app_credentials,
)
from utils.schemas.ad_account import FbAppSeedInfo

router = APIRouter(prefix="/fb/auth", tags=["Facebook Auth"])


@router.get(
    "/app-tokens",
    response_model=SuccessResponse[list[FbAppAuthSyncResult]],
    summary="List stored Facebook app credentials",
)
async def list_app_tokens(
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[list[FbAppAuthSyncResult]]:
    """
    Retrieve all stored Facebook credential records alongside token metadata and linked accounts.
    """

    records = await list_fb_app_credentials()
    return SuccessResponse(data=records)


@router.post(
    "/app-tokens",
    response_model=SuccessResponse[FbAppAuthSyncResult],
    status_code=status.HTTP_201_CREATED,
    summary="Validate and persist Facebook app credentials",
)
async def sync_app_token(
    payload: FbAppSeedRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[FbAppAuthSyncResult]:
    """
    Validate credentials against Facebook, store token + auth info, and synchronise accessible accounts.
    """

    seed_info = FbAppSeedInfo(**payload.model_dump())

    try:
        result = await sync_fb_app_credentials(seed_info, triggered_by=user_id)
    except FacebookAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": str(exc),
                "code": exc.code,
                "details": exc.details,
            },
        ) from exc

    return SuccessResponse(
        data=result,
        message="Facebook app token synchronised",
    )


@router.post(
    "/app-tokens/{app_id}/{token_user_id}/refresh",
    response_model=SuccessResponse[FbAppAuthSyncResult],
    summary="Refresh a stored Facebook app token",
)
async def refresh_app_token(
    app_id: str,
    token_user_id: str,
    current_user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[FbAppAuthSyncResult]:
    """
    Refresh a stored Facebook token and extend its validity when close to expiry.
    """

    try:
        result = await refresh_fb_app_token(
            app_id,
            token_user_id,
            triggered_by=current_user_id,
        )
    except FacebookAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": str(exc),
                "code": exc.code,
                "details": exc.details,
            },
        ) from exc

    return SuccessResponse(
        data=result,
        message="Facebook app token refreshed",
    )


@router.post(
    "/app-tokens/{app_id}/{token_user_id}/sync",
    response_model=SuccessResponse[FbAppAuthSyncResult],
    summary="Re-sync ad accounts for a stored token",
)
async def resync_app_token_accounts(
    app_id: str,
    token_user_id: str,
    current_user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[FbAppAuthSyncResult]:
    """
    Refresh account mappings and metadata for an existing token without exchanging it.
    """

    try:
        result = await resync_fb_app_accounts(
            app_id,
            token_user_id,
            triggered_by=current_user_id,
        )
    except FacebookAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": str(exc),
                "code": exc.code,
                "details": exc.details,
            },
        ) from exc

    return SuccessResponse(
        data=result,
        message="Facebook app token accounts re-synchronised",
    )
