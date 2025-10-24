"""
Request models for ad account endpoints.
"""

from pydantic import BaseModel, Field


class AdAccountResponse(BaseModel):
    """Ad account response model."""

    id: str = Field(..., description="Ad account ID (with act_ prefix)")
    name: str = Field(..., description="Ad account name")
    has_auth: bool = Field(..., description="Whether authentication is configured")


class AdAccountListResponse(BaseModel):
    """Ad account list response model."""

    accounts: list[AdAccountResponse] = Field(..., description="List of ad accounts")
    total: int = Field(..., description="Total number of accounts")
