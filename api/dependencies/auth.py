"""
Authentication dependencies for FastAPI routes.
Extracts user identity from X-User-Id header.
"""

from typing import Annotated

from fastapi import Header, HTTPException, status


async def get_current_user(x_user_id: Annotated[str, Header()]) -> str:
    """
    Extract and validate user ID from X-User-Id header.

    Args:
        x_user_id: User ID from request header

    Returns:
        User ID string

    Raises:
        HTTPException: If X-User-Id header is missing or empty
    """
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required for authentication",
        )
    return x_user_id.strip()


# Type alias for dependency injection
CurrentUser = Annotated[str, Header()]
