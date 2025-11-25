"""
Data transformation service for insights.

Handles conversion between different data formats:
- DataFrame to insights list
- Database documents to insights
- Metric normalization
"""

import math
from typing import Any

from utils.db import InsightsDailyDocument
from utils.account_id import normalize_account_id


class TransformService:
    """Service for transforming insights data between formats."""

    @staticmethod
    def df_to_insights_list(df) -> list[dict[str, Any]]:
        """
        Convert DataFrame to list of insight dictionaries.

        TODO: Extract from insights_service.py:_df_to_insights_list()
        """
        raise NotImplementedError("To be migrated from insights_service.py")

    @staticmethod
    def document_to_insight(doc: InsightsDailyDocument) -> dict[str, Any]:
        """
        Convert InsightsDailyDocument to insight dictionary.

        TODO: Extract from insights_service.py:_document_to_insight()
        """
        raise NotImplementedError("To be migrated from insights_service.py")
