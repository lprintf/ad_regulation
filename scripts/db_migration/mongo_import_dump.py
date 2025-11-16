"""
Restore MongoDB collections from files created by mongo_export_dump.py using
connection info from config.py. Drops target collections before inserting.
"""

from __future__ import annotations

import os
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

from config import MONGODB_DB_NAME, MONGODB_URL
from scripts.db_migration.mongo_collections import COLLECTION_NAMES

DEFAULT_DUMP_DIR = Path(os.getenv("MONGO_DUMP_DIR", "output/mongo_dump"))
BATCH_SIZE = 1000


def _load_indexes(dump_dir: Path) -> dict[str, list[dict]]:
    index_file = dump_dir / "indexes.json"
    if not index_file.exists():
        return {}
    raw = index_file.read_text(encoding="utf-8")
    return json_util.loads(raw)


def _restore_collection(db, collection_name: str, dump_dir: Path, indexes: dict[str, list[dict]]) -> int:
    file_path = dump_dir / f"{collection_name}.jsonl"
    if not file_path.exists():
        print(f"  ! Dump file {file_path} not found, skipping.")
        return 0

    collection = db[collection_name]
    collection.drop()

    inserted = 0
    batch: list[dict] = []
    with file_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            batch.append(json_util.loads(line))
            if len(batch) >= BATCH_SIZE:
                collection.insert_many(batch, ordered=False)
                inserted += len(batch)
                batch.clear()
    if batch:
        collection.insert_many(batch, ordered=False)
        inserted += len(batch)

    for index in indexes.get(collection_name, []):
        name = index.get("name")
        keys = list(index["key"].items())
        kwargs = {}
        for field in (
            "unique",
            "sparse",
            "expireAfterSeconds",
            "partialFilterExpression",
            "collation",
        ):
            if field in index:
                kwargs[field] = index[field]
        collection.create_index(keys, name=name, **kwargs)

    return inserted


def main() -> None:
    dump_dir = DEFAULT_DUMP_DIR
    if not dump_dir.exists():
        raise SystemExit(f"Dump directory {dump_dir} does not exist.")

    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DB_NAME]

    index_map = _load_indexes(dump_dir)

    for name in COLLECTION_NAMES:
        print(f"Importing collection '{name}'...")
        count = _restore_collection(db, name, dump_dir, index_map)
        print(f"  -> Restored {count} documents.")

    print("Mongo import completed.")


if __name__ == "__main__":
    main()

