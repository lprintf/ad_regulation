"""
Test script to check ad activities and verify operations
"""
import asyncio
from utils.db import init_db, close_db
from utils.fb_api_flyweight_factory import get_ad_object


async def check_activities():
    """Check ad activities to see if operations were recorded"""

    # Initialize database
    await init_db()
    print("✓ Database initialized\n")

    # Test parameters
    ad_account_id = "act_1279567647104057"
    ad_id = "120234815168290189"

    try:
        print("=" * 60)
        print("Checking Activities for Account:", ad_account_id)
        print("Filtering for Ad ID:", ad_id)
        print("=" * 60)

        # Get ad account object (activities are at account level, not ad level)
        account = await get_ad_object(ad_account_id, ad_account_id)

        # Get activities from account
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
            params={
                'limit': 1000
            }
        )

        activities_list = list(activities)

        if not activities_list:
            print("❌ No activities found for this account")
        else:
            # Filter activities related to our ad
            ad_activities = [a for a in activities_list if a.get('object_id') == ad_id]

            print(f"✓ Found {len(activities_list)} total activities")
            print(f"✓ Found {len(ad_activities)} activities for ad {ad_id}\n")

            if not ad_activities:
                print(f"❌ No activities found specifically for ad {ad_id}")
                print("\nShowing last 10 activities for context:")
                activities_to_show = activities_list[:10]
            else:
                print(f"Showing activities for ad {ad_id}:")
                activities_to_show = ad_activities[:20]

            for i, activity in enumerate(activities_to_show, 1):
                print(f"\nActivity #{i}:")
                print(f"  Time: {activity.get('event_time', 'N/A')}")
                print(f"  Actor: {activity.get('actor_name', 'N/A')}")
                print(f"  Event Type: {activity.get('event_type', 'N/A')}")
                print(f"  Object Type: {activity.get('object_type', 'N/A')}")
                print(f"  Object ID: {activity.get('object_id', 'N/A')}")
                print(f"  Object Name: {activity.get('object_name', 'N/A')}")
                extra_data = activity.get('extra_data', {})
                if extra_data:
                    print(f"  Extra Data: {extra_data}")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Close database
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(check_activities())
