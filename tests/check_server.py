"""
Quick API server status check.
Checks if the server is running and responsive.
"""

import httpx


def check_server():
    """Check if API server is running."""
    print("Checking if API server is running on http://localhost:8000...")

    try:
        # Try to connect to root endpoint (doesn't require auth or DB)
        # Disable proxy for localhost
        response = httpx.get("http://localhost:8000/", timeout=5.0, trust_env=False)

        if response.status_code == 200:
            print("✅ API server is running!")
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"⚠️  Server responded but with status code: {response.status_code}")
            return False

    except httpx.ConnectError:
        print("❌ Cannot connect to API server")
        print("\nServer is NOT running. Please start it:")
        print("  python run_api.py")
        return False

    except httpx.ReadTimeout:
        print("❌ Server is not responding (timeout)")
        print("\nThe server might be stuck during startup.")
        print("Check the server terminal for error messages.")
        return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    check_server()
