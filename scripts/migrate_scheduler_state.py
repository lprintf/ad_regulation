"""
One-off helper to migrate scheduler state from the legacy JSON file
(`output/scheduler_state.json`) into the new MongoDB collection.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.operations import ReplaceOne

from config import MONGODB_DB_NAME, MONGODB_URL

LEGACY_STATE_PATH = Path(
    os.getenv("SCHEDULER_STATE_PATH", "output/scheduler_state.json")
)
COLLECTION_NAME = "scheduler_state"


def _load_legacy_payload() -> Dict[str, Dict[str, Any]]:
    if not LEGACY_STATE_PATH.exists():
        print(f"No legacy scheduler file found at {LEGACY_STATE_PATH}")
        return {}

    try:
        with LEGACY_STATE_PATH.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
            if isinstance(payload, dict):
                return {
                    ns: value
                    for ns, value in payload.items()
                    if isinstance(value, dict)
                }
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Legacy scheduler state file is corrupted: {exc}"
        ) from exc
    return {}


def migrate() -> None:
    payload = _load_legacy_payload()
    if not payload:
        print("No scheduler state entries to migrate.")
        return

    client = MongoClient(MONGODB_URL)
    collection = client[MONGODB_DB_NAME][COLLECTION_NAME]
    collection.create_index("namespace", unique=True)

    operations: list[ReplaceOne] = []
    now = datetime.now(timezone.utc)
    for namespace, namespace_payload in payload.items():
        operations.append(
            ReplaceOne(
                {"namespace": namespace},
                {
                    "namespace": namespace,
                    "payload": namespace_payload,
                    "updated_at": now,
                },
                upsert=True,
            )
        )

    if not operations:
        print("No valid scheduler state documents detected.")
        return

    try:
        result = collection.bulk_write(operations, ordered=False)
    except PyMongoError as exc:
        raise RuntimeError(f"Failed to persist scheduler state: {exc}") from exc

    backup_path = LEGACY_STATE_PATH.with_suffix(LEGACY_STATE_PATH.suffix + ".bak")
    LEGACY_STATE_PATH.replace(backup_path)

    upserts = result.upserted_count
    modified = result.modified_count
    print(
        f"Migrated scheduler state to MongoDB (upserts={upserts}, modified={modified})."
    )
    print(f"Legacy file moved to {backup_path}")


if __name__ == "__main__":
    migrate()
