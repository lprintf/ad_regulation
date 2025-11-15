"""
Persistence utilities for APScheduler task configuration/state.

State is now stored in MongoDB instead of local JSON files so that scheduler
configuration survives container restarts and scales across instances.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from config import MONGODB_DB_NAME, MONGODB_URL

RULE_SCHEDULER_NAMESPACE = "rule_scheduler"
INSIGHTS_SCHEDULER_NAMESPACE = "insights_scheduler"

_STATE_LOCK = Lock()
_COLLECTION_NAME = "scheduler_state"
_mongo_client: MongoClient | None = None
_collection: Collection | None = None
_indexes_ensured = False

logger = logging.getLogger(__name__)


def _get_collection() -> Collection:
    """
    Lazily initialize the Mongo collection used to persist scheduler state.
    """
    global _mongo_client, _collection, _indexes_ensured
    if _collection is None:
        _mongo_client = MongoClient(MONGODB_URL)
        _collection = _mongo_client[MONGODB_DB_NAME][_COLLECTION_NAME]
    if not _indexes_ensured:
        try:
            _collection.create_index("namespace", unique=True)
        except PyMongoError as exc:  # pragma: no cover - defensive log
            logger.error("Failed to ensure scheduler_state index: %s", exc)
            raise
        _indexes_ensured = True
    return _collection


def load_namespace(namespace: str) -> Dict[str, Any]:
    """
    Fetch persisted scheduler payload for the provided namespace.
    """
    try:
        with _STATE_LOCK:
            document = _get_collection().find_one(
                {"namespace": namespace}, projection={"_id": 0, "payload": 1}
            )
    except PyMongoError as exc:
        logger.error("Failed to load scheduler state for %s: %s", namespace, exc)
        return {}

    payload = (document or {}).get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def save_namespace(namespace: str, payload: Dict[str, Any]) -> None:
    """
    Persist scheduler payload for the provided namespace.
    """
    if not isinstance(payload, dict):
        raise ValueError("Scheduler payload must be a dict")

    document = {
        "namespace": namespace,
        "payload": dict(payload),
        "updated_at": datetime.now(timezone.utc),
    }

    try:
        with _STATE_LOCK:
            _get_collection().replace_one(
                {"namespace": namespace},
                document,
                upsert=True,
            )
    except PyMongoError as exc:
        logger.error("Failed to persist scheduler state for %s: %s", namespace, exc)
        raise
