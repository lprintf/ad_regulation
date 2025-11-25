"""
Shared utilities for insights services.

This module contains helper functions used across multiple insights services:
- Date validation and parsing
- Filtering and object resolution
- Caching utilities  - Key generation

These utilities have no external service dependencies and are pure functions.
"""

import asyncio
from datetime import date, datetime
from typing import Any, Literal


# ===== Date Utilities =====

def validate_date(date_str: str, field_name: str) -> None:
    """
    Validate date string format and value.

    Args:
        date_str: Date string in YYYY-MM-DD format
        field_name: Name of the field for error messages

    Raises:
        ValueError: If date is invalid
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(
            f"Invalid {field_name}: '{date_str}'. Must be a valid date in YYYY-MM-DD format. Error: {e}"
        )


def parse_date(date_str: str, field_name: str) -> date:
    """
    Parse date string and return date object.

    Args:
        date_str: Date string in YYYY-MM-DD format
        field_name: Name of the field for error messages

    Returns:
        date object

    Raises:
        ValueError: If date is invalid
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(
            f"Invalid {field_name}: '{date_str}'. Must be a valid date in YYYY-MM-DD format. Error: {e}"
        )


def normalize_state_date(value: datetime | date | str | None) -> date | None:
    """Normalize various date inputs from sync state into a date object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


# ===== Filtering Utilities =====

OBJECT_LEVEL_TO_FIELD: dict[str, str] = {
    "ad": "ad_id",
    "adset": "adset_id",
    "campaign": "campaign_id",
}


def normalize_filter_ids(values: list[str] | None) -> list[str]:
    """Normalize and deduplicate filter ID list."""
    if not values:
        return []
    normalized = []
    for value in values:
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def resolve_object_filter(
    object_level: str | None, object_ids: list[str] | None
) -> tuple[str, list[str]] | None:
    """
    Resolve object_level and object_ids to (field_name, normalized_ids).

    Returns None if filtering should not be applied.
    """
    if not object_level or not object_ids:
        return None
    field_name = OBJECT_LEVEL_TO_FIELD.get(object_level)
    if not field_name:
        return None
    normalized_ids = normalize_filter_ids(object_ids)
    if not normalized_ids:
        return None
    return field_name, normalized_ids


def filter_insights_by_objects(
    insights_list: list[dict[str, Any]],
    object_level: str | None,
    object_ids: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter insights list by object_level and object_ids."""
    resolved = resolve_object_filter(object_level, object_ids)
    if not resolved:
        return insights_list
    field_name, normalized_ids = resolved
    normalized_set = set(normalized_ids)
    filtered = [
        insight
        for insight in insights_list
        if str(insight.get(field_name) or "").strip() in normalized_set
    ]
    return filtered


# ===== Caching Utilities =====

FROM_LAST_CACHE_TTL_SECONDS = 60
_from_last_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_from_last_cache_lock = asyncio.Lock()


def normalize_cache_key_fields(fields: list[str] | None) -> str:
    """Normalize fields list to cache key component."""
    if not fields:
        return ""
    return ",".join(sorted(fields))


def build_from_last_cache_key(
    *,
    ad_account_id: str,
    until: str,
    level: str,
    time_increment: int | None,
    breakdowns: str | None,
    fields: list[str] | None,
    object_level: str | None,
    object_ids: list[str] | None,
    cache_window_hint: str | None,
) -> str:
    """Build cache key for from_last gap queries."""
    parts = [
        ad_account_id.lower(),
        until,
        level,
        str(time_increment) if time_increment is not None else "null",
        breakdowns or "",
        normalize_cache_key_fields(fields),
        object_level or "",
        ",".join(normalize_filter_ids(object_ids)) if object_ids else "",
        cache_window_hint or "",
    ]
    return "|".join(parts)


async def get_from_last_cache(key: str) -> dict[str, Any] | None:
    """Get cached payload for from_last gap query."""
    if not key:
        return None
    async with _from_last_cache_lock:
        entry = _from_last_cache.get(key)
        if not entry:
            return None
        expires_at, payload = entry
        now = asyncio.get_running_loop().time()
        if expires_at <= now:
            _from_last_cache.pop(key, None)
            return None
        return payload


async def set_from_last_cache(key: str, payload: dict[str, Any]) -> None:
    """Store payload in from_last cache with TTL."""
    if not key:
        return
    ttl = FROM_LAST_CACHE_TTL_SECONDS
    async with _from_last_cache_lock:
        _from_last_cache[key] = (
            asyncio.get_running_loop().time() + ttl,
            payload,
        )


# ===== Key Generation =====

def key_for_insight(insight: dict[str, Any]) -> tuple[str, str]:
    """Generate unique key for an insight record (ad_id, date)."""
    return (insight["ad_id"], insight["date"])
