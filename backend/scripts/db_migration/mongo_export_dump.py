"""
Dump project MongoDB collections to newline-delimited JSON files using the
connection info defined in config.py. Useful for offline transfers.
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


def _ensure_dump_dir() -> Path:
    DEFAULT_DUMP_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DUMP_DIR


def _dump_collection(db, collection_name: str, dump_dir: Path) -> int:
    collection = db[collection_name]
    output_path = dump_dir / f"{collection_name}.jsonl"
    count = 0
    with output_path.open("w", encoding="utf-8") as stream:
        cursor = collection.find({}, no_cursor_timeout=True).batch_size(BATCH_SIZE)
        try:
            for document in cursor:
                stream.write(json_util.dumps(document))
                stream.write("\n")
                count += 1
        finally:
            cursor.close()
    return count


def _dump_indexes(db, dump_dir: Path) -> None:
    index_map: dict[str, list[dict]] = {}
    for collection_name in COLLECTION_NAMES:
        indexes = []
        for index in db[collection_name].list_indexes():
            if index.get("name") == "_id_":
                continue
            indexes.append(index)
        if indexes:
            index_map[collection_name] = indexes
    if index_map:
        (dump_dir / "indexes.json").write_text(
            json_util.dumps(index_map, indent=2),
            encoding="utf-8",
        )


def main() -> None:
    dump_dir = _ensure_dump_dir()
    client = MongoClient(MONGODB_URL)
    db = client[MONGODB_DB_NAME]

    for name in COLLECTION_NAMES:
        print(f"Exporting collection '{name}'...")
        count = _dump_collection(db, name, dump_dir)
        print(f"  -> Dumped {count} documents to {dump_dir / (name + '.jsonl')}")

    _dump_indexes(db, dump_dir)
    print(f"Index metadata saved to {dump_dir / 'indexes.json'}")
    print("Mongo dump completed.")


if __name__ == "__main__":
    main()

