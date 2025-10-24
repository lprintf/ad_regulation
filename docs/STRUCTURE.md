# Project Structure

```
ad_regulation/
│
├── api/                          # FastAPI application layer
│   ├── __init__.py
│   ├── app.py                   # Main FastAPI application with lifespan management
│   │
│   ├── routers/                 # API route handlers
│   │   ├── __init__.py
│   │   ├── health.py           # Health check endpoints
│   │   └── ad_accounts.py      # Ad account management endpoints
│   │
│   ├── dependencies/            # Dependency injection modules
│   │   ├── __init__.py
│   │   ├── auth.py             # X-User-Id authentication
│   │   └── database.py         # MongoDB connection management
│   │
│   └── models/                  # Pydantic request/response models
│       ├── __init__.py
│       ├── responses.py        # Standard response formats
│       └── ad_accounts.py      # Ad account models
│
├── baseline/                    # ML pipeline and data processing
│   ├── get_data.py             # Facebook API data fetching
│   ├── data_build.py           # Feature engineering and label generation
│   └── train_tools.py          # Model training utilities
│
├── utils/                       # Core utilities
│   ├── __init__.py
│   ├── db.py                   # Beanie ODM models and database operations
│   ├── fb_api_flyweight_factory.py  # Facebook API client cache
│   ├── insight_tool.py         # Insights extraction and transformation
│   └── schemas/
│       └── ad_account.py       # Pydantic schemas for ad accounts
│
├── docs/                        # Documentation
│   └── API.md                  # API endpoint documentation
│
├── config.py                    # Configuration management
├── run_api.py                  # API server startup script
├── test_api.py                 # API testing script
├── main.py                     # Legacy entry point
│
├── pyproject.toml              # Project dependencies
├── uv.lock                     # Dependency lock file
├── compose.yml                 # Docker Compose (MongoDB, MinIO)
│
├── CLAUDE.md                   # Development guidelines for Claude Code
├── README.md                   # Project documentation
├── .env.example                # Environment variable template
├── .gitignore                  # Git ignore rules
│
└── .venv/                      # Virtual environment (ignored)
```

## Directory Descriptions

### `/api` - FastAPI Application

The web service layer providing REST API endpoints for ad management and evaluation.

- **app.py**: Main application with:
  - Lifespan management (startup/shutdown)
  - Global exception handlers
  - Router registration

- **routers/**: API endpoints organized by domain
  - Thin controllers, business logic in services
  - Uses dependency injection for auth and DB access

- **dependencies/**: Reusable dependency injection functions
  - Authentication via X-User-Id header
  - Database connection pooling

- **models/**: Pydantic models for API contracts
  - Request validation
  - Response serialization
  - Type safety

### `/baseline` - ML Pipeline

Offline data processing and model training components.

- **get_data.py**: Fetches insights from Facebook Ads API
  - Async task management
  - Automatic retry logic
  - Saves to `.feather` files

- **data_build.py**: Feature engineering
  - Lag features (1-7 days)
  - Decay-weighted averages
  - Trend and volatility metrics

- **train_tools.py**: Model training
  - HistGradientBoostingClassifier
  - Ad-level data splitting
  - Threshold optimization

### `/utils` - Core Utilities

Shared utilities used by both API and ML pipeline.

- **db.py**: Database layer
  - Beanie ODM document models
  - Async MongoDB operations
  - Connection lifecycle management

- **fb_api_flyweight_factory.py**: Facebook API client factory
  - Flyweight pattern for caching
  - Credential management from MongoDB

- **insight_tool.py**: Insights processing
  - Atomic metric extraction
  - Data type optimization
  - Helper functions for different breakdowns

### `/docs` - Documentation

API documentation and guides.

## Configuration Files

- **pyproject.toml**: Python project metadata and dependencies
- **compose.yml**: Docker services (MongoDB, MinIO)
- **.env.example**: Environment variable template
- **CLAUDE.md**: Development guidelines for AI assistance

## Scripts

- **run_api.py**: Start development API server with hot reload
- **test_api.py**: Quick API endpoint testing

## Ignored Directories

- **.venv/**: Python virtual environment
- **models/**: Trained model files
- **data/**: Raw and processed data files
- **output/**: Analysis outputs
- **test/**: Test data and temporary files
