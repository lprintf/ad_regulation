"""
Utility for migrating the project's MongoDB collections without relying on
`mongodump`. Uses PyMongo to stream documents from a source database into a
target database, skipping log collections by default.

Example:
    uv run python scripts/db_migration/mongo_copy_collections.py \
        --source-uri mongodb://user:pass@old-host:27017/fb_monitor?authSource=admin \
        --target-uri mongodb://user:pass@new-host:27017/fb_monitor?authSource=admin \
        --drop-target
"""

from __future__ import annotations

import argparse

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConfigurationError

from scripts.db_migration.mongo_collections import (
    COLLECTION_NAMES,
    LOG_COLLECTIONS_LIMITED,
)


def _copy_indexes(source: Collection, target: Collection) -> None:
    for index in source.list_indexes():
        name = index.get("name")
        if name == "_id_":
            continue
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
        target.create_index(keys, name=name, **kwargs)


def copy_collection(
    source: Collection,
    target: Collection,
    *,
    batch_size: int,
    drop_target: bool,
    limit_latest: int | None = None,
) -> int:
    if drop_target:
        target.drop()

    copied = 0
    batch: list[dict] = []
    cursor = source.find({}, no_cursor_timeout=True)
    if limit_latest:
        cursor = cursor.sort([("_id", -1)]).limit(limit_latest)
    cursor = cursor.batch_size(batch_size)
    try:
        for document in cursor:
            batch.append(document)
            if len(batch) >= batch_size:
                target.insert_many(batch, ordered=False)
                copied += len(batch)
                batch.clear()
        if batch:
            target.insert_many(batch, ordered=False)
            copied += len(batch)
    finally:
        cursor.close()

    _copy_indexes(source, target)
    return copied


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy MongoDB collections without mongodump/mongorestore."
    )
    parser.add_argument("--source-uri", required=True, help="MongoDB URI for the source DB")
    parser.add_argument("--target-uri", required=True, help="MongoDB URI for the target DB")
    parser.add_argument(
        "--source-db",
        default=None,
        help="Source database name (defaults to database in URI)",
    )
    parser.add_argument(
        "--target-db",
        default=None,
        help="Target database name (defaults to database in URI)",
    )
    parser.add_argument(
        "--drop-target",
        action="store_true",
        help="Drop target collections before inserting (recommended for clean migrations).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of documents to insert per batch.",
    )
    return parser


def resolve_collections() -> list[str]:
    return list(COLLECTION_NAMES)


def _get_database(client: MongoClient, explicit_name: str | None) -> Database:
    if explicit_name:
        return client[explicit_name]
    try:
        return client.get_default_database()
    except ConfigurationError as exc:
        raise SystemExit(
            "Mongo URI must include a default database or provide --source-db/--target-db."
        ) from exc


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    source_client = MongoClient(args.source_uri)
    target_client = MongoClient(args.target_uri)

    source_db = _get_database(source_client, args.source_db)
    target_db = _get_database(target_client, args.target_db)

    collections = resolve_collections()
    for name in collections:
        print(f"Copying collection '{name}'...")
        source_col = source_db[name]
        target_col = target_db[name]
        if name in LOG_COLLECTIONS_LIMITED:
            limit_latest = 10
        else:
            limit_latest = None
        count = copy_collection(
            source_col,
            target_col,
            batch_size=args.batch_size,
            drop_target=args.drop_target,
            limit_latest=limit_latest,
        )
        print(f"  -> Copied {count} documents.")

    print("Migration completed.")


if __name__ == "__main__":
    main()

