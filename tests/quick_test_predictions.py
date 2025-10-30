"""
Quick test script for Predictions API endpoints.
Simple smoke test to verify the prediction endpoints are working.

Usage:
    python tests/quick_test_predictions.py [ad_account_id]

Example:
    python tests/quick_test_predictions.py act_1302299391281701
"""

import asyncio
import sys

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
USER_ID = "admin"


async def quick_test(ad_account_id: str):
    """Run a quick test of the prediction endpoint."""
    print(f"\n{'=' * 60}")
    print("QUICK PREDICTION API TEST")
    print(f"{'=' * 60}")
    print(f"Testing Account: {ad_account_id}")
    print(f"Base URL: {BASE_URL}\n")

    headers = {"X-User-Id": USER_ID}

    try:
        async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
            # Test the GET endpoint (simpler and faster)
            print("📡 Sending request to prediction endpoint...")
            print(f"   GET /predictions/evaluate/{ad_account_id}?lookback_days=10")
            print("   ⏳ This may take 1-3 minutes...\n")

            response = await client.get(
                f"{BASE_URL}/predictions/evaluate/{ad_account_id}",
                headers=headers,
                params={"lookback_days": 10}
            )

            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if data.get("success"):
                    prediction_data = data["data"]

                    print("\n✅ SUCCESS!")
                    print(f"\n📊 Results:")
                    print(f"   Total Predictions: {prediction_data['total_records']}")
                    print(f"   Evaluation Date: {prediction_data['evaluation_date']}")
                    print(f"   Date Range: {prediction_data['date_range']['since']} to {prediction_data['date_range']['until']}")

                    # Show sample predictions
                    predictions = prediction_data["predictions"][:5]
                    if predictions:
                        print(f"\n   Top {len(predictions)} Predictions:")
                        for i, pred in enumerate(predictions, 1):
                            stop_prob = pred['pred_proba']
                            emoji = "🔴" if stop_prob > 0.7 else "🟡" if stop_prob > 0.4 else "🟢"
                            print(f"\n   {i}. {emoji} Ad ID: {pred['ad_id']}")
                            print(f"      Account: {pred['ad_account_name']}")
                            print(f"      Stop Probability: {stop_prob:.2%}")
                            print(f"      Recommendation: {'CONSIDER STOPPING' if stop_prob > 0.7 else 'MONITOR' if stop_prob > 0.4 else 'KEEP RUNNING'}")

                    print(f"\n{'=' * 60}")
                    print("✅ PREDICTION API IS WORKING!")
                    print(f"{'=' * 60}\n")

                else:
                    print(f"\n❌ FAILED: {data}")

            elif response.status_code == 404:
                error_data = response.json()
                print(f"\n⚠️  MODEL NOT FOUND")
                print(f"Detail: {error_data.get('detail', 'Unknown error')}")
                print(f"\nPlease ensure:")
                print(f"  1. Model has been trained (run baseline/train_tools.py)")
                print(f"  2. Model file exists at: models/model.feather\n")

            elif response.status_code == 400:
                error_data = response.json()
                print(f"\n⚠️  BAD REQUEST")
                print(f"Detail: {error_data.get('detail', 'Unknown error')}")
                print(f"\nPossible issues:")
                print(f"  1. Ad account ID not found or invalid")
                print(f"  2. No data available for the specified lookback period\n")

            else:
                print(f"\n❌ UNEXPECTED STATUS CODE: {response.status_code}")
                print(f"Response: {response.text}\n")

    except httpx.ConnectError:
        print(f"\n❌ CONNECTION ERROR")
        print(f"Cannot connect to {BASE_URL}")
        print(f"\nPlease ensure:")
        print(f"  1. API server is running (python run_api.py)")
        print(f"  2. Server is accessible at {BASE_URL}\n")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point."""
    # Get ad account ID from command line or use default
    if len(sys.argv) > 1:
        ad_account_id = sys.argv[1]
    else:
        ad_account_id = "act_1302299391281701"  # Default test account
        print(f"No ad_account_id provided, using default: {ad_account_id}")
        print(f"Usage: python {sys.argv[0]} [ad_account_id]\n")

    await quick_test(ad_account_id)


if __name__ == "__main__":
    asyncio.run(main())
