"""
Ad Control Service - Handles Facebook ad operations
"""

from typing import Any, Dict, Optional

from facebook_business.adobjects.ad import Ad
from facebook_business.exceptions import FacebookRequestError

from utils.account_id import normalize_account_id
from utils.fb_api_flyweight_factory import get_ad_object


class AdControlService:
    """Service for controlling Facebook ads"""

    @staticmethod
    async def get_ad_status(ad_account_id: str, ad_id: str) -> Dict[str, Any]:
        """
        Get current status and details of an ad

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            ad_id: Ad ID

        Returns:
            Dictionary containing ad status and details
        """
        try:
            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get ad object
            ad = await get_ad_object(ad_account_id, ad_id)

            # Fetch ad details
            fields = [
                Ad.Field.id,
                Ad.Field.name,
                Ad.Field.configured_status,
                Ad.Field.effective_status,
                Ad.Field.campaign_id,
                Ad.Field.adset_id,
                Ad.Field.created_time,
                Ad.Field.updated_time,
            ]

            ad_data = ad.api_get(fields=fields)

            return {
                "ad_id": ad_data.get(Ad.Field.id),
                "name": ad_data.get(Ad.Field.name),
                "configured_status": ad_data.get(Ad.Field.configured_status),
                "effective_status": ad_data.get(Ad.Field.effective_status),
                "campaign_id": ad_data.get(Ad.Field.campaign_id),
                "adset_id": ad_data.get(Ad.Field.adset_id),
                "created_time": ad_data.get(Ad.Field.created_time),
                "updated_time": ad_data.get(Ad.Field.updated_time),
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to get ad status: {str(e)}")

    @staticmethod
    async def start_ad(ad_account_id: str, ad_id: str) -> Dict[str, Any]:
        """
        Start (activate) an ad

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            ad_id: Ad ID

        Returns:
            Dictionary with operation result
        """
        try:
            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get ad object
            ad = await get_ad_object(ad_account_id, ad_id)

            # Update status to active
            ad.api_update(
                params={Ad.Field.configured_status: Ad.ConfiguredStatus.active}
            )

            # Verify the change
            updated_ad = await AdControlService.get_ad_status(ad_account_id, ad_id)

            return {
                "success": True,
                "message": f"Ad {ad_id} started successfully",
                "ad_status": updated_ad,
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to start ad: {str(e)}")

    @staticmethod
    async def stop_ad(ad_account_id: str, ad_id: str) -> Dict[str, Any]:
        """
        Stop (pause) an ad

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            ad_id: Ad ID

        Returns:
            Dictionary with operation result
        """
        try:
            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get ad object
            ad = await get_ad_object(ad_account_id, ad_id)

            # Update status to paused
            ad.api_update(
                params={Ad.Field.configured_status: Ad.ConfiguredStatus.paused}
            )

            # Verify the change
            updated_ad = await AdControlService.get_ad_status(ad_account_id, ad_id)

            return {
                "success": True,
                "message": f"Ad {ad_id} stopped successfully",
                "ad_status": updated_ad,
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to stop ad: {str(e)}")

    @staticmethod
    async def update_ad_name(
        ad_account_id: str, ad_id: str, new_name: str
    ) -> Dict[str, Any]:
        """
        Update ad name

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            ad_id: Ad ID
            new_name: New name for the ad

        Returns:
            Dictionary with operation result
        """
        try:
            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get ad object
            ad = await get_ad_object(ad_account_id, ad_id)

            # Update name
            ad.api_update(params={Ad.Field.name: new_name})

            # Verify the change
            updated_ad = await AdControlService.get_ad_status(ad_account_id, ad_id)

            return {
                "success": True,
                "message": "Ad name updated successfully",
                "ad_status": updated_ad,
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to update ad name: {str(e)}")

    @staticmethod
    async def get_adset_budget(ad_account_id: str, adset_id: str) -> Dict[str, Any]:
        """
        Get AdSet budget information (budget is set at AdSet level, not Ad level)

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            adset_id: AdSet ID

        Returns:
            Dictionary containing budget information
        """
        try:
            from facebook_business.adobjects.adset import AdSet

            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get adset object
            adset = await get_ad_object(ad_account_id, adset_id)

            # Fetch budget fields
            fields = [
                AdSet.Field.id,
                AdSet.Field.name,
                AdSet.Field.daily_budget,
                AdSet.Field.lifetime_budget,
                AdSet.Field.budget_remaining,
            ]

            adset_data = adset.api_get(fields=fields)

            return {
                "adset_id": adset_data.get(AdSet.Field.id),
                "name": adset_data.get(AdSet.Field.name),
                "daily_budget": adset_data.get(AdSet.Field.daily_budget),
                "lifetime_budget": adset_data.get(AdSet.Field.lifetime_budget),
                "budget_remaining": adset_data.get(AdSet.Field.budget_remaining),
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to get adset budget: {str(e)}")

    @staticmethod
    async def get_account_activities(
        ad_account_id: str,
        object_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get account activities (operation logs)

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            object_id: Optional filter by specific object ID (ad, adset, campaign)
            limit: Maximum number of activities to retrieve

        Returns:
            Dictionary containing activities list
        """
        try:
            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get account object
            account = await get_ad_object(ad_account_id, ad_account_id)

            # Get activities
            activities = account.get_activities(
                fields=[
                    'event_time',
                    'actor_name',
                    'event_type',
                    'object_type',
                    'object_id',
                    'object_name',
                    'extra_data'
                ],
                params={'limit': limit}
            )

            activities_list = list(activities)

            # Filter by object_id if specified
            if object_id:
                activities_list = [a for a in activities_list if a.get('object_id') == object_id]

            return {
                "total_activities": len(activities_list),
                "activities": activities_list
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to get activities: {str(e)}")

    @staticmethod
    async def update_adset_budget(
        ad_account_id: str,
        adset_id: str,
        daily_budget: Optional[int] = None,
        lifetime_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update AdSet budget (budget is set at AdSet level, not Ad level)
        Note: Budget values are in cents (e.g., 10000 = $100.00)

        Args:
            ad_account_id: Ad account ID (with or without act_ prefix)
            adset_id: AdSet ID
            daily_budget: Daily budget in cents (optional)
            lifetime_budget: Lifetime budget in cents (optional)

        Returns:
            Dictionary with operation result
        """
        try:
            from facebook_business.adobjects.adset import AdSet

            if not daily_budget and not lifetime_budget:
                raise ValueError("Must specify either daily_budget or lifetime_budget")

            # Normalize account ID
            ad_account_id = normalize_account_id(ad_account_id)

            # Get adset object
            adset = await get_ad_object(ad_account_id, adset_id)

            # Prepare update params
            params = {}
            if daily_budget is not None:
                params[AdSet.Field.daily_budget] = daily_budget
            if lifetime_budget is not None:
                params[AdSet.Field.lifetime_budget] = lifetime_budget

            # Update budget
            adset.api_update(params=params)

            # Verify the change
            updated_adset = await AdControlService.get_adset_budget(
                ad_account_id, adset_id
            )

            return {
                "success": True,
                "message": "AdSet budget updated successfully",
                "adset_budget": updated_adset,
            }

        except FacebookRequestError as e:
            raise ValueError(f"Facebook API error: {e.api_error_message()}")
        except Exception as e:
            raise ValueError(f"Failed to update adset budget: {str(e)}")
