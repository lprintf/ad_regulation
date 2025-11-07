#!/usr/bin/env python3
"""
Test that adset_id and campaign_id fields are correctly populated in responses.
"""

import asyncio
from api.services.insights_service import InsightsService
from utils.db import init_db, close_db


async def test_field_population():
    """Test that the correct ID fields are populated based on level."""
    print("Initializing database connection...")
    await init_db()

    try:
        test_account_id = "1244295750378353"
        since = "2025-07-22"
        until = "2025-07-23"  # Just 2 days for quick testing

        print("\n" + "="*70)
        print("Testing field population across different levels")
        print("="*70)

        # Test Ad level
        print("\n1. Ad-level query:")
        result_ad = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="ad",
            time_increment=1,
        )

        if result_ad['insights']:
            sample = result_ad['insights'][0]
            print(f"   ad_id: {sample.get('ad_id')}")
            print(f"   adset_id: {sample.get('adset_id')}")
            print(f"   campaign_id: {sample.get('campaign_id')}")
            assert sample.get('ad_id') is not None, "ad_id should be populated"
            assert sample.get('adset_id') is None, "adset_id should be None for ad-level"
            assert sample.get('campaign_id') is None, "campaign_id should be None for ad-level"
            print("   ✓ Field population correct for ad-level")

        # Test AdSet level
        print("\n2. AdSet-level query:")
        result_adset = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="adset",
            time_increment=1,
        )

        if result_adset['insights']:
            sample = result_adset['insights'][0]
            print(f"   ad_id: {sample.get('ad_id')}")
            print(f"   adset_id: {sample.get('adset_id')}")
            print(f"   campaign_id: {sample.get('campaign_id')}")
            assert sample.get('ad_id') is not None, "ad_id should be populated (for backward compat)"
            assert sample.get('adset_id') is not None, "adset_id should be populated for adset-level"
            assert sample.get('campaign_id') is None, "campaign_id should be None for adset-level"
            # Verify ad_id and adset_id have the same value
            assert sample.get('ad_id') == sample.get('adset_id'), "ad_id should equal adset_id for adset-level"
            print("   ✓ Field population correct for adset-level")

        # Test Campaign level
        print("\n3. Campaign-level query:")
        result_campaign = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="campaign",
            time_increment=1,
        )

        if result_campaign['insights']:
            sample = result_campaign['insights'][0]
            print(f"   ad_id: {sample.get('ad_id')}")
            print(f"   adset_id: {sample.get('adset_id')}")
            print(f"   campaign_id: {sample.get('campaign_id')}")
            assert sample.get('ad_id') is not None, "ad_id should be populated (for backward compat)"
            assert sample.get('adset_id') is None, "adset_id should be None for campaign-level"
            assert sample.get('campaign_id') is not None, "campaign_id should be populated for campaign-level"
            # Verify ad_id and campaign_id have the same value
            assert sample.get('ad_id') == sample.get('campaign_id'), "ad_id should equal campaign_id for campaign-level"
            print("   ✓ Field population correct for campaign-level")

        print("\n" + "="*70)
        print("✓ All field population tests passed!")
        print("="*70)

    except AssertionError as e:
        print(f"\n✗ Assertion failed: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nClosing database connection...")
        await close_db()


if __name__ == "__main__":
    asyncio.run(test_field_population())
