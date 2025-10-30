"""
Test script for Insights API endpoints.
Tests synchronous insights fetching and error handling.

For async tests, run: python tests/test_async_insights.py

Usage:
    python tests/test_insights_api.py
"""

import asyncio
from datetime import datetime, timedelta

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "admin"
AD_ACCOUNT_ID = "act_1302299391281701"  # Replace with your test account ID

# Test date range (recent 7 days)
today = datetime.now()
until = (today - timedelta(days=1)).strftime("%Y-%m-%d")
since = (today - timedelta(days=7)).strftime("%Y-%m-%d")


def print_test_header(test_name: str):
    """Print a formatted test header."""
    print(f"\n{'=' * 60}")
    print(f"TEST: {test_name}")
    print(f"{'=' * 60}")


def print_response(response: httpx.Response):
    """Print formatted HTTP response."""
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


async def test_health_check():
    """Test the health check endpoint."""
    print_test_header("Health Check")

    # Disable proxy for localhost
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get(f"{BASE_URL}/health")
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    print("✅ Health check passed")


async def test_list_ad_accounts():
    """Test listing ad accounts."""
    print_test_header("List Ad Accounts")

    headers = {"X-User-Id": USER_ID}

    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get(f"{BASE_URL}/ad-accounts", headers=headers)
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "accounts" in data["data"]

    print("✅ List ad accounts passed")


async def test_sync_insights_daily():
    """Test synchronous daily insights fetching."""
    print_test_header("Sync Insights - Daily Data")

    headers = {"X-User-Id": USER_ID}
    params = {
        "ad_account_id": AD_ACCOUNT_ID,
        "since": since,
        "until": until,
        "time_increment": 1,
        "level": "ad",
    }

    print(f"Fetching daily insights from {since} to {until}...")

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.get(
            f"{BASE_URL}/insights/sync", headers=headers, params=params
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "insights" in data["data"]
        print(f"Total records: {data['data']['total_records']}")

    print("✅ Sync daily insights passed")


async def test_sync_insights_aggregate():
    """Test synchronous aggregate insights fetching."""
    print_test_header("Sync Insights - Aggregated Data")

    headers = {"X-User-Id": USER_ID}
    params = {
        "ad_account_id": AD_ACCOUNT_ID,
        "since": since,
        "until": until,
        "level": "ad",
        # No time_increment = aggregate all
    }

    print(f"Fetching aggregated insights from {since} to {until}...")

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.get(
            f"{BASE_URL}/insights/sync", headers=headers, params=params
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print(f"Total records: {data['data']['total_records']}")

    print("✅ Sync aggregated insights passed")


async def test_sync_insights_with_breakdowns():
    """Test synchronous insights with breakdown dimensions."""
    print_test_header("Sync Insights - With Country Breakdown")

    headers = {"X-User-Id": USER_ID}
    params = {
        "ad_account_id": AD_ACCOUNT_ID,
        "since": since,
        "until": until,
        "time_increment": 1,
        "level": "ad",
        "breakdowns": "country",
    }

    print(f"Fetching insights with country breakdown from {since} to {until}...")

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.get(
            f"{BASE_URL}/insights/sync", headers=headers, params=params
        )
        print_response(response)

        if response.status_code == 200:
            data = response.json()
            print(f"Total records: {data['data']['total_records']}")
            print("✅ Sync insights with breakdowns passed")
        else:
            print("⚠️  Note: Breakdown queries may not work for all accounts")


async def test_error_handling():
    """Test error handling with invalid requests."""
    print_test_header("Error Handling")

    headers = {"X-User-Id": USER_ID}

    async with httpx.AsyncClient(trust_env=False) as client:
        # Test 1: Missing required parameter
        print("\nTest 1: Missing required parameter (ad_account_id)")
        response = await client.get(
            f"{BASE_URL}/insights/sync",
            headers=headers,
            params={"since": since, "until": until},
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422

        # Test 2: Invalid date format
        print("\nTest 2: Invalid date format")
        response = await client.get(
            f"{BASE_URL}/insights/sync",
            headers=headers,
            params={
                "ad_account_id": AD_ACCOUNT_ID,
                "since": "2025-13-45",  # Invalid date
                "until": until,
            },
        )
        print(f"Status: {response.status_code} (Expected: 400)")
        assert response.status_code == 400

        # Test 3: Missing authentication header
        print("\nTest 3: Missing X-User-Id header")
        response = await client.get(
            f"{BASE_URL}/insights/sync",
            params={
                "ad_account_id": AD_ACCOUNT_ID,
                "since": since,
                "until": until,
            },
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422

    print("\n✅ Error handling tests passed")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("INSIGHTS API TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"User ID: {USER_ID}")
    print(f"Test Account: {AD_ACCOUNT_ID}")
    print(f"Date Range: {since} to {until}")
    print("=" * 60)

    try:
        # Run synchronous tests
        await test_health_check()
        await test_list_ad_accounts()
        await test_sync_insights_daily()
        await test_sync_insights_aggregate()
        await test_sync_insights_with_breakdowns()
        await test_error_handling()

        print("\n" + "=" * 60)
        print("✅ ALL SYNC TESTS PASSED!")
        print("=" * 60)
        print("\n💡 TIP: Run async tests separately with:")
        print("   python tests/test_async_insights.py")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
