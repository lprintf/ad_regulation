#!/usr/bin/env python3
"""
Quick test script for API endpoints.
Run this after starting the API server to verify everything works.
"""

import asyncio

import httpx


async def test_api():
    """Test basic API endpoints."""
    base_url = "http://localhost:8000"
    headers = {"X-User-Id": "admin"}

    # Disable proxy for localhost (trust_env=False ignores system proxy settings)
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        print("🧪 Testing API endpoints...\n")

        # Test 1: Root endpoint
        print("1. Testing root endpoint...")
        response = await client.get(f"{base_url}/")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Test 2: Health check
        print("2. Testing health endpoint...")
        response = await client.get(f"{base_url}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Test 3: List ad accounts (with auth)
        print("3. Testing ad accounts endpoint (with auth)...")
        response = await client.get(f"{base_url}/ad-accounts", headers=headers)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}\n")

        # Test 4: Missing auth header
        print("4. Testing missing auth header (should fail)...")
        try:
            response = await client.get(f"{base_url}/ad-accounts")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}\n")
        except Exception as e:
            print(f"   Error: {e}\n")

        print("✅ All tests completed!")


if __name__ == "__main__":
    try:
        asyncio.run(test_api())
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
