"""
Test script for Account Activities API
Tests fetching historical modification records for ad accounts
"""
import asyncio
from utils.db import init_db, close_db
from api.services.ad_control_service import AdControlService


async def test_activities():
    """Test account activities fetching"""

    # Initialize database
    await init_db()
    print("✓ Database initialized\n")

    # Test parameters
    ad_account_id = "1279567647104057"  # Will be converted to act_1279567647104057
    ad_id = "120234815168290189"  # Example ad ID for filtering

    try:
        # Test 1: Get All Account Activities
        print("=" * 80)
        print("Test 1: Get All Account Activities (last 100)")
        print("=" * 80)
        activities = await AdControlService.get_account_activities(
            ad_account_id=ad_account_id,
            limit=100
        )
        print(f"Total Activities: {activities['total_activities']}")
        print()

        # Display first 5 activities
        if activities['activities']:
            print("First 5 Activities:")
            print("-" * 80)
            for i, activity in enumerate(activities['activities'][:5], 1):
                print(f"\n{i}. Activity:")
                print(f"   Event Time: {activity.get('event_time', 'N/A')}")
                print(f"   Actor: {activity.get('actor_name', 'N/A')}")
                print(f"   Event Type: {activity.get('event_type', 'N/A')}")
                print(f"   Object Type: {activity.get('object_type', 'N/A')}")
                print(f"   Object ID: {activity.get('object_id', 'N/A')}")
                print(f"   Object Name: {activity.get('object_name', 'N/A')}")
                if activity.get('extra_data'):
                    print(f"   Extra Data: {activity.get('extra_data')}")
        else:
            print("No activities found for this account")
        print()

        # Test 2: Get Activities Filtered by Specific Ad ID
        print("=" * 80)
        print(f"Test 2: Get Activities Filtered by Ad ID: {ad_id}")
        print("=" * 80)
        filtered_activities = await AdControlService.get_account_activities(
            ad_account_id=ad_account_id,
            object_id=ad_id,
            limit=50
        )
        print(f"Total Activities for Ad {ad_id}: {filtered_activities['total_activities']}")
        print()

        if filtered_activities['activities']:
            print("Activities for this specific ad:")
            print("-" * 80)
            for i, activity in enumerate(filtered_activities['activities'], 1):
                print(f"\n{i}. Activity:")
                print(f"   Event Time: {activity.get('event_time', 'N/A')}")
                print(f"   Actor: {activity.get('actor_name', 'N/A')}")
                print(f"   Event Type: {activity.get('event_type', 'N/A')}")
                print(f"   Object Name: {activity.get('object_name', 'N/A')}")
                if activity.get('extra_data'):
                    print(f"   Extra Data: {activity.get('extra_data')}")
        else:
            print(f"No activities found for ad {ad_id}")
        print()

        # Test 3: Get Recent Activities (last 10)
        print("=" * 80)
        print("Test 3: Get Recent Activities (last 10)")
        print("=" * 80)
        recent_activities = await AdControlService.get_account_activities(
            ad_account_id=ad_account_id,
            limit=10
        )
        print(f"Total Recent Activities: {recent_activities['total_activities']}")
        print()

        if recent_activities['activities']:
            print("Recent Activities Summary:")
            print("-" * 80)
            for i, activity in enumerate(recent_activities['activities'], 1):
                print(f"{i}. [{activity.get('event_time', 'N/A')}] "
                      f"{activity.get('event_type', 'N/A')} on "
                      f"{activity.get('object_type', 'N/A')} "
                      f"'{activity.get('object_name', 'N/A')}' "
                      f"by {activity.get('actor_name', 'N/A')}")
        print()

        print("=" * 80)
        print("✓ All tests completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Close database
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(test_activities())
