"""
Ad Control Models - Request and response models for ad operations
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AdStatusResponse(BaseModel):
    """Response model for ad status"""
    ad_id: str
    name: str
    configured_status: str = Field(description="Configured status (active, paused, archived, deleted)")
    effective_status: str = Field(description="Effective status considering parent campaign/adset status")
    campaign_id: str
    adset_id: str
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


class AdOperationRequest(BaseModel):
    """Request model for ad operations"""
    ad_account_id: str = Field(description="Ad account ID (with or without act_ prefix)")
    ad_id: str = Field(description="Ad ID to operate on")


class UpdateAdNameRequest(BaseModel):
    """Request model for updating ad name"""
    ad_account_id: str = Field(description="Ad account ID (with or without act_ prefix)")
    ad_id: str = Field(description="Ad ID to update")
    new_name: str = Field(description="New name for the ad")


class AdSetBudgetResponse(BaseModel):
    """Response model for adset budget"""
    adset_id: str
    name: str
    daily_budget: Optional[str] = Field(None, description="Daily budget in cents")
    lifetime_budget: Optional[str] = Field(None, description="Lifetime budget in cents")
    budget_remaining: Optional[str] = Field(None, description="Remaining budget in cents")


class UpdateAdSetBudgetRequest(BaseModel):
    """Request model for updating adset budget"""
    ad_account_id: str = Field(description="Ad account ID (with or without act_ prefix)")
    adset_id: str = Field(description="AdSet ID to update")
    daily_budget: Optional[int] = Field(None, description="Daily budget in cents (e.g., 10000 = $100.00)")
    lifetime_budget: Optional[int] = Field(None, description="Lifetime budget in cents")

    class Config:
        json_schema_extra = {
            "example": {
                "ad_account_id": "act_1279567647104057",
                "adset_id": "120234815168290189",
                "daily_budget": 10000
            }
        }


class AdOperationResponse(BaseModel):
    """Response model for ad operations"""
    success: bool
    message: str
    ad_status: Optional[AdStatusResponse] = None


class AdSetBudgetOperationResponse(BaseModel):
    """Response model for adset budget operations"""
    success: bool
    message: str
    adset_budget: Optional[AdSetBudgetResponse] = None


class ActivityRecord(BaseModel):
    """Model for a single activity record"""
    event_time: Optional[str] = Field(None, description="Time when the event occurred")
    actor_name: Optional[str] = Field(None, description="Name of the person/system that performed the action")
    event_type: Optional[str] = Field(None, description="Type of event (e.g., create, update, delete)")
    object_type: Optional[str] = Field(None, description="Type of object (e.g., ad, adset, campaign)")
    object_id: Optional[str] = Field(None, description="ID of the object that was modified")
    object_name: Optional[str] = Field(None, description="Name of the object")
    extra_data: Optional[Dict[str, Any]] = Field(None, description="Additional metadata about the change")


class GetActivitiesRequest(BaseModel):
    """Request model for getting account activities"""
    ad_account_id: str = Field(description="Ad account ID (with or without act_ prefix)")
    object_id: Optional[str] = Field(None, description="Filter by specific object ID (ad, adset, campaign)")
    limit: int = Field(default=100, ge=1, le=10000, description="Maximum number of activities to retrieve")

    class Config:
        json_schema_extra = {
            "example": {
                "ad_account_id": "act_1279567647104057",
                "object_id": "120234815168290189",
                "limit": 100
            }
        }


class ActivitiesResponse(BaseModel):
    """Response model for account activities"""
    total_activities: int = Field(description="Total number of activities returned")
    activities: List[Dict[str, Any]] = Field(description="List of activity records")
