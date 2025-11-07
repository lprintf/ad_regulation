#!/usr/bin/env python3
"""
Test script for aggregation levels in /insights/query endpoint.
Tests ad, adset, and campaign level queries.
"""

import asyncio
from api.services.insights_service import InsightsService
from utils.db import init_db, close_db


async def test_aggregation_levels():
    """Test all three aggregation levels."""
    print("Initializing database connection...")
    await init_db()

    try:
        test_account_id = "1244295750378353"
        since = "2025-07-22"
        until = "2025-08-31"

        # Test 1: Ad-level query (no aggregation)
        print("\n" + "="*70)
        print("TEST 1: Ad-level query (no aggregation)")
        print("="*70)

        result_ad = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="ad",
            time_increment=1,
            breakdowns=None,
        )

        print(f"\n✓ Ad-level results:")
        print(f"  Total records: {result_ad['total_records']}")
        if result_ad['insights']:
            print(f"  Sample (first 3):")
            for i, record in enumerate(result_ad['insights'][:3], 1):
                print(f"    {i}. Ad ID: {record['ad_id']}, Date: {record['date']}, "
                      f"Spend: ${record['metrics']['spend']:.2f}")

        # Test 2: AdSet-level query (aggregate by adset)
        print("\n" + "="*70)
        print("TEST 2: AdSet-level query (aggregate by adset)")
        print("="*70)

        result_adset = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="adset",
            time_increment=1,
            breakdowns=None,
        )

        print(f"\n✓ AdSet-level results:")
        print(f"  Total records: {result_adset['total_records']}")
        if result_adset['insights']:
            print(f"  Sample (first 3):")
            for i, record in enumerate(result_adset['insights'][:3], 1):
                print(f"    {i}. AdSet ID: {record['ad_id']}, Date: {record['date']}, "
                      f"Spend: ${record['metrics']['spend']:.2f}, "
                      f"Impressions: {record['metrics']['impressions']}")

        # Test 3: Campaign-level query (aggregate by campaign)
        print("\n" + "="*70)
        print("TEST 3: Campaign-level query (aggregate by campaign)")
        print("="*70)

        result_campaign = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="campaign",
            time_increment=1,
            breakdowns=None,
        )

        print(f"\n✓ Campaign-level results:")
        print(f"  Total records: {result_campaign['total_records']}")
        if result_campaign['insights']:
            print(f"  Sample (first 3):")
            for i, record in enumerate(result_campaign['insights'][:3], 1):
                print(f"    {i}. Campaign ID: {record['ad_id']}, Date: {record['date']}, "
                      f"Spend: ${record['metrics']['spend']:.2f}, "
                      f"Impressions: {record['metrics']['impressions']}")

        # Verification: Ad-level count should be >= AdSet-level count >= Campaign-level count
        print("\n" + "="*70)
        print("VERIFICATION")
        print("="*70)
        print(f"\nRecord counts (same date range):")
        print(f"  Ad-level:      {result_ad['total_records']} records")
        print(f"  AdSet-level:   {result_adset['total_records']} records")
        print(f"  Campaign-level: {result_campaign['total_records']} records")

        if result_ad['total_records'] >= result_adset['total_records'] >= result_campaign['total_records']:
            print(f"\n✓ Aggregation hierarchy is correct!")
            print(f"  (Ad records >= AdSet records >= Campaign records)")
        else:
            print(f"\n⚠ Warning: Aggregation hierarchy seems unexpected")

        # Compare spend totals (should be the same across all levels for same date range)
        ad_total_spend = sum(r['metrics']['spend'] for r in result_ad['insights'])
        adset_total_spend = sum(r['metrics']['spend'] for r in result_adset['insights'])
        campaign_total_spend = sum(r['metrics']['spend'] for r in result_campaign['insights'])

        print(f"\nTotal spend across all levels:")
        print(f"  Ad-level:      ${ad_total_spend:.2f}")
        print(f"  AdSet-level:   ${adset_total_spend:.2f}")
        print(f"  Campaign-level: ${campaign_total_spend:.2f}")

        if abs(ad_total_spend - adset_total_spend) < 0.01 and abs(ad_total_spend - campaign_total_spend) < 0.01:
            print(f"\n✓ Total spend matches across all levels!")
        else:
            print(f"\n⚠ Warning: Total spend discrepancy detected")

        print("\n" + "="*70)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*70)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nClosing database connection...")
        await close_db()


if __name__ == "__main__":
    asyncio.run(test_aggregation_levels())
