# InsightsService Refactoring Plan

## Current State
- Single file: `api/services/insights_service.py` (1812 lines)
- 22+ methods mixing multiple responsibilities
- Difficult to test and maintain

## Goals
1. Separate concerns by responsibility
2. Improve testability
3. Make code easier to understand and maintain
4. Prepare for DTO integration

## Proposed Structure

```
api/services/insights/
├── __init__.py                      # Public API facade
├── query_service.py                 # Main query orchestration (FACADE)
├── data_source_service.py           # Data fetching (MongoDB, Redis, FB API)
├── aggregation_service.py           # Level-based aggregation + entity names
├── transform_service.py             # Data format transformations
├── async_job_service.py             # Async job management
└── utils.py                         # Shared utilities
```

## Service Responsibilities

### 1. `query_service.py` (Main Facade)
**Purpose**: High-level query orchestration, composes other services

**Public Methods**:
- `query_realtime()` - Hybrid MongoDB + Facebook API
- `query_from_last_gap()` - Auto-fill gap since last sync
- `query_hybrid()` - Database + realtime gap combination
- `query_mongo_only()` - Pure MongoDB historical query
- `query_mongo_redis()` - MongoDB + Redis hybrid cache

**Dependencies**: All other services

### 2. `data_source_service.py`
**Purpose**: Fetch data from different sources

**Methods**:
- `fetch_from_mongodb(account_id, since, until, filters)` → list[dict]
- `fetch_from_redis(account_id, since, until)` → list[dict]
- `fetch_from_facebook_api(account_id, params)` → list[dict]
- `fetch_facebook_async_job(job_id)` → list[dict]

**Internal Helpers**:
- `_get_insights_from_redis_range()`
- `_fetch_insights_sync()`

### 3. `aggregation_service.py`
**Purpose**: Aggregate data by level and attach entity names

**Methods**:
- `aggregate_by_level(records, level, account_id)` → list[dict]
- `attach_entity_names(records, level, account_id)` → list[dict]

**Internal Helpers**:
- `_aggregate_records_for_level()`
- `_attach_entity_names()`
- `_load_names()`
- `_sum_numeric_expression()`

### 4. `transform_service.py`
**Purpose**: Convert between data formats

**Methods**:
- `df_to_insights_list(df)` → list[dict]
- `document_to_insight(doc)` → dict
- `normalize_insight_record(raw)` → dict

**Internal Helpers**:
- `_normalize_optional()`
- `_safe_get_metric()`

### 5. `async_job_service.py`
**Purpose**: Facebook async job management

**Methods**:
- `create_async_job(account_id, params)` → dict
- `check_job_status(account_id, job_id)` → dict
- `get_job_result(account_id, job_id)` → list[dict]

### 6. `utils.py`
**Purpose**: Shared utilities and helpers

**Functions**:
- Date: `validate_date()`, `parse_date()`, `normalize_state_date()`
- Filtering: `resolve_object_filter()`, `filter_insights_by_objects()`
- Caching: `build_cache_key()`, `get_from_cache()`, `set_to_cache()`
- Keys: `key_for_insight()`, `normalize_cache_key_fields()`

## Migration Steps

### Phase 1: Create Structure ✓
1. Create `api/services/insights/` directory
2. Create empty service files with docstrings
3. Create `__init__.py` with facade pattern

### Phase 2: Extract Utilities
1. Move utility functions to `utils.py`
2. Update imports
3. Test

### Phase 3: Extract Data Sources
1. Move data fetching methods to `data_source_service.py`
2. Update imports
3. Test

### Phase 4: Extract Transformations
1. Move transformation methods to `transform_service.py`
2. Update imports
3. Test

### Phase 5: Extract Aggregation
1. Move aggregation methods to `aggregation_service.py`
2. Update imports
3. Test

### Phase 6: Extract Async Jobs
1. Move async job methods to `async_job_service.py`
2. Update imports
3. Test

### Phase 7: Create Query Service Facade
1. Move high-level query methods to `query_service.py`
2. Compose using extracted services
3. Update imports
4. Test

### Phase 8: Update Routers
1. Update router imports to use new services
2. Test all endpoints
3. Remove old `insights_service.py`

## Testing Strategy

After each phase:
1. Run health check: `GET /health`
2. Test insights query: `GET /insights?ad_account_id=...&since=...&until=...`
3. Verify no regressions

## Notes

- **Backward Compatibility**: Keep old imports working during migration
- **No Behavior Changes**: Only structural changes, no logic modifications
- **Gradual Migration**: One service at a time, test after each step
- **DTO Integration**: Will happen naturally during this refactoring

## Current Status (2025-11-24)

- ✅ Planning complete
- 🔄 **Next**: Phase 1 - Create directory structure
