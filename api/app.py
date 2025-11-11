"""
FastAPI application entry point.
Automated Facebook advertising regulation system.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies.database import close_db_connection
from api.models.responses import ErrorDetail, ErrorResponse
from api.routers import (
    ad_accounts,
    ad_control,
    fb_auth,
    health,
    insights,
    predictions,
    rules,
    scheduler,
)
from api.services.rule_engine_service import RuleEngineService
from api.services.rule_scheduler import start_rule_scheduler, stop_rule_scheduler
from api.services.insights_sync_scheduler import (
    start_insights_sync_scheduler,
    stop_insights_sync_scheduler,
)
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
    await RuleEngineService.ensure_demo_rule_seed()
    print("✓ Demo rule seeded (if missing)")
    await start_rule_scheduler()
    print("✓ Rule scheduler started")
    await start_insights_sync_scheduler()
    print("✓ Insights sync scheduler started")

    yield

    # Shutdown: Close database connection
    await stop_rule_scheduler()
    print("✓ Rule scheduler stopped")
    await stop_insights_sync_scheduler()
    print("✓ Insights sync scheduler stopped")
    await close_db_connection()
    print("✓ Database connection closed")


# Create FastAPI application
app = FastAPI(
    title="Ad Regulation API",
    description="Automated Facebook advertising regulation system with ML-powered evaluation",
    version="0.1.0",
    lifespan=lifespan,
)

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(insights.router)
app.include_router(predictions.router)
app.include_router(ad_control.router)
app.include_router(rules.router)
app.include_router(scheduler.router)
app.include_router(fb_auth.router)


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
