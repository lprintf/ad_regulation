# DTO Layer Architecture

## Purpose

The DTO (Data Transfer Object) layer provides type-safe data structures for transferring data between service and router layers. This separates internal data representation from external API contracts.

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│         API Layer (FastAPI Routers)         │
│  - Handles HTTP requests/responses          │
│  - Uses api/models/ (Pydantic models)       │
│  - External API contracts                   │
└──────────────────┬──────────────────────────┘
                   │
          ┌────────▼────────┐
          │    Mappers      │  (api/mappers/)
          │  DTO ↔ Models   │
          └────────┬────────┘
                   │
┌──────────────────▼──────────────────────────┐
│        Service Layer (Business Logic)       │
│  - Returns DTOs (api/dto/)                  │
│  - Type-safe internal data structures       │
│  - Independent of API contract changes      │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│      Data Layer (Database, External APIs)   │
│  - MongoDB, Redis, Facebook API             │
│  - Returns raw data (dicts, documents)      │
└─────────────────────────────────────────────┘
```

## Benefits

1. **Type Safety**: Services return typed DTOs instead of `dict[str, Any]`
2. **Separation of Concerns**: Internal data models independent from API contracts
3. **Easier Refactoring**: Change internal structure without breaking API
4. **Better Testing**: Mock DTOs instead of complex dictionaries
5. **Clear Documentation**: DTO fields document service layer contracts

## Directory Structure

```
api/
├── dto/                    # Internal data transfer objects
│   ├── __init__.py
│   └── insights.py         # Insights domain DTOs
├── mappers/                # Convert DTOs ↔ API models
│   └── __init__.py
├── models/                 # External API contracts (Pydantic)
│   └── insights.py
├── services/               # Business logic (returns DTOs)
│   └── insights_service.py
└── routers/                # FastAPI endpoints
    └── insights.py
```

## Usage Example

### 1. Define DTO (Internal)

```python
# api/dto/insights.py
from dataclasses import dataclass

@dataclass
class InsightsResultDTO:
    insights: list[InsightRecordDTO]
    date_range: DateRangeDTO
    last_synced_date: str | None = None

    @property
    def total_records(self) -> int:
        return len(self.insights)
```

### 2. Service Returns DTO

```python
# api/services/insights_service.py
from api.dto import InsightsResultDTO

class InsightsService:
    @staticmethod
    async def query_insights(...) -> InsightsResultDTO:
        # Business logic
        return InsightsResultDTO(
            insights=records,
            date_range=DateRangeDTO(since, until),
            last_synced_date=last_synced,
        )
```

### 3. Router Uses Mapper

```python
# api/routers/insights.py
from api.mappers import insights_result_dto_to_response

@router.get("", response_model=SuccessResponse[InsightsResponse])
async def query_insights(...):
    # Call service (returns DTO)
    dto = await InsightsService.query_insights(...)

    # Convert DTO to API response format
    response_data = insights_result_dto_to_response(dto)

    return SuccessResponse(data=response_data)
```

## Migration Strategy

**Current Status**: DTO layer structure established, pattern documented

**Migration Plan**:
1. ✅ Create DTO models (`api/dto/insights.py`)
2. ✅ Create mappers (`api/mappers/`)
3. ✅ Document architecture (this file)
4. 🔄 **Next**: Migrate services during service splitting (Task #5)
   - Split `InsightsService` into sub-services
   - Each sub-service returns DTOs
   - Update routers to use mappers
5. 📋 Clean up: Remove old dict-based service methods

## Design Principles

### DTOs should be:
- **Immutable** where possible (use `@dataclass(frozen=True)`)
- **Simple** - just data, minimal logic
- **Independent** - not coupled to database models or API models
- **Typed** - use type hints for all fields

### Mappers should:
- **Be pure functions** - no side effects
- **Handle all conversions** - DTO ↔ API models
- **Be in one direction** - typically DTO → API model (response)
- **Live in `api/mappers/`** - separate from DTOs and models

## Current State (2025-11-24)

### Implemented:
- ✅ DTO structure (`api/dto/`)
- ✅ Insights domain DTOs
- ✅ Mapper utilities
- ✅ Documentation

### Pending:
- 🔄 Service layer migration (Task #5: Split InsightsService)
- 🔄 Router updates to use mappers
- 🔄 Create DTOs for other domains (ad_control, predictions, etc.)

## Notes

- **Transition Period**: During migration, `InsightsResultDTO.from_service_dict()` provides bridge from old dict-based services
- **Backward Compatibility**: Old dict-based services still work, gradual migration
- **Service Splitting**: Full DTO adoption will happen during InsightsService refactoring (Task #5)
