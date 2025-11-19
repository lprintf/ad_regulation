"""
Test ad control using HTTP API calls
"""
import requests
import time

# API configuration
BASE_URL = "http://localhost:8000"
USER_ID = "test_user"
HEADERS = {
    "X-User-Id": USER_ID,
    "Content-Type": "application/json"
}

# Test parameters
AD_ACCOUNT_ID = "1279567647104057"
AD_ID = "120234815168290189"


def test_api():
    """Test ad control operations via HTTP API"""

    print("=" * 60)
    print("Testing Ad Control API with HTTP Requests")
    print("=" * 60)

    # Test 1: Get Ad Status
    print("\n1. Getting ad status...")
    response = requests.get(
        f"{BASE_URL}/ad-control/status",
        params={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID
        },
        headers=HEADERS
    )
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        ad_status = data["data"]
        print(f"   ✓ Ad ID: {ad_status['ad_id']}")
        print(f"   ✓ Name: {ad_status['name']}")
        print(f"   ✓ Status: {ad_status['configured_status']}")
        original_status = ad_status['configured_status']
    else:
        print(f"   ❌ Error: {response.text}")
        return

    # Test 2: Start Ad
    print("\n2. Starting (activating) ad...")
    response = requests.post(
        f"{BASE_URL}/ad-control/start",
        json={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID
        },
        headers=HEADERS
    )
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Message: {data['message']}")
        print(f"   ✓ New Status: {data['data']['ad_status']['configured_status']}")
    else:
        print(f"   ❌ Error: {response.text}")

    # Wait a moment
    print("\n   Waiting 3 seconds...")
    time.sleep(3)

    # Verify on Facebook
    print("\n3. Verifying status on Facebook...")
    response = requests.get(
        f"{BASE_URL}/ad-control/status",
        params={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID
        },
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        current_status = data["data"]["configured_status"]
        print(f"   Current Status on Facebook: {current_status}")

        if current_status == "ACTIVE":
            print("   ✅ SUCCESS! Ad is now ACTIVE on Facebook")
        else:
            print(f"   ❌ FAILED! Ad is still {current_status}")
    else:
        print(f"   ❌ Error: {response.text}")

    # Test 3: Stop Ad
    print("\n4. Stopping (pausing) ad...")
    response = requests.post(
        f"{BASE_URL}/ad-control/stop",
        json={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID
        },
        headers=HEADERS
    )
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ Message: {data['message']}")
        print(f"   ✓ New Status: {data['data']['ad_status']['configured_status']}")
    else:
        print(f"   ❌ Error: {response.text}")

    # Wait and verify
    print("\n   Waiting 3 seconds...")
    time.sleep(3)

    print("\n5. Final verification...")
    response = requests.get(
        f"{BASE_URL}/ad-control/status",
        params={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID
        },
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()
        final_status = data["data"]["configured_status"]
        print(f"   Final Status on Facebook: {final_status}")

        if final_status == "PAUSED":
            print("   ✅ SUCCESS! Ad is now PAUSED on Facebook")
        else:
            print(f"   ⚠️  Ad is {final_status}")
    else:
        print(f"   ❌ Error: {response.text}")

    # Test 4: Update Ad Name
    print("\n6. Testing name update...")
    new_name = "Ad global_engagement_$1 [API TEST]"
    response = requests.post(
        f"{BASE_URL}/ad-control/update-name",
        json={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID,
            "new_name": new_name
        },
        headers=HEADERS
    )
    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✓ New Name: {data['data']['ad_status']['name']}")
    else:
        print(f"   ❌ Error: {response.text}")

    # Restore original name
    time.sleep(2)
    print("\n7. Restoring original name...")
    response = requests.post(
        f"{BASE_URL}/ad-control/update-name",
        json={
            "ad_account_id": AD_ACCOUNT_ID,
            "ad_id": AD_ID,
            "new_name": "Ad global_engagement_$1"
        },
        headers=HEADERS
    )
    if response.status_code == 200:
        print("   ✓ Name restored")

    print("\n" + "=" * 60)
    print("✓ Test completed!")
    print("=" * 60)
    print("\n请到Facebook广告管理后台查看操作记录！")


if __name__ == "__main__":
    # Check if API is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✓ API server is running\n")
            test_api()
        else:
            print("❌ API server responded with error")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server at", BASE_URL)
        print("Please start the API server first:")
        print("  python run_api.py")
    except Exception as e:
        print(f"❌ Error: {e}")
