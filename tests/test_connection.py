"""
Simple connection diagnostic script
"""
import requests
import os

print("=" * 80)
print("Connection Diagnostic Test")
print("=" * 80)
print()

# Check environment variables
print("Environment Variables:")
print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'Not set')}")
print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'Not set')}")
print(f"http_proxy: {os.environ.get('http_proxy', 'Not set')}")
print(f"https_proxy: {os.environ.get('https_proxy', 'Not set')}")
print(f"NO_PROXY: {os.environ.get('NO_PROXY', 'Not set')}")
print(f"no_proxy: {os.environ.get('no_proxy', 'Not set')}")
print()

# Test 1: Default requests (with environment)
print("Test 1: Default requests.get()")
try:
    response = requests.get("http://localhost:8000/health", timeout=5)
    print(f"✓ Success! Status: {response.status_code}")
    print(f"  Response: {response.text[:100]}")
except Exception as e:
    print(f"❌ Failed: {e}")
print()

# Test 2: With trust_env=False using session
print("Test 2: Session with trust_env=False")
try:
    session = requests.Session()
    session.trust_env = False
    response = session.get("http://localhost:8000/health", timeout=5)
    print(f"✓ Success! Status: {response.status_code}")
    print(f"  Response: {response.text[:100]}")
except Exception as e:
    print(f"❌ Failed: {e}")
print()

# Test 3: With explicit proxies=None
print("Test 3: With proxies={'http': None, 'https': None}")
try:
    response = requests.get(
        "http://localhost:8000/health",
        proxies={"http": None, "https": None},
        timeout=5
    )
    print(f"✓ Success! Status: {response.status_code}")
    print(f"  Response: {response.text[:100]}")
except Exception as e:
    print(f"❌ Failed: {e}")
print()

# Test 4: With 127.0.0.1 instead of localhost
print("Test 4: Using 127.0.0.1 instead of localhost")
try:
    session = requests.Session()
    session.trust_env = False
    response = session.get("http://127.0.0.1:8000/health", timeout=5)
    print(f"✓ Success! Status: {response.status_code}")
    print(f"  Response: {response.text[:100]}")
except Exception as e:
    print(f"❌ Failed: {e}")
print()

# Test 5: Test activities endpoint
print("Test 5: Test activities endpoint with trust_env=False")
try:
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        "http://127.0.0.1:8000/ad-control/activities",
        params={"ad_account_id": "1279567647104057", "limit": 10},
        headers={"X-User-Id": "test_user_123"},
        timeout=10
    )
    print(f"✓ Success! Status: {response.status_code}")
    print(f"  Response: {response.text[:200]}")
except Exception as e:
    print(f"❌ Failed: {e}")
print()

print("=" * 80)
print("Diagnostic Complete")
print("=" * 80)
