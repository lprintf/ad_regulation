"""
Shared MongoDB collection definitions for migration utilities.
"""

from __future__ import annotations

from utils.db import (
    ADAccountDocument,
    AdEntityNamesDocument,
    BIUserAdAccountLink,
    FbAppAuthDocument,
    FbAppTokenInfoDocument,
    InsightsDailyDocument,
    InsightsSyncLogDocument,
    InsightsSyncStateDocument,
    RuleBindingDocument,
    RuleDefinitionDocument,
    RuleExecutionLogDocument,
)


def _resolve_collection_name(document_cls) -> str:
    settings = getattr(document_cls, "Settings", None)
    if settings and getattr(settings, "name", None):
        return settings.name  # type: ignore[attr-defined]
    return document_cls.__name__


CORE_DOCUMENTS = [
    FbAppTokenInfoDocument,
    FbAppAuthDocument,
    ADAccountDocument,
    BIUserAdAccountLink,
    RuleDefinitionDocument,
    RuleBindingDocument,
    InsightsDailyDocument,
    InsightsSyncStateDocument,
    AdEntityNamesDocument,
]

ADDITIONAL_COLLECTIONS = {
    "scheduler_state",
}

INSIGHTS_SYNC_LOG_COLLECTION = _resolve_collection_name(InsightsSyncLogDocument)

LOG_COLLECTIONS_FULL = {
    INSIGHTS_SYNC_LOG_COLLECTION,
}

LOG_COLLECTIONS_LIMITED: set[str] = set()

COLLECTION_NAMES = sorted(
    {_resolve_collection_name(doc) for doc in CORE_DOCUMENTS}
    | ADDITIONAL_COLLECTIONS
    | LOG_COLLECTIONS_FULL
    | LOG_COLLECTIONS_LIMITED
)


def iter_collection_names() -> list[str]:
    return list(COLLECTION_NAMES)

