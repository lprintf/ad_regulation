"""
FastAPI application entry point.
Automated Facebook advertising regulation system.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, APIRouter
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
    user,
)
from api.services.rule_scheduler import start_rule_scheduler, stop_rule_scheduler
from rules import init_rules
from api.services.insights_sync_scheduler import (
    start_insights_sync_scheduler,
    stop_insights_sync_scheduler,
)
from api.services.realtime_cache_scheduler import (
    start_realtime_cache_scheduler,
    stop_realtime_cache_scheduler,
)
from utils.db import init_db
from utils.redis_client import init_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    Supports environment variables:
    - ENABLE_SCHEDULER: true/false (default: false) - 是否启用调度器（入队任务）
    - ENABLE_WORKER: true/false (default: false) - 是否启用 worker（消费任务）
    """
    import os

    # 读取环境变量
    enable_scheduler = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"
    enable_worker = os.getenv("ENABLE_WORKER", "false").lower() == "true"
    worker_concurrency = int(os.getenv("WORKER_CONCURRENCY", "10"))

    # Startup: Initialize database connection
    await init_db()
    print("✓ Database initialized")
    await init_redis()
    print("✓ Redis initialized")

    # 启动调度器（只负责入队任务）
    # 使用 Leader Election 确保只有一个实例执行调度任务
    if enable_scheduler:
        from api.services.scheduler_leader_election import start_leader_election

        # 启动 Leader 选举（所有实例都参与）
        await start_leader_election()
        print("✓ Leader election started")

        # 初始化规则系统（发现并注册所有内置规则）
        init_rules()
        print("✓ Rules initialized from registry")
        await start_rule_scheduler()
        print("✓ Rule scheduler started (with leader election)")
        await start_insights_sync_scheduler()
        print("✓ Insights sync scheduler started (with leader election)")
        await start_realtime_cache_scheduler()
        print("✓ Realtime cache scheduler started (with leader election)")
    else:
        print("⊗ Scheduler disabled (ENABLE_SCHEDULER not set)")

    # 启动 worker（消费队列中的任务）
    if enable_worker:
        from api.services.atomic_task_queue import start_sync_queue_workers
        await start_sync_queue_workers(concurrency=worker_concurrency)
        print(f"✓ Task queue workers started (concurrency={worker_concurrency})")
    else:
        print("⊗ Workers disabled (ENABLE_WORKER not set)")

    yield

    # Shutdown: Stop services
    if enable_scheduler:
        from api.services.scheduler_leader_election import stop_leader_election

        await stop_rule_scheduler()
        print("✓ Rule scheduler stopped")
        await stop_insights_sync_scheduler()
        print("✓ Insights sync scheduler stopped")
        await stop_realtime_cache_scheduler()
        print("✓ Realtime cache scheduler stopped")

        # 停止 Leader 选举
        await stop_leader_election()
        print("✓ Leader election stopped")

    if enable_worker:
        from api.services.atomic_task_queue import stop_sync_queue_workers
        await stop_sync_queue_workers()
        print("✓ Task queue workers stopped")

    await close_redis()
    print("✓ Redis connection closed")
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


# Create API router for /api prefix
api_router = APIRouter()

# Include all routers under /api
api_router.include_router(health.router)
api_router.include_router(user.router)
api_router.include_router(ad_accounts.router)
api_router.include_router(insights.router)
api_router.include_router(predictions.router)
api_router.include_router(ad_control.router)
api_router.include_router(rules.router)
api_router.include_router(scheduler.router)
api_router.include_router(fb_auth.router)

# Include the API router with /api prefix
app.include_router(api_router, prefix="/api")


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
