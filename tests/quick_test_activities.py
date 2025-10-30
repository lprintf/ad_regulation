"""
Quick test for activities endpoint
"""
import requests

BASE_URL = "http://127.0.0.1:8000"
PROXIES = {"http": None, "https": None}

print("Testing activities endpoint...")
print()

# Test health first
try:
    response = requests.get(f"{BASE_URL}/health", proxies=PROXIES, timeout=5)
    print(f"✓ Health check: {response.status_code}")
except Exception as e:
    print(f"❌ Server not responding: {e}")
    print("\nPlease start the server:")
    print("  uv run python run_api.py")
    exit(1)

# Test activities endpoint
try:
    response = requests.get(
        f"{BASE_URL}/ad-control/activities",
        params={"ad_account_id": "1279567647104057", "limit": 5},
        headers={"X-User-Id": "admin"},
        proxies=PROXIES,
        timeout=10
    )

    print(f"Activities endpoint: {response.status_code}")
    print()

    if response.status_code == 404:
        print("❌ ERROR: Endpoint returns 404")
        print()
        print("The code has the endpoint, but the running server doesn't.")
        print()
        print("SOLUTION:")
        print("1. Stop the API server (Ctrl+C)")
        print("2. Clear Python cache:")
        print("   cd D:/projects/ad_regulation")
        print("   rm -rf api/__pycache__ api/*/__pycache__")
        print("3. Restart server:")
        print("   uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000")
        print()

    elif response.status_code == 200:
        print("✓ SUCCESS! Endpoint is working!")
        data = response.json()
        if data.get("success"):
            total = data["data"]["total_activities"]
            print(f"  Found {total} activities")
            if data["data"]["activities"]:
                first = data["data"]["activities"][0]
                print(f"  Latest: {first.get('event_time')} - {first.get('event_type')} by {first.get('actor_name')}")
        print()

    else:
        print(f"Unexpected status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        print()

except Exception as e:
    print(f"❌ Request failed: {e}")
    print()
