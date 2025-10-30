# Tests for Ad Regulation API

This directory contains test scripts for the Ad Regulation API endpoints.

## Test Scripts

### 1. Predictions API Tests

#### Comprehensive Test Suite
**File:** `test_predictions_api.py`

Full test suite covering all prediction endpoints, error handling, and edge cases.

```bash
# Run all prediction tests
python tests/test_predictions_api.py
```

**Test Coverage:**
- ✅ Health check
- ✅ Evaluate all accounts (POST endpoint)
- ✅ Evaluate specific accounts with custom parameters
- ✅ Single account evaluation (GET endpoint)
- ✅ Custom model path
- ✅ Lookback days boundary validation (7-30 days)
- ✅ Output format validation
- ✅ Error handling (invalid inputs, missing auth, etc.)
- ✅ Model not found handling

#### Quick Smoke Test
**File:** `quick_test_predictions.py`

Fast smoke test to verify the prediction API is working.

```bash
# Test with default account
python tests/quick_test_predictions.py

# Test with specific account
python tests/quick_test_predictions.py act_1302299391281701
```

**Output Example:**
```
QUICK PREDICTION API TEST
Testing Account: act_1302299391281701
...
✅ SUCCESS!
📊 Results:
   Total Predictions: 15
   Evaluation Date: 2025-10-27

   Top 5 Predictions:
   1. 🔴 Ad ID: 123456789
      Stop Probability: 85.23%
      Recommendation: CONSIDER STOPPING
   ...
```

### 2. Insights API Tests

#### Synchronous Insights Test
**File:** `test_insights_api.py`

Tests for synchronous insights fetching endpoints.

```bash
python tests/test_insights_api.py
```

**Test Coverage:**
- Health check
- List ad accounts
- Sync daily insights
- Sync aggregated insights
- Insights with breakdown dimensions
- Error handling

#### Async Insights Test
**File:** `test_async_insights.py`

Tests for asynchronous insights job management.

```bash
python tests/test_async_insights.py
```

**Test Coverage:**
- Create async job
- Check job status
- Fetch completed job results
- Job lifecycle management

## Configuration

Before running tests, update the following in each test file:

```python
BASE_URL = "http://localhost:8000"      # API server URL
USER_ID = "admin"                        # Test user ID
AD_ACCOUNT_ID = "act_1302299391281701"  # Your test account ID
```

## Prerequisites

1. **API Server Running:**
   ```bash
   python run_api.py
   # Or
   uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Database Connected:**
   - MongoDB must be running and accessible
   - Database must contain ad account credentials

3. **Model Trained (for prediction tests):**
   ```bash
   # Train the model first
   python baseline/train_tools.py
   ```
   - Model file should exist at: `models/model.feather`

4. **Dependencies Installed:**
   ```bash
   uv sync
   ```

## Test Categories

### ✅ Unit Tests
- Individual endpoint functionality
- Parameter validation
- Error handling

### ✅ Integration Tests
- End-to-end API workflows
- Database interactions
- Facebook API integration

### ✅ Smoke Tests
- Quick validation that services are up
- Basic functionality checks

## Troubleshooting

### Common Issues

**1. Connection Error**
```
❌ CONNECTION ERROR
Cannot connect to http://localhost:8000
```
**Solution:** Start the API server first
```bash
python run_api.py
```

**2. Model Not Found**
```
⚠️  MODEL NOT FOUND
Detail: Model file not found: models/model.feather
```
**Solution:** Train the model first
```bash
python baseline/train_tools.py
```

**3. Authentication Failed**
```
Status Code: 422
Missing X-User-Id header
```
**Solution:** Update USER_ID in test configuration

**4. Invalid Ad Account**
```
⚠️  BAD REQUEST
Detail: No valid predictions could be generated
```
**Solution:**
- Verify ad account ID is correct
- Ensure ad account has sufficient data
- Check MongoDB contains valid credentials for the account

## Test Output

### Success Example
```
============================================================
PREDICTIONS API TEST SUITE
============================================================
Base URL: http://localhost:8000
User ID: admin
Test Account: act_1302299391281701
============================================================

============================================================
TEST: Health Check
============================================================
Status: 200
Response: {'status': 'healthy', ...}
✅ Health check passed

============================================================
TEST: Evaluate All Accounts (Default Parameters)
============================================================
...
📊 Summary:
   Total Records: 25
   Date Range: {'since': '2025-10-17', 'until': '2025-10-27'}
   Evaluation Date: 2025-10-27
✅ Evaluate all accounts passed

...

============================================================
✅ ALL PREDICTION TESTS PASSED!
============================================================
```

### Failure Example
```
============================================================
TEST: Model Not Found Handling
============================================================
Status: 404
Response: {'success': False, 'error': {...}}
✅ Model not found handling passed
```

## Writing New Tests

To add new test cases, follow this pattern:

```python
async def test_your_feature():
    """Test description."""
    print_test_header("Your Feature Test")

    headers = {"X-User-Id": USER_ID}

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.get(
            f"{BASE_URL}/your-endpoint",
            headers=headers
        )
        print_response(response)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    print("✅ Your feature test passed")

# Add to main()
async def main():
    ...
    await test_your_feature()
    ...
```

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run API Tests
  run: |
    python run_api.py &
    sleep 5
    python tests/test_predictions_api.py
    python tests/test_insights_api.py
```

## Contributing

When adding new endpoints:
1. Add corresponding test cases
2. Update this README
3. Ensure all tests pass before committing

## Support

For issues or questions:
- Check the main project README
- Review API documentation at http://localhost:8000/docs
- Check test output for detailed error messages
