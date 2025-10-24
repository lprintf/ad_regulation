"""
Response models for API endpoints.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail model."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")


class ErrorResponse(BaseModel):
    """Standard error response model."""

    success: bool = Field(False, description="Operation success status")
    error: ErrorDetail = Field(..., description="Error details")


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response model."""

    success: bool = Field(True, description="Operation success status")
    data: T = Field(..., description="Response data")
    message: str | None = Field(None, description="Optional success message")


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    database: str = Field(..., description="Database connection status")
