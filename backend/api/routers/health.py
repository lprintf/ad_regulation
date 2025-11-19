"""
Health check and system info router.
"""

from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from api.dependencies.database import get_database
from api.models.responses import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check(db: AsyncDatabase = Depends(get_database)) -> HealthResponse:
    """
    Health check endpoint to verify service and database status.

    Returns:
        HealthResponse: Service health status
    """
    # Test database connection
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(status="healthy", version="0.1.0", database=db_status)
