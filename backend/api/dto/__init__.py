"""
Data Transfer Objects (DTOs) for internal service layer.

DTOs define the data structures passed between service layer and routers.
They are separate from API models (api/models/) which define external API contracts.

Purpose:
- Type-safe data transfer between layers
- Internal representation not coupled to external API
- Easier to refactor services without breaking API contracts
"""

from api.dto.insights import (
    InsightMetricsDTO,
    InsightRecordDTO,
    InsightsResultDTO,
    DateRangeDTO,
)

__all__ = [
    "InsightMetricsDTO",
    "InsightRecordDTO",
    "InsightsResultDTO",
    "DateRangeDTO",
]
