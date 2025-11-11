"""
Async Insights API test script.
Tests the asynchronous insights workflow: create job -> poll status -> get results.

Usage:
    python tests/test_async_insights.py [--auto]

Options:
    --auto  Run without confirmation prompt (useful for CI/CD)
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "admin"
AD_ACCOUNT_ID = "act_1302299391281701"  # Replace with your test account ID

# Test date range (last 30 days for async job)
today = datetime.now()
until = (today - timedelta(days=1)).strftime("%Y-%m-%d")
since = (today - timedelta(days=30)).strftime("%Y-%m-%d")


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"{title}")
    print(f"{'=' * 70}\n")


async def test_async_insights_workflow():
    """Test the full async insights workflow."""
    print_section("🔄 Async Insights Workflow Test")

    headers = {"X-User-Id": USER_ID, "Content-Type": "application/json"}

    payload = {
        "ad_account_id": AD_ACCOUNT_ID,
        "since": since,
        "until": until,
        "level": "ad",
        "time_increment": 1,
    }

    print(f"📅 Date Range: {since} to {until}")
    print(f"📊 Account: {AD_ACCOUNT_ID}\n")

    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        # Step 1: Create async job
        print_section("1️⃣  Creating Async Job")
        print(f"Request payload:\n{payload}\n")

        try:
            response = await client.post(
                f"{BASE_URL}/insights/jobs", headers=headers, json=payload
            )

            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}\n")

            if response.status_code != 200:
                print("❌ Failed to create async job")
                return False

            data = response.json()
            if not data.get("success"):
                print("❌ Job creation failed")
                return False

            job_id = data["data"]["job_id"]
            print("✅ Job created successfully!")
            print(f"   Job ID: {job_id}")
            print(f"   Initial Status: {data['data']['status']}\n")

        except Exception as e:
            print(f"❌ Error creating job: {e}")
            return False

        # Step 2: Poll job status
        print_section("2️⃣  Polling Job Status")

        # Wait a bit for the job to be registered in Facebook's system
        print("⏱️  Waiting 15 seconds for job to be registered...")
        await asyncio.sleep(15)

        max_polls = 30  # Maximum 30 polls
        poll_interval = 10  # Poll every 10 seconds (reduced frequency)
        job_completed = False

        for i in range(max_polls):
            try:
                status_response = await client.get(
                    f"{BASE_URL}/insights/jobs/{job_id}",
                    headers={"X-User-Id": USER_ID},
                    params={"ad_account_id": AD_ACCOUNT_ID},
                )

                if status_response.status_code == 404:
                    # Job not found yet, might still be registering
                    if i < 3:  # Retry for first 3 attempts
                        print(f"⏳ Job not found yet (attempt {i+1}/3), waiting...")
                        await asyncio.sleep(10)
                        continue
                    else:
                        print(f"❌ Job {job_id} not found after retries")
                        return False
                elif status_response.status_code != 200:
                    print(
                        f"⚠️  Status check returned {status_response.status_code}, retrying..."
                    )
                    await asyncio.sleep(poll_interval)
                    continue

                status_data = status_response.json()
                job_status = status_data["data"]["status"]
                percent = status_data["data"]["percent_complete"]

                # Print progress
                progress_bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
                print(
                    f"Poll {i+1:2d}/{max_polls}: [{progress_bar}] {percent:3d}% - {job_status}"
                )

                # Check if completed
                if job_status == "Job Completed":
                    print(f"\n✅ Job completed successfully after {i+1} polls!")
                    job_completed = True
                    break
                elif job_status in ["Job Failed", "Job Skipped"]:
                    print(f"\n❌ Job failed with status: {job_status}")
                    return False

                # Wait before next poll
                if i < max_polls - 1:
                    await asyncio.sleep(poll_interval)

            except Exception as e:
                print(f"⚠️  Error checking status: {e}")
                await asyncio.sleep(poll_interval)

        if not job_completed:
            print(
                f"\n⚠️  Job did not complete within {max_polls * poll_interval} seconds"
            )
            print("   This might be normal for very large date ranges.")
            return False

        # Step 3: Get job results
        print_section("3️⃣  Retrieving Job Results")

        try:
            result_response = await client.get(
                f"{BASE_URL}/insights/jobs/{job_id}/result",
                headers={"X-User-Id": USER_ID},
                params={"ad_account_id": AD_ACCOUNT_ID},
            )

            print(f"Status Code: {result_response.status_code}")

            if result_response.status_code != 200:
                print(f"❌ Failed to get results: {result_response.json()}")
                return False

            result_data = result_response.json()

            if result_data.get("success"):
                total_records = result_data["data"]["total_records"]
                date_range = result_data["data"]["date_range"]

                print("\n✅ Results retrieved successfully!")
                print(f"   Total Records: {total_records}")
                print(f"   Date Range: {date_range['since']} to {date_range['until']}")

                # Show sample data
                if total_records > 0:
                    print("\n📊 Sample Record (first insight):")
                    sample = result_data["data"]["insights"][0]
                    print(f"   Ad ID: {sample['ad_id']}")
                    print(f"   Date: {sample['date']}")
                    print(f"   Spend: ${sample['metrics']['spend']:.2f}")
                    print(f"   Impressions: {sample['metrics']['impressions']}")
                    print(f"   Clicks: {sample['metrics']['clicks']}")

                return True
            else:
                print("❌ Failed to retrieve results")
                return False

        except Exception as e:
            print(f"❌ Error retrieving results: {e}")
            return False


async def test_async_job_status_check():
    """Test checking status of a non-existent job."""
    print_section("🔍 Testing Non-Existent Job Status")

    headers = {"X-User-Id": USER_ID}
    fake_job_id = "999999999999999"

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/insights/jobs/{fake_job_id}",
                headers=headers,
                params={"ad_account_id": AD_ACCOUNT_ID},
            )

            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}\n")

            if response.status_code == 404:
                print("✅ Correctly returns 404 for non-existent job")
                return True
            else:
                print(f"⚠️  Expected 404, got {response.status_code}")
                return False

        except Exception as e:
            print(f"Error: {e}")
            return False


async def main():
    """Run all async tests."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Async Insights API Tests")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Run without confirmation prompt (useful for CI/CD)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🧪 ASYNC INSIGHTS API TEST SUITE")
    print("=" * 70)
    print(f"Base URL: {BASE_URL}")
    print(f"User ID: {USER_ID}")
    print(f"Test Account: {AD_ACCOUNT_ID}")
    print(f"Date Range: {since} to {until}")
    print("=" * 70)

    print("\n⚠️  NOTE: These tests may take 5-10 minutes to complete.")
    print("   Facebook async jobs need time to process.")
    print("   Polling every 10 seconds to avoid rate limits.\n")

    # Confirm before running (unless --auto flag is set)
    if not args.auto:
        try:
            confirm = input("Continue with async tests? [y/N]: ")
            if confirm.lower() != "y":
                print("\n❌ Tests cancelled")
                return
        except EOFError:
            print("\n❌ Cannot read input in non-interactive mode.")
            print("   Use --auto flag to run without confirmation:")
            print("   python tests/test_async_insights.py --auto")
            sys.exit(1)
    else:
        print("🤖 Running in auto mode (--auto flag set)\n")

    try:
        # Test 1: Full workflow
        result1 = await test_async_insights_workflow()

        # Test 2: Error handling
        result2 = await test_async_job_status_check()

        # Summary
        print_section("📋 Test Summary")
        print(f"Full Async Workflow: {'✅ PASSED' if result1 else '❌ FAILED'}")
        print(f"Error Handling: {'✅ PASSED' if result2 else '❌ FAILED'}")

        if result1 and result2:
            print("\n" + "=" * 70)
            print("✅ ALL ASYNC TESTS PASSED!")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("❌ SOME TESTS FAILED")
            print("=" * 70)

    except KeyboardInterrupt:
        print("\n\n❌ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
