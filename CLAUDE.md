# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **automated Facebook advertising regulation system** designed to optimize ad performance through data-driven decision making. The system uses Facebook Python Business SDK for ad operations and data fetching, with authentication credentials stored in MongoDB.

### System Goals
- **Automatic Ad Control**: Programmatically start, stop, and adjust Facebook ads based on performance
- **ML-Powered Evaluation**: Use HistGradientBoostingClassifier to predict ad performance and recommend stop/continue decisions based on ROAS (Return on Ad Spend) targets
- **Rule-Based + ML Hybrid**: Combine business rules with machine learning for comprehensive ad evaluation
- **API Service**: Expose ad operations and evaluation functionality through FastAPI endpoints (planned)

### Current Implementation Status
- ✅ Facebook API integration with Flyweight pattern for authentication caching
- ✅ Data fetching pipeline with async task management
- ✅ Feature engineering with lag features, trends, and volatility metrics
- ✅ ML model training with HistGradientBoostingClassifier
- ✅ FastAPI service layer with Insights data endpoints
- ✅ ML prediction API endpoints for ad evaluation
- ✅ Ad control operations (start/stop ads, update names, modify budgets)
- 🚧 Rule-based evaluation engine (to be implemented)
- 🚧 Automated decision-making system (to be implemented)

## Architecture

### Core Components

1. **Data Layer** (`utils/db.py`)
   - Uses Beanie ODM (Object Document Mapper) on top of PyMongo for async MongoDB operations
   - Document models: `ADAccountDocument`, `FbAppAuthDocument`, `FbAppTokenInfoDocument`, `BIUserAdAccountLink`
   - All database operations are async (use `await`)
   - Connection must be initialized with `await init_db()` before any DB operations

2. **Facebook API Integration** (`utils/fb_api_flyweight_factory.py`)
   - Implements Flyweight pattern to cache `FacebookAdsApi` instances per ad account
   - Use `get_ad_object(ad_account_id, fbid)` to get Facebook ad objects with proper authentication
   - Authentication credentials are stored in MongoDB and linked to ad accounts

3. **Insights Fetching** (`utils/insight_tool.py`)
   - Core atomic metrics: spend, impressions, reach, clicks, inline_link_clicks, outbound_clicks, and conversion actions
   - `get_atomic_metric()` extracts and transforms raw API responses into structured metrics
   - Helper functions: `get_daily_insight()`, `get_advertiser_hourly_insight()`, `get_audience_hourly_insight()`, `get_country_insight()`
   - Data is typed with `atomic_dtype_spec` for memory efficiency (float32/int32)

4. **Data Pipeline** (`baseline/`)
   - `get_data.py`: Async data fetching from Facebook API, saves to `.feather` files
     - Supports both sync (`get_insight()`) and async (`get_insight_tasks()`) fetching
     - `await_async_tasks()` polls async jobs until completion, with automatic retry logic
   - `data_build.py`: Feature engineering and label generation
     - `clean_data()`: Removes invalid records and low-spend ads
     - `build_features()`: Creates lag features (1-7 days), decay-weighted averages, trends, momentum, volatility
     - `build_labels()`: Generates binary stop/continue labels based on ROAS thresholds with margin zones
   - `train_tools.py`: Model training pipeline with sklearn HistGradientBoostingClassifier
     - `train_model()` handles full pipeline: split by ad_id, train, threshold optimization on F1
     - Returns comprehensive metrics: AUC, classification reports, predicted probabilities

5. **FastAPI Service Layer** (`api/`)
   - `app.py`: Main FastAPI application with lifespan management and error handlers
   - `routers/`: API endpoint definitions
     - `health.py`: Health check endpoint
     - `ad_accounts.py`: Ad account management endpoints
     - `insights.py`: Insights data fetching endpoints (sync and async)
     - `predictions.py`: ML-powered ad evaluation endpoints
     - `ad_control.py`: Ad control operations (start/stop, update name/budget)
   - `services/`: Business logic layer
     - `insights_service.py`: Service for fetching and processing Facebook Ads Insights
     - `prediction_service.py`: Service for ad performance prediction using trained ML models
     - `ad_control_service.py`: Service for controlling Facebook ads (status, name, budget)
   - `models/`: Pydantic request/response models
     - `responses.py`: Standard success/error response models
     - `ad_accounts.py`: Ad account models
     - `insights.py`: Insights data models, async job models, and prediction models
     - `ad_control.py`: Ad control request/response models
   - `dependencies/`: Shared dependencies
     - `auth.py`: User authentication via X-User-Id header
     - `database.py`: Database connection management

### Data Flow

**Current Implementation:**
1. Facebook API → Raw insights data (via `get_data.py` or API endpoints)
2. Raw data → Cleaned data → Feature matrix (via `data_build.py`)
3. Features + Labels → Trained model (via `train_tools.py`)
4. Model predictions → Ad stop/continue recommendations

**API Architecture (Current):**
```
┌─────────────────────────────────────────────────────┐
│            FastAPI Application                      │
│  ┌──────┬──────────┬──────────┬────────┬──────────┐│
│  │Health│    Ad    │ Insights │   ML   │   Ad     ││
│  │      │ Accounts │   API    │ Predict│ Control  ││
│  └──────┴──────────┴──────────┴────────┴──────────┘│
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────┴─────────┐
    │                    │
┌───▼────────────┐ ┌────▼──────────┐
│ Service Layer  │ │  Auth Layer   │
│ - Insights     │ │ - X-User-Id   │
│ - Predictions  │ │               │
│ - Ad Control   │ │               │
└───┬────────────┘ └───────────────┘
    │
┌───▼─────────────────────────────┐
│  Facebook API Integration       │
│  - Flyweight Pattern Caching    │
│  - Sync/Async Insights Fetching │
└───┬─────────────────────────────┘
    │
┌───▼─────────────┐
│ Facebook Ads API│
└─────────────────┘
```

**Future Extensions:**
```
┌─────────────────┐
│  FastAPI Layer  │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼────┐ ┌──▼────────┐
│ Rule   │ │ ML Model  │
│ Engine │ │ Predictor │
└───┬────┘ └──┬────────┘
    │         │
    └────┬────┘
         │
┌────────▼─────────┐
│ Ad Control Layer │
│ (SDK Actions)    │
└────────┬─────────┘
         │
┌────────▼─────────┐
│ Facebook Ads API │
└──────────────────┘
```

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv (Python 3.12+ required)
uv sync
```

### Running Data Pipeline
```bash
# Fetch Facebook Ads data (requires MongoDB running)
python baseline/get_data.py

# Build features and labels from raw data
python baseline/data_build.py

# Train model
python baseline/train_tools.py
```

### Running API Server
```bash
# Start the API server (development mode with auto-reload)
python run_api.py
# Or using uvicorn directly
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# Access API documentation
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### Docker Services
```bash
# Start MinIO for object storage (configured but not actively used in current code)
docker compose up -d
```

### Testing Individual Components
```bash
# Test MongoDB connection and Beanie models
python -c "from utils.db import init_db, close_db; import asyncio; asyncio.run(init_db())"

# Test Facebook API connection (requires valid credentials in MongoDB)
python utils/insight_tool.py

# Test feature building
python baseline/data_build.py
```

## Configuration

### Environment Variables (config.py)
- `MONGODB_HOST`: MongoDB hostname (default: localhost)
- `MONGODB_PORT`: MongoDB port (default: 27017)
- `MONGODB_DB_NAME`: Database name (default: fb_monitor)
- `MONGO_INITDB_ROOT_USERNAME`: MongoDB admin username
- `MONGO_INITDB_ROOT_PASSWORD`: MongoDB admin password

### Data Storage
- Raw insights data: `.feather` files in `D:/data/insights_data_1020/` (hardcoded in `get_data.py`)
- Feature/label files: `models/feat.feather`, `models/labels.feather`
- Trained models: Saved with joblib as `.feather` files

## Key Design Patterns

1. **Flyweight Pattern**: Facebook API clients are cached per ad account to avoid redundant authentication
2. **Async/Await**: All database and API operations are async; use `asyncio.run()` for entry points
3. **Ad-level Grouping**: Features and labels are computed per ad_id, maintaining temporal consistency
4. **Feather Format**: All DataFrames use `.feather` for fast I/O and type preservation

## Development Principles

### Code Quality Standards
- **Simplicity**: Prefer simple, readable code over clever abstractions
- **Architecture**: Follow clean architecture principles with clear separation of concerns
- **Best Practices**: Adhere to Python and async programming best practices
- **Type Hints**: Use type annotations for better code documentation and IDE support

### FastAPI Development Guidelines (for future implementation)
1. **Authentication**: Extract user identity from request headers
   - Primary header: `X-User-Id` for user identification
   - Use FastAPI dependency injection for authentication middleware
   - Example pattern:
   ```python
   from fastapi import Header, HTTPException

   async def get_current_user(x_user_id: str = Header(...)) -> str:
       if not x_user_id:
           raise HTTPException(status_code=401, detail="User ID required")
       return x_user_id
   ```

2. **Service Layer Pattern**:
   - Controllers (FastAPI routes) → Service layer → Data access layer
   - Keep route handlers thin, business logic in services
   - Services should be async and testable

3. **Error Handling**:
   - Use FastAPI's HTTPException for API errors
   - Log all exceptions with context
   - Return consistent error response formats

4. **Dependency Injection**:
   - Use FastAPI's Depends() for database connections, user context
   - Singleton pattern for model loading and API client factories

## Important Notes

- Ad account IDs have `act_` prefix in Facebook API but may be stored without it
- Time ranges in insights use `YYYY-MM-DD` format
- Feature lookback window is 3 days by default, with 4 additional days appended for context
- Label calculation uses combined past 3 days + future 7 days to compute ROAS
- Model splits data by ad_id (not by time) to prevent leakage across ads
- Threshold optimization maximizes F1 score on validation set

## Database Schema

- `ADAccountDocument`: Ad account info with linked FB app auth
- `FbAppAuthDocument`: App credentials (app_id, app_secret, access_token, user_id)
- `FbAppTokenInfoDocument`: Token metadata from Facebook Graph API
- `BIUserAdAccountLink`: User-account relationships with role-based access

## API Endpoints

### Authentication
All endpoints require the `X-User-Id` header for user authentication.

### Available Endpoints

#### Health Check
- `GET /health` - Check service health status

#### Ad Accounts
- `GET /ad-accounts` - List all ad accounts
- `GET /ad-accounts/{account_id}` - Get specific ad account details

#### Insights Data (Synchronous)
- `GET /insights/sync` - Fetch insights data immediately
  - Query parameters:
    - `ad_account_id` (required): Ad account ID
    - `since` (required): Start date (YYYY-MM-DD)
    - `until` (required): End date (YYYY-MM-DD)
    - `level` (optional): Aggregation level (ad/adset/campaign), default: "ad"
    - `time_increment` (optional): Time granularity (1=daily, null=aggregate)
    - `breakdowns` (optional): Breakdown dimensions (e.g., "country", "hourly_stats_aggregated_by_advertiser_time_zone")

#### Insights Data (Asynchronous)
- `POST /insights/async` - Create async insights job
  - Request body: JSON with `ad_account_id`, `since`, `until`, `level`, `time_increment`, `breakdowns`
  - Returns: `job_id` and initial status
- `GET /insights/async/{job_id}` - Check job status
  - Query parameters: `ad_account_id`
  - Returns: Job status and completion percentage
- `GET /insights/async/{job_id}/result` - Get completed job results
  - Query parameters: `ad_account_id`
  - Returns: Insights data (only when job is completed)

#### ML-Powered Ad Evaluation (Predictions)
- `POST /predictions/evaluate` - Evaluate ad performance for today using ML model
  - Request body: JSON with optional `ad_account_ids`, `lookback_days`, `model_path`
  - Returns: Predictions with stop probabilities and features for all ads
  - If `ad_account_ids` is null, evaluates all accounts
- `GET /predictions/evaluate/{ad_account_id}` - Evaluate ads for a specific account
  - Path parameter: `ad_account_id` (with or without act_ prefix)
  - Query parameters:
    - `lookback_days` (optional): Days to look back (default: 10, range: 7-30)
  - Returns: Predictions with stop probabilities for the specified account

#### Ad Control Operations
- `GET /ad-control/status` - Get current status and details of an ad
  - Query parameters:
    - `ad_account_id` (required): Ad account ID (with or without act_ prefix)
    - `ad_id` (required): Ad ID to query
  - Returns: Ad status, name, campaign/adset IDs, created/updated time
- `POST /ad-control/start` - Start (activate) an ad
  - Request body: JSON with `ad_account_id`, `ad_id`
  - Returns: Operation result and updated ad status
- `POST /ad-control/stop` - Stop (pause) an ad
  - Request body: JSON with `ad_account_id`, `ad_id`
  - Returns: Operation result and updated ad status
- `POST /ad-control/update-name` - Update ad name
  - Request body: JSON with `ad_account_id`, `ad_id`, `new_name`
  - Returns: Operation result and updated ad details
- `GET /ad-control/adset/budget` - Get AdSet budget information
  - Query parameters:
    - `ad_account_id` (required): Ad account ID
    - `adset_id` (required): AdSet ID to query
  - Returns: Daily budget, lifetime budget, budget remaining (in cents)
- `POST /ad-control/adset/update-budget` - Update AdSet budget
  - Request body: JSON with `ad_account_id`, `adset_id`, and optional `daily_budget` or `lifetime_budget` (in cents)
  - Returns: Operation result and updated budget details
  - Note: Budget values are in cents (100 cents = $1.00)
- `GET /ad-control/activities` - Get account activities (activity log / audit trail)
  - Query parameters:
    - `ad_account_id` (required): Ad account ID (with or without act_ prefix)
    - `object_id` (optional): Filter by specific object ID (ad, adset, or campaign)
    - `limit` (optional): Maximum number of activities to retrieve (default: 100, max: 10000)
  - Returns: List of historical modification records with event time, actor, event type, object details, and extra metadata
  - Use cases: Track who changed what and when, audit ad modifications, debug unexpected changes

### Usage Examples

#### Example 1: Fetch Daily Insights (Sync)
```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123&since=2025-10-01&until=2025-10-20&time_increment=1" \
  -H "X-User-Id: user123"
```

#### Example 2: Fetch Hourly Insights by Advertiser Time Zone (Sync)
```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123&since=2025-10-20&until=2025-10-20&breakdowns=hourly_stats_aggregated_by_advertiser_time_zone" \
  -H "X-User-Id: user123"
```

#### Example 3: Fetch Country-Level Insights (Sync)
```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123&since=2025-10-01&until=2025-10-20&time_increment=1&breakdowns=country" \
  -H "X-User-Id: user123"
```

#### Example 4: Large Data Fetch (Async)
```bash
# Step 1: Create async job
curl -X POST "http://localhost:8000/insights/async" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "act_123",
    "since": "2025-01-01",
    "until": "2025-12-31",
    "level": "ad",
    "time_increment": 1
  }'

# Response: {"success": true, "data": {"job_id": "12345678", ...}}

# Step 2: Check job status
curl -X GET "http://localhost:8000/insights/async/12345678?ad_account_id=act_123" \
  -H "X-User-Id: user123"

# Response: {"success": true, "data": {"status": "Job Completed", "percent_complete": 100, ...}}

# Step 3: Get results
curl -X GET "http://localhost:8000/insights/async/12345678/result?ad_account_id=act_123" \
  -H "X-User-Id: user123"
```

#### Example 5: Evaluate All Ads with ML Model
```bash
# Evaluate all ad accounts
curl -X POST "http://localhost:8000/predictions/evaluate" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "lookback_days": 10
  }'

# Response:
# {
#   "success": true,
#   "data": {
#     "predictions": [
#       {
#         "ad_account_name": "My Account",
#         "ad_id": "123456789",
#         "date": "2025-10-27",
#         "pred_proba": 0.75,
#         "features": {
#           "spend_lag1": 100.5,
#           "roas_lag1": 0.45,
#           "ctr_lag1": 0.02,
#           ...
#         }
#       }
#     ],
#     "total_records": 50,
#     "date_range": {"since": "2025-10-17", "until": "2025-10-27"},
#     "evaluation_date": "2025-10-27"
#   }
# }
```

#### Example 6: Evaluate Specific Ad Account
```bash
curl -X GET "http://localhost:8000/predictions/evaluate/act_123?lookback_days=10" \
  -H "X-User-Id: user123"

# Response: Same format as Example 5, but only for the specified account
```

#### Example 7: Get Ad Status
```bash
curl -X GET "http://localhost:8000/ad-control/status?ad_account_id=1279567647104057&ad_id=120234815168290189" \
  -H "X-User-Id: user123"

# Response:
# {
#   "success": true,
#   "data": {
#     "ad_id": "120234815168290189",
#     "name": "Ad global_engagement_$1",
#     "configured_status": "PAUSED",
#     "effective_status": "PAUSED",
#     "campaign_id": "120234813759620189",
#     "adset_id": "120234814836800189"
#   }
# }
```

#### Example 8: Start/Stop Ad
```bash
# Start an ad
curl -X POST "http://localhost:8000/ad-control/start" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189"
  }'

# Stop an ad
curl -X POST "http://localhost:8000/ad-control/stop" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189"
  }'
```

#### Example 9: Update Ad Name and Budget
```bash
# Update ad name
curl -X POST "http://localhost:8000/ad-control/update-name" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189",
    "new_name": "优化后的广告"
  }'

# Update adset daily budget to $5.00
curl -X POST "http://localhost:8000/ad-control/adset/update-budget" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "adset_id": "120234814836800189",
    "daily_budget": 500
  }'
```

#### Example 10: Get Account Activities (Activity Log / Audit Trail)
```bash
# Get all account activities (last 100 records)
curl -X GET "http://localhost:8000/ad-control/activities?ad_account_id=1279567647104057&limit=100" \
  -H "X-User-Id: user123"

# Get activities for a specific ad
curl -X GET "http://localhost:8000/ad-control/activities?ad_account_id=1279567647104057&object_id=120234815168290189&limit=50" \
  -H "X-User-Id: user123"

# Response:
# {
#   "success": true,
#   "data": {
#     "total_activities": 15,
#     "activities": [
#       {
#         "event_time": "2025-10-29T10:30:00+0000",
#         "actor_name": "John Doe",
#         "event_type": "update",
#         "object_type": "ad",
#         "object_id": "120234815168290189",
#         "object_name": "Ad global_engagement_$1",
#         "extra_data": {
#           "field": "status",
#           "old_value": "ACTIVE",
#           "new_value": "PAUSED"
#         }
#       }
#     ]
#   }
# }
```

### Response Format
All endpoints return standardized JSON responses:

**Success Response:**
```json
{
  "success": true,
  "data": { ... },
  "message": "Optional success message"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description",
    "details": { ... }
  }
}
```
