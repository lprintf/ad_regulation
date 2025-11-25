"""
Aggregation service for insights.

Handles:
- Level-based aggregation (account, campaign, adset, ad)
- Entity name attachment
- Metric summation
"""

from typing import Any, Dict, Literal, Tuple


class AggregationService:
    """Service for aggregating and enriching insights data."""

    @staticmethod
    def aggregate_by_level(
        records: list[dict[str, Any]],
        target_level: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        """
        Aggregate ad-level records by target level (account, campaign, adset).

        TODO: Extract from insights_service.py:_aggregate_records_for_level()
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    async def attach_entity_names(
        insights_list: list[dict[str, Any]],
        level: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch entity names from database and attach to insights records.

        TODO: Extract from insights_service.py:_attach_entity_names()
        """
        raise NotImplementedError("To be migrated from insights_service.py")
