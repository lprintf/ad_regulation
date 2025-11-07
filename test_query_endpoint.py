#!/usr/bin/env python3
"""
Test script for the new /insights/query endpoint.
This script tests the database-only query functionality.
"""

import asyncio
from datetime import datetime, timedelta
from api.services.insights_service import InsightsService
from utils.db import init_db, close_db


async def test_query_insights():
    """Test the query_insights_from_db method."""
    print("Initializing database connection...")
    await init_db()

    try:
        # Test parameters - using account ID from database (without act_ prefix is OK)
        # The service will handle normalization
        test_account_id = "1244295750378353"  # Real account ID from database

        # Use a date range that should have data (based on actual DB data: 2025-07-22 to 2025-10-16)
        since = "2025-07-22"
        until = "2025-08-31"

        print(f"\nTesting query_insights_from_db...")
        print(f"  Account: {test_account_id}")
        print(f"  Date range: {since} to {until}")
        print(f"  Level: ad")
        print(f"  Time increment: 1 (daily)")

        # Call the new method
        result = await InsightsService.query_insights_from_db(
            ad_account_id=test_account_id,
            since=since,
            until=until,
            level="ad",
            time_increment=1,
            breakdowns=None,
        )

        print(f"\n✓ Success!")
        print(f"  Total records: {result['total_records']}")
        print(f"  Date range: {result['date_range']['since']} to {result['date_range']['until']}")

        if result['insights']:
            print(f"\n  Sample records (first 3):")
            for i, sample in enumerate(result['insights'][:3], 1):
                print(f"\n  Record {i}:")
                print(f"    Ad ID: {sample['ad_id']}")
                print(f"    Date: {sample['date']}")
                print(f"    Spend: ${sample['metrics']['spend']:.2f}")
                print(f"    Impressions: {sample['metrics']['impressions']}")
                print(f"    Clicks: {sample['metrics']['clicks']}")
        else:
            print(f"\n  No records found in database for this date range.")
            print(f"  Try a different date range or account ID.")

        # Test with act_ prefix
        print(f"\n\nTesting with act_ prefix...")
        print(f"  Account: act_{test_account_id}")
        result2 = await InsightsService.query_insights_from_db(
            ad_account_id=f"act_{test_account_id}",
            since=since,
            until=until,
            level="ad",
            time_increment=1,
            breakdowns=None,
        )
        print(f"  Total records: {result2['total_records']}")
        print(f"  ✓ Works with both formats!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nClosing database connection...")
        await close_db()


if __name__ == "__main__":
    asyncio.run(test_query_insights())
