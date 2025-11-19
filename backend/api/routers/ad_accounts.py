"""
Ad account management router.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.auth import get_current_user
from api.models.ad_accounts import AdAccountListResponse, AdAccountResponse
from api.models.responses import SuccessResponse
from utils.db import ADAccountDocument, get_all_ad_account_documents

router = APIRouter(prefix="/ad-accounts", tags=["Ad Accounts"])


@router.get("", response_model=SuccessResponse[AdAccountListResponse])
async def list_ad_accounts(
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[AdAccountListResponse]:
    """
    List all ad accounts accessible by the current user.

    Args:
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing list of ad accounts

    Note:
        Currently returns all ad accounts. Future implementation will filter by user permissions.
    """
    # TODO: Filter by user permissions using BIUserAdAccountLink
    ad_accounts = await get_all_ad_account_documents(fetch_links=True)

    accounts = [
        AdAccountResponse(
            id=acc.id, name=acc.name, has_auth=acc.fb_app_auth is not None
        )
        for acc in ad_accounts
    ]

    return SuccessResponse(
        data=AdAccountListResponse(accounts=accounts, total=len(accounts))
    )


@router.get("/{account_id}", response_model=SuccessResponse[AdAccountResponse])
async def get_ad_account(
    account_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SuccessResponse[AdAccountResponse]:
    """
    Get details of a specific ad account.

    Args:
        account_id: Ad account ID (with or without act_ prefix)
        user_id: Current user ID from X-User-Id header

    Returns:
        SuccessResponse containing ad account details

    Raises:
        HTTPException: If account not found or user has no access
    """
    # Normalize account ID
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    # TODO: Check user permissions using BIUserAdAccountLink
    ad_account = await ADAccountDocument.find_one(
        ADAccountDocument.id == account_id, fetch_links=True
    )

    if not ad_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ad account {account_id} not found",
        )

    return SuccessResponse(
        data=AdAccountResponse(
            id=ad_account.id,
            name=ad_account.name,
            has_auth=ad_account.fb_app_auth is not None,
        )
    )
