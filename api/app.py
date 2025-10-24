"""
FastAPI application entry point.
Automated Facebook advertising regulation system.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.dependencies.database import close_db_connection
from api.models.responses import ErrorDetail, ErrorResponse
from api.routers import ad_accounts, health
from utils.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup: Initialize database connection
    await init_db()
    print("✓ Database initialized")

    yield

    # Shutdown: Close database connection
    await close_db_connection()
    print("✓ Database connection closed")


# Create FastAPI application
app = FastAPI(
    title="Ad Regulation API",
    description="Automated Facebook advertising regulation system with ML-powered evaluation",
    version="0.1.0",
    lifespan=lifespan,
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": exc.errors()},
            )
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    # Log the exception (in production, use proper logging)
    print(f"Unexpected error: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                details={"type": type(exc).__name__},
            )
        ).model_dump(),
    )


# Include routers
app.include_router(health.router)
app.include_router(ad_accounts.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Ad Regulation API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
