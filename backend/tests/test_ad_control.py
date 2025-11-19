"""
Test script for Ad Control Service
Tests basic ad operations with the provided ad account and ad ID
"""
import asyncio
from utils.db import init_db, close_db
from api.services.ad_control_service import AdControlService


async def test_ad_control():
    """Test ad control operations"""

    # Initialize database
    await init_db()
    print("✓ Database initialized\n")

    # Test parameters
    ad_account_id = "1279567647104057"  # Will be converted to act_1279567647104057
    ad_id = "120234815168290189"

    try:
        # Test 1: Get Ad Status
        print("=" * 60)
        print("Test 1: Get Ad Status")
        print("=" * 60)
        status = await AdControlService.get_ad_status(ad_account_id, ad_id)
        print(f"Ad ID: {status['ad_id']}")
        print(f"Name: {status['name']}")
        print(f"Configured Status: {status['configured_status']}")
        print(f"Effective Status: {status['effective_status']}")
        print(f"Campaign ID: {status['campaign_id']}")
        print(f"AdSet ID: {status['adset_id']}")
        print(f"Created Time: {status.get('created_time', 'N/A')}")
        print(f"Updated Time: {status.get('updated_time', 'N/A')}")
        print()

        # Store original status
        original_status = status['configured_status']
        adset_id = status['adset_id']

        # Test 2: Get AdSet Budget
        print("=" * 60)
        print("Test 2: Get AdSet Budget")
        print("=" * 60)
        budget_info = await AdControlService.get_adset_budget(ad_account_id, adset_id)
        print(f"AdSet ID: {budget_info['adset_id']}")
        print(f"AdSet Name: {budget_info['name']}")
        print(f"Daily Budget: {budget_info.get('daily_budget', 'N/A')} cents")
        print(f"Lifetime Budget: {budget_info.get('lifetime_budget', 'N/A')} cents")
        print(f"Budget Remaining: {budget_info.get('budget_remaining', 'N/A')} cents")
        print()

        # Test 3: Stop Ad (if currently active)
        if original_status == 'ACTIVE':
            print("=" * 60)
            print("Test 3: Stop Ad (Pause)")
            print("=" * 60)
            result = await AdControlService.stop_ad(ad_account_id, ad_id)
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            print(f"New Status: {result['ad_status']['configured_status']}")
            print()

            # Wait a moment
            await asyncio.sleep(2)

            # Test 4: Start Ad
            print("=" * 60)
            print("Test 4: Start Ad (Activate)")
            print("=" * 60)
            result = await AdControlService.start_ad(ad_account_id, ad_id)
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            print(f"New Status: {result['ad_status']['configured_status']}")
            print()
        else:
            print("=" * 60)
            print("Test 3: Start Ad (Activate)")
            print("=" * 60)
            result = await AdControlService.start_ad(ad_account_id, ad_id)
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            print(f"New Status: {result['ad_status']['configured_status']}")
            print()

            # Wait a moment
            await asyncio.sleep(2)

            # Test 4: Stop Ad
            print("=" * 60)
            print("Test 4: Stop Ad (Pause)")
            print("=" * 60)
            result = await AdControlService.stop_ad(ad_account_id, ad_id)
            print(f"Success: {result['success']}")
            print(f"Message: {result['message']}")
            print(f"New Status: {result['ad_status']['configured_status']}")
            print()

        # Test 5: Update Ad Name
        print("=" * 60)
        print("Test 5: Update Ad Name")
        print("=" * 60)
        original_name = status['name']
        new_name = f"{original_name} [TEST]"
        print(f"Original Name: {original_name}")
        print(f"New Name: {new_name}")
        result = await AdControlService.update_ad_name(ad_account_id, ad_id, new_name)
        print(f"Success: {result['success']}")
        print(f"Message: {result['message']}")
        print(f"Updated Name: {result['ad_status']['name']}")
        print()

        # Wait a moment
        await asyncio.sleep(2)

        # Restore original name
        print("=" * 60)
        print("Test 6: Restore Original Name")
        print("=" * 60)
        result = await AdControlService.update_ad_name(ad_account_id, ad_id, original_name)
        print(f"Success: {result['success']}")
        print(f"Restored Name: {result['ad_status']['name']}")
        print()

        # Restore original status
        if original_status == 'ACTIVE':
            print("=" * 60)
            print("Restoring Original Ad Status (ACTIVE)")
            print("=" * 60)
            result = await AdControlService.start_ad(ad_account_id, ad_id)
            print(f"Status Restored: {result['ad_status']['configured_status']}")
        elif original_status == 'PAUSED':
            print("=" * 60)
            print("Restoring Original Ad Status (PAUSED)")
            print("=" * 60)
            result = await AdControlService.stop_ad(ad_account_id, ad_id)
            print(f"Status Restored: {result['ad_status']['configured_status']}")
        print()

        print("=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        # Close database
        await close_db()
        print("\n✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(test_ad_control())
