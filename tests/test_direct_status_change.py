"""
Direct test to change ad status and verify it works on Facebook
"""
import asyncio
from facebook_business.adobjects.ad import Ad
from utils.db import init_db, close_db
from utils.fb_api_flyweight_factory import get_ad_object


async def test_status_change():
    """Test changing ad status directly"""

    # Initialize database
    await init_db()
    print("✓ Database initialized\n")

    # Test parameters
    ad_account_id = "act_1279567647104057"
    ad_id = "120234815168290189"

    try:
        print("=" * 60)
        print("Direct Status Change Test")
        print("=" * 60)

        # Get ad object
        ad = await get_ad_object(ad_account_id, ad_id)

        # Step 1: Get current status
        print("\n1. Getting current status...")
        ad_data = ad.api_get(fields=[Ad.Field.id, Ad.Field.name, Ad.Field.status])
        current_status = ad_data.get(Ad.Field.status, 'UNKNOWN')
        print(f"   Current status: {current_status}")
        print(f"   Ad name: {ad_data.get(Ad.Field.name)}")

        # Step 2: Try to change status
        if current_status == 'PAUSED':
            new_status = Ad.Status.active
            print(f"\n2. Attempting to ACTIVATE ad...")
        else:
            new_status = Ad.Status.paused
            print(f"\n2. Attempting to PAUSE ad...")

        print(f"   Calling api_update with status={new_status}")

        # Try the update
        result = ad.api_update(params={
            Ad.Field.status: new_status
        })

        print(f"   API Update result: {result}")

        # Step 3: Wait a moment and check again
        print("\n3. Waiting 2 seconds...")
        await asyncio.sleep(2)

        # Step 4: Verify the change
        print("\n4. Verifying status change...")
        ad_refreshed = await get_ad_object(ad_account_id, ad_id)
        ad_data_new = ad_refreshed.api_get(fields=[Ad.Field.id, Ad.Field.status])
        final_status = ad_data_new.get(Ad.Field.status, 'UNKNOWN')

        print(f"   New status: {final_status}")

        if final_status != current_status:
            print(f"\n✅ SUCCESS! Status changed from {current_status} to {final_status}")
        else:
            print(f"\n❌ FAILED! Status remains {current_status}")
            print("\nDebug info:")
            print(f"  - Attempted to set: {new_status}")
            print(f"  - API update returned: {result}")
            print(f"  - Current status: {final_status}")

        # Step 5: Restore original status
        if final_status != current_status:
            print(f"\n5. Restoring original status to {current_status}...")
            ad.api_update(params={
                Ad.Field.status: current_status
            })
            await asyncio.sleep(1)
            print("   Status restored")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Close database
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(test_status_change())
