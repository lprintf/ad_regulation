# Ad Regulation API - Quick Start Guide

This guide will help you get started with the Ad Regulation API for fetching Facebook Ads Insights data.

## Prerequisites

- Python 3.12+
- MongoDB running locally
- Valid Facebook Ad Account credentials stored in MongoDB
- Dependencies installed via `uv sync`

## Starting the API Server

```bash
# Option 1: Using the run script
python run_api.py

# Option 2: Using uvicorn directly
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

**Interactive Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Authentication

All API endpoints require the `X-User-Id` header for authentication:

```bash
-H "X-User-Id: your-user-id"
```

## Available Endpoints

### 1. Health Check
Check if the API service is running:

```bash
curl http://localhost:8000/health
```

### 2. List Ad Accounts
Get all available ad accounts:

```bash
curl -X GET http://localhost:8000/ad-accounts \
  -H "X-User-Id: user123"
```

### 3. Synchronous Insights (For Small Data)

#### Daily Insights
Fetch daily breakdown of ad performance:

```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123456789&since=2025-10-01&until=2025-10-20&time_increment=1" \
  -H "X-User-Id: user123"
```

#### Aggregated Insights
Get aggregated data across the date range:

```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123456789&since=2025-10-01&until=2025-10-20" \
  -H "X-User-Id: user123"
```

#### With Breakdowns
Get insights broken down by country:

```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123456789&since=2025-10-01&until=2025-10-20&time_increment=1&breakdowns=country" \
  -H "X-User-Id: user123"
```

Hourly insights by advertiser timezone:

```bash
curl -X GET "http://localhost:8000/insights/sync?ad_account_id=act_123456789&since=2025-10-20&until=2025-10-20&breakdowns=hourly_stats_aggregated_by_advertiser_time_zone" \
  -H "X-User-Id: user123"
```

### 4. Asynchronous Insights (For Large Data)

For large date ranges or heavy queries, use the async workflow:

#### Step 1: Create Job

```bash
curl -X POST "http://localhost:8000/insights/async" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "act_123456789",
    "since": "2025-01-01",
    "until": "2025-12-31",
    "level": "ad",
    "time_increment": 1
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "job_id": "987654321",
    "ad_account_id": "act_123456789",
    "status": "Job Running",
    "created_at": "2025-10-27T12:00:00"
  },
  "message": "Async job created successfully. Job ID: 987654321"
}
```

#### Step 2: Check Status

```bash
curl -X GET "http://localhost:8000/insights/async/987654321?ad_account_id=act_123456789" \
  -H "X-User-Id: user123"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "job_id": "987654321",
    "ad_account_id": "act_123456789",
    "status": "Job Completed",
    "percent_complete": 100,
    "created_at": "2025-10-27T12:00:00",
    "updated_at": "2025-10-27T12:02:30"
  },
  "message": "Job status: Job Completed (100%)"
}
```

#### Step 3: Get Results

Once the job is completed (`status: "Job Completed"`):

```bash
curl -X GET "http://localhost:8000/insights/async/987654321/result?ad_account_id=act_123456789" \
  -H "X-User-Id: user123"
```

## Query Parameters Reference

| Parameter | Required | Type | Description | Example |
|-----------|----------|------|-------------|---------|
| `ad_account_id` | Yes | string | Ad account ID (with or without `act_` prefix) | `act_123456789` |
| `since` | Yes | string | Start date in YYYY-MM-DD format | `2025-01-01` |
| `until` | Yes | string | End date in YYYY-MM-DD format | `2025-01-31` |
| `level` | No | string | Aggregation level: `ad`, `adset`, or `campaign` | `ad` (default) |
| `time_increment` | No | int | Time granularity: `1` for daily, `null` for aggregate | `1` |
| `breakdowns` | No | string | Breakdown dimensions (comma-separated) | `country` |

### Common Breakdown Dimensions

- `country` - Breakdown by country
- `hourly_stats_aggregated_by_advertiser_time_zone` - Hourly data by advertiser timezone
- `hourly_stats_aggregated_by_audience_time_zone` - Hourly data by audience timezone
- `age` - Breakdown by age group
- `gender` - Breakdown by gender

## Response Format

All endpoints return standardized JSON responses:

### Success Response
```json
{
  "success": true,
  "data": {
    "insights": [
      {
        "ad_id": "123456789",
        "date": "2025-10-20",
        "metrics": {
          "spend": 100.50,
          "impressions": 5000,
          "reach": 3500,
          "clicks": 150,
          "inline_link_clicks": 120,
          "outbound_clicks": 100,
          "landing_page_view": 80,
          "onsite_web_checkout": 10,
          "onsite_web_add_to_cart": 25,
          "onsite_web_purchase": 5,
          "onsite_web_checkout_value": 150.00,
          "onsite_web_add_to_cart_value": 300.00,
          "onsite_web_purchase_value": 250.00
        }
      }
    ],
    "total_records": 100,
    "date_range": {
      "since": "2025-10-01",
      "until": "2025-10-20"
    }
  },
  "message": "Successfully fetched 100 insight records"
}
```

### Error Response
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "errors": [...]
    }
  }
}
```

## Running Tests

Run the test suite to verify your API setup:

```bash
python test_insights_api.py
```

**Note:** Update the `AD_ACCOUNT_ID` in the test script with your actual account ID.

## Tips & Best Practices

### When to Use Sync vs Async

**Use Sync (`/insights/sync`):**
- Date range ≤ 30 days
- Need immediate results
- Small to medium data volume

**Use Async (`/insights/async`):**
- Date range > 30 days
- Large data volume
- Can wait for results
- Multiple concurrent large queries

### Performance Optimization

1. **Use time_increment wisely:**
   - `time_increment=1` (daily) returns more records
   - `time_increment=null` (aggregate) returns summary data

2. **Limit date ranges:**
   - Facebook API has rate limits
   - Shorter ranges = faster responses

3. **Use breakdowns selectively:**
   - Breakdowns multiply the number of records
   - Example: 30 days × 50 ads × 10 countries = 15,000 records

## Common Issues

### 1. "X-User-Id header is required"
Add the authentication header to all requests:
```bash
-H "X-User-Id: your-user-id"
```

### 2. "Failed to fetch insights"
- Verify MongoDB is running
- Check Facebook credentials in database
- Ensure ad account ID is correct (with `act_` prefix)

### 3. "Job is not completed yet"
Wait for async job to complete before fetching results. Poll the status endpoint until `status: "Job Completed"`.

## Ad Control Operations

The API now supports direct ad control operations for managing Facebook ads.

### 1. Get Ad Status

Query the current status and details of an ad:

```bash
curl -X GET "http://localhost:8000/ad-control/status?ad_account_id=1279567647104057&ad_id=120234815168290189" \
  -H "X-User-Id: user123"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "ad_id": "120234815168290189",
    "name": "Ad global_engagement_$1",
    "configured_status": "PAUSED",
    "effective_status": "PAUSED",
    "campaign_id": "120234813759620189",
    "adset_id": "120234814836800189",
    "created_time": "2025-10-11T04:47:10-0500",
    "updated_time": "2025-10-28T04:16:17-0500"
  }
}
```

### 2. Start (Activate) Ad

Activate a paused ad:

```bash
curl -X POST "http://localhost:8000/ad-control/start" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189"
  }'
```

### 3. Stop (Pause) Ad

Pause an active ad:

```bash
curl -X POST "http://localhost:8000/ad-control/stop" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189"
  }'
```

### 4. Update Ad Name

Change the name of an ad:

```bash
curl -X POST "http://localhost:8000/ad-control/update-name" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "ad_id": "120234815168290189",
    "new_name": "优化后的广告名称"
  }'
```

### 5. Get AdSet Budget

Query the budget settings for an ad set (budgets are set at the ad set level):

```bash
curl -X GET "http://localhost:8000/ad-control/adset/budget?ad_account_id=1279567647104057&adset_id=120234814836800189" \
  -H "X-User-Id: user123"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "adset_id": "120234814836800189",
    "name": "Global $1/day",
    "daily_budget": "100",
    "lifetime_budget": "0",
    "budget_remaining": "100"
  }
}
```

**Note:** Budget amounts are in cents (100 cents = $1.00)

### 6. Update AdSet Budget

Modify the budget for an ad set:

**Update daily budget to $5.00:**
```bash
curl -X POST "http://localhost:8000/ad-control/adset/update-budget" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "adset_id": "120234814836800189",
    "daily_budget": 500
  }'
```

**Update lifetime budget to $100.00:**
```bash
curl -X POST "http://localhost:8000/ad-control/adset/update-budget" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "ad_account_id": "1279567647104057",
    "adset_id": "120234814836800189",
    "lifetime_budget": 10000
  }'
```

### 7. Get Account Activities (Activity Log / Audit Trail)

Retrieve historical modification records for your ad account. This endpoint provides an audit trail of all changes made to ads, ad sets, and campaigns.

**Get all account activities (last 100 records):**
```bash
curl -X GET "http://localhost:8000/ad-control/activities?ad_account_id=1279567647104057&limit=100" \
  -H "X-User-Id: user123"
```

**Get activities for a specific ad:**
```bash
curl -X GET "http://localhost:8000/ad-control/activities?ad_account_id=1279567647104057&object_id=120234815168290189&limit=50" \
  -H "X-User-Id: user123"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_activities": 15,
    "activities": [
      {
        "event_time": "2025-10-29T10:30:00+0000",
        "actor_name": "John Doe",
        "event_type": "update",
        "object_type": "ad",
        "object_id": "120234815168290189",
        "object_name": "Ad global_engagement_$1",
        "extra_data": {
          "field": "status",
          "old_value": "ACTIVE",
          "new_value": "PAUSED"
        }
      }
    ]
  }
}
```

**Common Use Cases:**
- **Audit Trail:** Track who changed what and when
- **Debug Changes:** Find out why an ad was paused or modified
- **Compliance:** Maintain records of all ad account modifications
- **Analytics:** Analyze patterns in ad management activities

**Query Parameters:**
| Parameter | Required | Type | Description | Example |
|-----------|----------|------|-------------|---------|
| `ad_account_id` | Yes | string | Ad account ID (with or without `act_` prefix) | `1279567647104057` |
| `object_id` | No | string | Filter by specific object ID (ad, adset, or campaign) | `120234815168290189` |
| `limit` | No | int | Maximum number of activities to retrieve (default: 100, max: 10000) | `100` |

**Activity Fields:**
- `event_time` - When the change occurred (ISO 8601 timestamp)
- `actor_name` - Who made the change (person or system)
- `event_type` - Type of action (create, update, delete, etc.)
- `object_type` - What was changed (ad, adset, campaign)
- `object_id` - ID of the modified object
- `object_name` - Name of the modified object
- `extra_data` - Additional metadata about the change (field, old_value, new_value, etc.)

### Ad Status Reference

**Configured Status:**
- `ACTIVE` - Ad is activated
- `PAUSED` - Ad is paused
- `ARCHIVED` - Ad is archived
- `DELETED` - Ad is deleted

**Effective Status:**
Considers parent campaign/adset status:
- `ACTIVE` - Ad is actively running
- `PAUSED` - Ad is paused
- `CAMPAIGN_PAUSED` - Campaign is paused
- `ADSET_PAUSED` - Ad set is paused
- `PENDING_REVIEW` - Awaiting review
- `DISAPPROVED` - Rejected by review
- `WITH_ISSUES` - Has issues preventing delivery

### Python SDK Example

```python
import asyncio
from api.services.ad_control_service import AdControlService
from utils.db import init_db, close_db

async def manage_ads():
    await init_db()

    ad_account_id = "1279567647104057"
    ad_id = "120234815168290189"

    # Get status
    status = await AdControlService.get_ad_status(ad_account_id, ad_id)
    print(f"Ad Status: {status['configured_status']}")

    # Start ad
    result = await AdControlService.start_ad(ad_account_id, ad_id)
    print(f"Started: {result['message']}")

    # Stop ad
    result = await AdControlService.stop_ad(ad_account_id, ad_id)
    print(f"Stopped: {result['message']}")

    # Update name
    result = await AdControlService.update_ad_name(
        ad_account_id, ad_id, "New Ad Name"
    )
    print(f"Renamed: {result['message']}")

    # Get account activities
    activities = await AdControlService.get_account_activities(
        ad_account_id, limit=10
    )
    print(f"Total activities: {activities['total_activities']}")
    for activity in activities['activities']:
        print(f"  {activity['event_time']} - {activity['event_type']} "
              f"on {activity['object_type']} by {activity['actor_name']}")

    await close_db()

asyncio.run(manage_ads())
```

### Running Test Scripts

Test the ad control operations:

```bash
# Test all ad control operations (status, start, stop, update name, budget)
python tests/test_ad_control.py

# Test activities API (service layer)
python tests/test_activities.py

# Test activities API (HTTP endpoints)
python tests/test_activities_http.py
```

## Next Steps

- Explore the interactive API docs at `/docs`
- Check out the full project documentation in `CLAUDE.md`
- Build features on top of the insights data
- Integrate with ML models for ad optimization
- Develop rule-based automation using ad control operations

## Support

For issues and questions, refer to the main project documentation in `CLAUDE.md`.
