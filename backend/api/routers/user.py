"""
User information endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Header

from api.models.responses import SuccessResponse
from pydantic import BaseModel


router = APIRouter(prefix="/user", tags=["User"])


class UserInfo(BaseModel):
    """User information model."""

    user_id: str
    email: str | None = None
    name: str | None = None


@router.get("/me", response_model=SuccessResponse[UserInfo])
async def get_current_user_info(
    x_user_id: Annotated[str, Header()],
    x_user_email: Annotated[str | None, Header()] = None,
    x_user_name: Annotated[str | None, Header()] = None,
) -> SuccessResponse[UserInfo]:
    """
    Get current user information from request headers.

    Headers are injected by the authentication gateway (Traefik OIDC or nginx in dev mode).

    Args:
        x_user_id: User ID from X-User-Id header
        x_user_email: User email from X-User-Email header
        x_user_name: User display name from X-User-Name header

    Returns:
        SuccessResponse containing user information
    """
    user_info = UserInfo(
        user_id=x_user_id,
        email=x_user_email,
        name=x_user_name,
    )

    return SuccessResponse(data=user_info)
