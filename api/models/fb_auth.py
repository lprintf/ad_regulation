"""
Pydantic models for Facebook app authentication management.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FbAppSeedRequest(BaseModel):
    """Manual seed request containing app credentials and token."""

    app_id: str = Field(..., description="Facebook App ID")
    app_secret: str = Field(..., description="Facebook App Secret")
    access_token: str = Field(..., description="User or system user access token")


class FbAdAccountModel(BaseModel):
    """Simplified ad account representation."""

    id: str = Field(..., description="Ad account ID with act_ prefix")
    name: str = Field(..., description="Ad account display name")


class FbAppAuthSyncResult(BaseModel):
    """Response model summarising auth + token state after sync."""

    app_id: str = Field(..., description="Facebook App ID")
    user_id: str | None = Field(None, description="Token owner user ID")
    user_name: str | None = Field(None, description="Token owner display name")
    type: Literal["SYSTEM_USER", "USER"] | None = Field(
        None, description="Access token type"
    )
    application: str | None = Field(None, description="Application display name")
    is_valid: bool | None = Field(None, description="Whether Facebook reports token valid")
    expires_at: datetime | None = Field(
        None, description="Token expiry timestamp in UTC"
    )
    data_access_expires_at: datetime | None = Field(
        None, description="Data access expiry timestamp in UTC"
    )
    scopes: list[str] = Field(default_factory=list, description="Granted token scopes")
    granular_scopes: list[dict[str, Any]] = Field(
        default_factory=list, description="Granular scope assignments"
    )
    accounts: list[FbAdAccountModel] = Field(
        default_factory=list, description="Accounts discovered for this token"
    )
    last_synced_at: datetime = Field(
        ..., description="When credentials were last synchronised"
    )
    last_synced_by: str | None = Field(
        None, description="Which internal user triggered the last sync"
    )
    access_token_last4: str | None = Field(
        None, description="Last four characters of stored access token"
    )

    @field_validator("scopes", mode="before")
    @classmethod
    def _ensure_list(cls, value):
        if value is None:
            return []
        return value
