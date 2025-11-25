"""
Insights service package - Modular insights query and management.

This package provides a clean separation of concerns for Facebook Ads
Insights data operations:

- **QueryService**: Main facade for high-level queries
- **DataSourceService**: Fetch data from MongoDB, Redis, Facebook API
- **AggregationService**: Aggregate by level and attach entity names
- **TransformService**: Convert between data formats
- **AsyncJobService**: Manage Facebook async jobs
- **utils**: Shared utilities

Example usage:
    from api.services.insights import InsightsService

    # Main facade (backward compatible)
    result = await InsightsService.query_realtime(account_id, since, until)

    # Or use specific services directly
    from api.services.insights import QueryService
    result = await QueryService.query_realtime(account_id, since, until)
"""

# Facade class for backward compatibility
from api.services.insights.query_service import QueryService as InsightsService

# Individual services for direct access
from api.services.insights.query_service import QueryService
from api.services.insights.data_source_service import DataSourceService
from api.services.insights.aggregation_service import AggregationService
from api.services.insights.transform_service import TransformService
from api.services.insights.async_job_service import AsyncJobService

__all__ = [
    "InsightsService",  # Main facade (backward compatible)
    "QueryService",
    "DataSourceService",
    "AggregationService",
    "TransformService",
    "AsyncJobService",
]
