"""
Models shared by scheduler management endpoints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SchedulerNamespace(str, Enum):
    """Scheduler namespaces supported by the API."""

    RULES = "rules"
    INSIGHTS = "insights"
    REALTIME_CACHE = "realtime_cache"


class SchedulerTaskResponse(BaseModel):
    """Serialized scheduler task metadata with namespace tag."""

    namespace: SchedulerNamespace
    id: str
    name: str
    cron: str
    status: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    average_latency_ms: float | None = None
    max_latency_ms: float | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SchedulerTaskUpdateRequest(BaseModel):
    """Payload for updating scheduler task cron expression or metadata."""

    cron: str | None = Field(
        default=None,
        description="APScheduler cron expression in `cron[...]` format",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Custom scheduler task configuration payload",
    )

