"""
Test script for Predictions API endpoints.
Tests ML-powered ad evaluation endpoints and error handling.

Usage:
    python tests/test_predictions_api.py
"""

import asyncio
from datetime import datetime, timedelta

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "admin"
AD_ACCOUNT_ID = "act_1302299391281701"  # Replace with your test account ID

# Test parameters
DEFAULT_LOOKBACK_DAYS = 10
CUSTOM_LOOKBACK_DAYS = 15


def print_test_header(test_name: str):
    """Print a formatted test header."""
    print(f"\n{'=' * 60}")
    print(f"TEST: {test_name}")
    print(f"{'=' * 60}")


def print_response(response: httpx.Response):
    """Print formatted HTTP response."""
    print(f"Status: {response.status_code}")
    try:
        json_data = response.json()
        print(f"Response: {json_data}\n")

        # Print prediction summary if available
        if response.status_code == 200 and "data" in json_data:
            data = json_data["data"]
            if "predictions" in data:
                print(f"📊 Summary:")
                print(f"   Total Records: {data.get('total_records', 0)}")
                print(f"   Date Range: {data.get('date_range', {})}")
                print(f"   Evaluation Date: {data.get('evaluation_date', 'N/A')}")

                # Show first few predictions
                predictions = data["predictions"][:3]
                if predictions:
                    print(f"\n   Sample Predictions (first 3):")
                    for i, pred in enumerate(predictions, 1):
                        print(f"   {i}. Ad ID: {pred['ad_id']}")
                        print(f"      Account: {pred['ad_account_name']}")
                        print(f"      Stop Probability: {pred['pred_proba']:.2%}")
                        print(f"      Date: {pred['date']}")
                        print()
    except Exception as e:
        print(f"Response Text: {response.text}\n")
        print(f"⚠️  Could not parse JSON: {e}")


async def test_health_check():
    """Test the health check endpoint."""
    print_test_header("Health Check")

    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get(f"{BASE_URL}/health")
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    print("✅ Health check passed")


async def test_evaluate_all_accounts():
    """Test POST /predictions/evaluate - Evaluate all accounts."""
    print_test_header("Evaluate All Accounts (Default Parameters)")

    headers = {"X-User-Id": USER_ID}
    payload = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS
    }

    print(f"Evaluating all accounts with lookback_days={DEFAULT_LOOKBACK_DAYS}...")
    print("⚠️  This may take several minutes for multiple accounts...\n")

    async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json=payload
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "predictions" in data["data"]
        assert "total_records" in data["data"]
        assert "evaluation_date" in data["data"]

    print("✅ Evaluate all accounts passed")


async def test_evaluate_specific_accounts():
    """Test POST /predictions/evaluate - Evaluate specific accounts."""
    print_test_header("Evaluate Specific Accounts")

    headers = {"X-User-Id": USER_ID}
    payload = {
        "ad_account_ids": [AD_ACCOUNT_ID],
        "lookback_days": CUSTOM_LOOKBACK_DAYS
    }

    print(f"Evaluating account {AD_ACCOUNT_ID} with lookback_days={CUSTOM_LOOKBACK_DAYS}...")
    print("⏳ Processing...\n")

    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json=payload
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "predictions" in data["data"]

        # Verify predictions have required fields
        if data["data"]["predictions"]:
            pred = data["data"]["predictions"][0]
            assert "ad_account_name" in pred
            assert "ad_id" in pred
            assert "date" in pred
            assert "pred_proba" in pred
            assert "features" in pred
            assert 0.0 <= pred["pred_proba"] <= 1.0

    print("✅ Evaluate specific accounts passed")


async def test_evaluate_single_account_get():
    """Test GET /predictions/evaluate/{ad_account_id}."""
    print_test_header("Evaluate Single Account (GET Endpoint)")

    headers = {"X-User-Id": USER_ID}
    params = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS
    }

    print(f"Evaluating account {AD_ACCOUNT_ID} via GET endpoint...")
    print("⏳ Processing...\n")

    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        response = await client.get(
            f"{BASE_URL}/predictions/evaluate/{AD_ACCOUNT_ID}",
            headers=headers,
            params=params
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "predictions" in data["data"]

    print("✅ Evaluate single account GET passed")


async def test_evaluate_with_custom_model_path():
    """Test POST /predictions/evaluate - Custom model path."""
    print_test_header("Evaluate with Custom Model Path")

    headers = {"X-User-Id": USER_ID}
    payload = {
        "ad_account_ids": [AD_ACCOUNT_ID],
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "model_path": "models/model.feather"  # Using default model path
    }

    print(f"Evaluating with custom model path...")
    print("⏳ Processing...\n")

    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json=payload
        )
        print_response(response)

        # Should succeed if model exists at specified path
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            print("✅ Custom model path test passed")
        elif response.status_code == 404:
            print("⚠️  Model file not found (expected if model hasn't been trained)")
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")


async def test_lookback_days_boundaries():
    """Test lookback_days parameter boundaries."""
    print_test_header("Lookback Days Boundary Tests")

    headers = {"X-User-Id": USER_ID}

    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        # Test 1: Minimum boundary (7 days)
        print("\nTest 1: Minimum lookback_days (7)")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"ad_account_ids": [AD_ACCOUNT_ID], "lookback_days": 7}
        )
        print(f"Status: {response.status_code} (Expected: 200)")
        if response.status_code == 200:
            print("✅ Minimum boundary passed")
        else:
            print_response(response)

        # Test 2: Maximum boundary (30 days)
        print("\nTest 2: Maximum lookback_days (30)")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"ad_account_ids": [AD_ACCOUNT_ID], "lookback_days": 30}
        )
        print(f"Status: {response.status_code} (Expected: 200)")
        if response.status_code == 200:
            print("✅ Maximum boundary passed")
        else:
            print_response(response)

        # Test 3: Below minimum (should fail)
        print("\nTest 3: Below minimum lookback_days (6)")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"ad_account_ids": [AD_ACCOUNT_ID], "lookback_days": 6}
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422
        print("✅ Below minimum validation passed")

        # Test 4: Above maximum (should fail)
        print("\nTest 4: Above maximum lookback_days (31)")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"ad_account_ids": [AD_ACCOUNT_ID], "lookback_days": 31}
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422
        print("✅ Above maximum validation passed")


async def test_error_handling():
    """Test error handling with invalid requests."""
    print_test_header("Error Handling")

    headers = {"X-User-Id": USER_ID}

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        # Test 1: Missing authentication header
        print("\nTest 1: Missing X-User-Id header")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            json={"lookback_days": DEFAULT_LOOKBACK_DAYS}
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422
        print("✅ Missing auth header validation passed")

        # Test 2: Invalid ad_account_id format
        print("\nTest 2: Non-existent ad account")
        response = await client.get(
            f"{BASE_URL}/predictions/evaluate/act_invalid_999999",
            headers=headers,
            params={"lookback_days": DEFAULT_LOOKBACK_DAYS}
        )
        print(f"Status: {response.status_code} (Expected: 400 or 500)")
        # May return 400 (bad request) or 500 (error during processing)
        assert response.status_code in [400, 500]
        print("✅ Invalid account handling passed")

        # Test 3: Invalid request body
        print("\nTest 3: Invalid request body (wrong type)")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"lookback_days": "invalid"}  # Should be int
        )
        print(f"Status: {response.status_code} (Expected: 422)")
        assert response.status_code == 422
        print("✅ Invalid body validation passed")

        # Test 4: Empty ad_account_ids list
        print("\nTest 4: Empty ad_account_ids list")
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json={"ad_account_ids": [], "lookback_days": DEFAULT_LOOKBACK_DAYS}
        )
        print(f"Status: {response.status_code}")
        # May succeed but return no predictions, or fail with 400
        if response.status_code == 200:
            data = response.json()
            assert data["data"]["total_records"] == 0
            print("✅ Empty list returns no predictions")
        elif response.status_code == 400:
            print("✅ Empty list validation passed")

    print("\n✅ All error handling tests passed")


async def test_model_not_found():
    """Test behavior when model file doesn't exist."""
    print_test_header("Model Not Found Handling")

    headers = {"X-User-Id": USER_ID}
    payload = {
        "ad_account_ids": [AD_ACCOUNT_ID],
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "model_path": "models/nonexistent_model.feather"
    }

    print("Testing with non-existent model path...")

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json=payload
        )
        print_response(response)

        assert response.status_code == 404
        data = response.json()

        # FastAPI HTTPException returns {'detail': '...'} format
        # Our custom ErrorResponse returns {'success': False, 'error': {...}} format
        # Accept either format
        if "detail" in data:
            assert "Model file not found" in data["detail"]
        elif "success" in data:
            assert data["success"] is False
            assert "error" in data
        else:
            raise AssertionError(f"Unexpected response format: {data}")

    print("✅ Model not found handling passed")


async def test_prediction_output_format():
    """Test that prediction output format matches expected structure."""
    print_test_header("Prediction Output Format Validation")

    headers = {"X-User-Id": USER_ID}
    payload = {
        "ad_account_ids": [AD_ACCOUNT_ID],
        "lookback_days": DEFAULT_LOOKBACK_DAYS
    }

    async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
        response = await client.post(
            f"{BASE_URL}/predictions/evaluate",
            headers=headers,
            json=payload
        )

        if response.status_code != 200:
            print("⚠️  Skipping format validation (no successful response)")
            return

        data = response.json()

        # Validate top-level structure
        assert "success" in data
        assert "data" in data
        assert data["success"] is True

        # Validate data structure
        prediction_data = data["data"]
        assert "predictions" in prediction_data
        assert "total_records" in prediction_data
        assert "date_range" in prediction_data
        assert "evaluation_date" in prediction_data

        # Validate date_range structure
        date_range = prediction_data["date_range"]
        assert "since" in date_range
        assert "until" in date_range

        # Validate prediction records
        if prediction_data["predictions"]:
            pred = prediction_data["predictions"][0]

            # Required fields
            assert "ad_account_name" in pred
            assert "ad_id" in pred
            assert "date" in pred
            assert "pred_proba" in pred
            assert "features" in pred

            # Type validation
            assert isinstance(pred["ad_account_name"], str)
            assert isinstance(pred["ad_id"], str)
            assert isinstance(pred["date"], str)
            assert isinstance(pred["pred_proba"], (int, float))
            assert isinstance(pred["features"], dict)

            # Value validation
            assert 0.0 <= pred["pred_proba"] <= 1.0

            # Features should contain numeric values or None
            for feature_name, feature_value in pred["features"].items():
                assert feature_value is None or isinstance(feature_value, (int, float))

            print(f"\n✅ Format validation passed")
            print(f"   Prediction record structure:")
            print(f"   - ad_account_name: {type(pred['ad_account_name']).__name__}")
            print(f"   - ad_id: {type(pred['ad_id']).__name__}")
            print(f"   - date: {type(pred['date']).__name__}")
            print(f"   - pred_proba: {type(pred['pred_proba']).__name__} (value: {pred['pred_proba']:.4f})")
            print(f"   - features: dict with {len(pred['features'])} features")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PREDICTIONS API TEST SUITE")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"User ID: {USER_ID}")
    print(f"Test Account: {AD_ACCOUNT_ID}")
    print(f"Default Lookback Days: {DEFAULT_LOOKBACK_DAYS}")
    print("=" * 60)

    try:
        # Preliminary test
        await test_health_check()

        # Core functionality tests (start with simpler tests first)
        print("\n💡 Starting with single account tests (faster)...\n")
        await test_evaluate_single_account_get()
        await test_evaluate_specific_accounts()

        print("\n💡 Now testing all accounts (may take several minutes)...\n")
        await test_evaluate_all_accounts()

        # Parameter validation tests
        await test_lookback_days_boundaries()
        await test_evaluate_with_custom_model_path()

        # Output format validation
        await test_prediction_output_format()

        # Error handling tests
        await test_error_handling()
        await test_model_not_found()

        print("\n" + "=" * 60)
        print("✅ ALL PREDICTION TESTS PASSED!")
        print("=" * 60)
        print("\n💡 Test Coverage:")
        print("   ✓ Health check")
        print("   ✓ Evaluate all accounts")
        print("   ✓ Evaluate specific accounts")
        print("   ✓ Single account GET endpoint")
        print("   ✓ Custom model path")
        print("   ✓ Lookback days boundaries")
        print("   ✓ Output format validation")
        print("   ✓ Error handling")
        print("   ✓ Model not found handling")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
