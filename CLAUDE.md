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
- 🚧 FastAPI service layer (to be implemented)
- 🚧 Automated ad control actions (to be implemented)
- 🚧 Rule-based evaluation engine (to be implemented)

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

### Data Flow

**Current Implementation:**
1. Facebook API → Raw insights data (via `get_data.py`)
2. Raw data → Cleaned data → Feature matrix (via `data_build.py`)
3. Features + Labels → Trained model (via `train_tools.py`)
4. Model predictions → Ad stop/continue recommendations

**Future Architecture (with FastAPI):**
```
┌─────────────────┐
│  FastAPI Layer  │
│  (Planned)      │
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
