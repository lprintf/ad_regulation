"""
Test script for Account Activities API using HTTP requests
Tests the FastAPI endpoints for fetching historical modification records
"""

import json

import requests

# API Configuration
BASE_URL = "http://127.0.0.1:8000"  # Use 127.0.0.1 instead of localhost
USER_ID = "admin"  # Mock user ID for testing

# Test parameters
AD_ACCOUNT_ID = "1279567647104057"
AD_ID = "120234815168290189"

# Disable proxy for localhost connections
PROXIES = {
    "http": None,
    "https": None,
}


def test_get_all_activities():
    """Test 1: Get all account activities"""
    print("=" * 80)
    print("Test 1: Get All Account Activities (last 100)")
    print("=" * 80)

    url = f"{BASE_URL}/ad-control/activities"
    params = {"ad_account_id": AD_ACCOUNT_ID, "limit": 100}
    headers = {"X-User-Id": USER_ID}

    response = requests.get(url, params=params, headers=headers, proxies=PROXIES)

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            activities_data = data.get("data", {})
            total = activities_data.get("total_activities", 0)
            activities = activities_data.get("activities", [])

            print("✓ Success!")
            print(f"Total Activities: {total}")
            print()

            if activities:
                print("First 5 Activities:")
                print("-" * 80)
                for i, activity in enumerate(activities[:5], 1):
                    print(f"\n{i}. Activity:")
                    print(f"   Event Time: {activity.get('event_time', 'N/A')}")
                    print(f"   Actor: {activity.get('actor_name', 'N/A')}")
                    print(f"   Event Type: {activity.get('event_type', 'N/A')}")
                    print(f"   Object Type: {activity.get('object_type', 'N/A')}")
                    print(f"   Object ID: {activity.get('object_id', 'N/A')}")
                    print(f"   Object Name: {activity.get('object_name', 'N/A')}")
                    if activity.get("extra_data"):
                        print(f"   Extra Data: {activity.get('extra_data')}")
            else:
                print("No activities found")
        else:
            print(f"❌ API returned error: {data.get('error')}")
    else:
        print(f"❌ Request failed: {response.text}")

    print()


def test_get_filtered_activities():
    """Test 2: Get activities filtered by specific ad ID"""
    print("=" * 80)
    print(f"Test 2: Get Activities Filtered by Ad ID: {AD_ID}")
    print("=" * 80)

    url = f"{BASE_URL}/ad-control/activities"
    params = {"ad_account_id": AD_ACCOUNT_ID, "object_id": AD_ID, "limit": 50}
    headers = {"X-User-Id": USER_ID}

    response = requests.get(url, params=params, headers=headers, proxies=PROXIES)

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            activities_data = data.get("data", {})
            total = activities_data.get("total_activities", 0)
            activities = activities_data.get("activities", [])

            print("✓ Success!")
            print(f"Total Activities for Ad {AD_ID}: {total}")
            print()

            if activities:
                print("Activities for this specific ad:")
                print("-" * 80)
                for i, activity in enumerate(activities, 1):
                    print(f"\n{i}. Activity:")
                    print(f"   Event Time: {activity.get('event_time', 'N/A')}")
                    print(f"   Actor: {activity.get('actor_name', 'N/A')}")
                    print(f"   Event Type: {activity.get('event_type', 'N/A')}")
                    print(f"   Object Name: {activity.get('object_name', 'N/A')}")
                    if activity.get("extra_data"):
                        print(
                            f"   Extra Data: {json.dumps(activity.get('extra_data'), indent=2)}"
                        )
            else:
                print(f"No activities found for ad {AD_ID}")
        else:
            print(f"❌ API returned error: {data.get('error')}")
    else:
        print(f"❌ Request failed: {response.text}")

    print()


def test_get_recent_activities():
    """Test 3: Get recent activities (last 10)"""
    print("=" * 80)
    print("Test 3: Get Recent Activities (last 10)")
    print("=" * 80)

    url = f"{BASE_URL}/ad-control/activities"
    params = {"ad_account_id": AD_ACCOUNT_ID, "limit": 10}
    headers = {"X-User-Id": USER_ID}

    response = requests.get(url, params=params, headers=headers, proxies=PROXIES)

    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            activities_data = data.get("data", {})
            total = activities_data.get("total_activities", 0)
            activities = activities_data.get("activities", [])

            print("✓ Success!")
            print(f"Total Recent Activities: {total}")
            print()

            if activities:
                print("Recent Activities Summary:")
                print("-" * 80)
                for i, activity in enumerate(activities, 1):
                    print(
                        f"{i}. [{activity.get('event_time', 'N/A')}] "
                        f"{activity.get('event_type', 'N/A')} on "
                        f"{activity.get('object_type', 'N/A')} "
                        f"'{activity.get('object_name', 'N/A')}' "
                        f"by {activity.get('actor_name', 'N/A')}"
                    )
            else:
                print("No recent activities found")
        else:
            print(f"❌ API returned error: {data.get('error')}")
    else:
        print(f"❌ Request failed: {response.text}")

    print()


def test_curl_examples():
    """Print curl command examples for manual testing"""
    print("=" * 80)
    print("cURL Examples for Manual Testing")
    print("=" * 80)
    print()

    print("1. Get all activities:")
    print(
        f'curl -X GET "{BASE_URL}/ad-control/activities?ad_account_id={AD_ACCOUNT_ID}&limit=100" \\'
    )
    print(f'  -H "X-User-Id: {USER_ID}"')
    print()

    print("2. Get activities for specific ad:")
    print(
        f'curl -X GET "{BASE_URL}/ad-control/activities?ad_account_id={AD_ACCOUNT_ID}&object_id={AD_ID}&limit=50" \\'
    )
    print(f'  -H "X-User-Id: {USER_ID}"')
    print()

    print("3. Get recent activities:")
    print(
        f'curl -X GET "{BASE_URL}/ad-control/activities?ad_account_id={AD_ACCOUNT_ID}&limit=10" \\'
    )
    print(f'  -H "X-User-Id: {USER_ID}"')
    print()


if __name__ == "__main__":
    print("\n")
    print("=" * 80)
    print("Account Activities API Test Suite")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Ad Account ID: {AD_ACCOUNT_ID}")
    print(f"User ID: {USER_ID}")
    print()

    try:
        # Run tests
        test_get_all_activities()
        test_get_filtered_activities()
        test_get_recent_activities()

        # Print curl examples
        test_curl_examples()

        print("=" * 80)
        print("✓ All tests completed!")
        print("=" * 80)

    except requests.exceptions.ConnectionError:
        print("\n❌ Connection Error: Could not connect to the API server.")
        print("Please make sure the API server is running:")
        print("  python run_api.py")
        print("  or")
        print("  uvicorn api.app:app --reload")
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback

        traceback.print_exc()
