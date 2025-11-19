"""
Database dependencies for FastAPI routes.
Provides typed access to the shared MongoDB connection.
"""

from typing import AsyncGenerator

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from config import MONGODB_DB_NAME, MONGODB_URL

# Global MongoDB client instance
_mongo_client: AsyncMongoClient | None = None


async def get_database() -> AsyncGenerator[AsyncDatabase, None]:
    """
    Dependency that provides MongoDB database instance.

    Yields:
        AsyncDatabase: MongoDB database instance
    """
    global _mongo_client

    if _mongo_client is None:
        _mongo_client = AsyncMongoClient(MONGODB_URL)

    try:
        yield _mongo_client[MONGODB_DB_NAME]
    finally:
        # Connection cleanup handled by lifespan events
        pass


async def close_db_connection() -> None:
    """Close MongoDB connection. Called during app shutdown."""
    global _mongo_client
    if _mongo_client:
        await _mongo_client.close()
        _mongo_client = None
