# API Documentation

## Overview

The Ad Regulation API provides endpoints for managing Facebook ad accounts and accessing insights data. All endpoints require authentication via the `X-User-Id` header.

## Authentication

All API requests must include the `X-User-Id` header:

```bash
X-User-Id: your_user_id
```

**Example:**
```bash
curl -H "X-User-Id: user123" http://localhost:8000/ad-accounts
```

## Base URL

```
http://localhost:8000
```

## Endpoints

### Health Check

**GET** `/health`

Check API service and database status.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "database": "connected"
}
```

---

### List Ad Accounts

**GET** `/ad-accounts`

Get all ad accounts accessible by the current user.

**Headers:**
- `X-User-Id` (required): User identifier

**Response:**
```json
{
  "success": true,
  "data": {
    "accounts": [
      {
        "id": "act_1243925423619499",
        "name": "My Ad Account",
        "has_auth": true
      }
    ],
    "total": 1
  }
}
```

**Status Codes:**
- `200`: Success
- `401`: Missing or invalid X-User-Id header
- `500`: Internal server error

---

### Get Ad Account

**GET** `/ad-accounts/{account_id}`

Get details of a specific ad account.

**Parameters:**
- `account_id` (path): Ad account ID (with or without `act_` prefix)

**Headers:**
- `X-User-Id` (required): User identifier

**Response:**
```json
{
  "success": true,
  "data": {
    "id": "act_1243925423619499",
    "name": "My Ad Account",
    "has_auth": true
  }
}
```

**Status Codes:**
- `200`: Success
- `401`: Missing or invalid X-User-Id header
- `404`: Ad account not found
- `500`: Internal server error

---

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "additional": "context"
    }
  }
}
```

**Common Error Codes:**
- `VALIDATION_ERROR`: Request validation failed
- `INTERNAL_ERROR`: Unexpected server error

---

## Testing

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# List ad accounts
curl -H "X-User-Id: user123" http://localhost:8000/ad-accounts

# Get specific ad account
curl -H "X-User-Id: user123" http://localhost:8000/ad-accounts/act_1243925423619499
```

### Using Python test script

```bash
python test_api.py
```

### Using Interactive Docs

FastAPI provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Future Endpoints (Planned)

### Ad Insights
- `GET /ad-accounts/{account_id}/insights` - Fetch ad insights data
- `GET /ad-accounts/{account_id}/insights/daily` - Daily aggregated insights

### Ad Evaluation
- `POST /evaluate/ml` - ML-based ad performance evaluation
- `POST /evaluate/rules` - Rule-based ad evaluation
- `POST /evaluate/hybrid` - Combined ML + rules evaluation

### Ad Control
- `POST /ad-accounts/{account_id}/ads/{ad_id}/start` - Start an ad
- `POST /ad-accounts/{account_id}/ads/{ad_id}/stop` - Stop an ad
- `PATCH /ad-accounts/{account_id}/ads/{ad_id}/budget` - Update ad budget

### User Management
- `GET /users/me` - Get current user info
- `GET /users/me/accounts` - Get user's accessible accounts
