# 重构建议和最佳实践

**文档版本**: 1.0
**最后更新**: 2025-12-05

---

## 目标

本文档提供系统化的重构建议，帮助团队提升代码质量、安全性和可维护性。

---

## 1. 立即行动项（1-2周）

### 1.1 实现全局异常处理和结构化日志

**优先级**: CRITICAL
**预计时间**: 3-4 天

#### 步骤

**1) 引入结构化日志库**
```bash
# backend/pyproject.toml
dependencies = [
    # ...
    "structlog>=24.0.0",
    "python-json-logger>=2.0.0"
]
```

**2) 配置日志系统**
```python
# backend/utils/logger.py
import structlog
import logging
from pythonjsonlogger import jsonlogger

def setup_logging():
    """配置结构化日志"""

    # JSON 格式化器
    json_formatter = jsonlogger.JsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s"
    )

    # 配置 structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# backend/api/app.py
from utils.logger import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)
```

**3) 实现全局异常处理器**
```python
# backend/api/middleware/error_handler.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""

    # 生成请求 ID
    request_id = request.headers.get("X-Request-ID", "unknown")

    # 记录异常
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error_message=str(exc),
        exc_info=True
    )

    # 返回统一错误响应
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "request_id": request_id
            }
        }
    )

# backend/api/app.py
from api.middleware.error_handler import global_exception_handler

app.add_exception_handler(Exception, global_exception_handler)
```

**4) 添加请求追踪中间件**
```python
# backend/api/middleware/request_tracking.py
import uuid
from fastapi import Request
import structlog

logger = structlog.get_logger(__name__)

async def request_tracking_middleware(request: Request, call_next):
    """请求追踪中间件"""

    # 生成或获取请求 ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # 绑定到日志上下文
    structlog.contextvars.bind_contextvars(request_id=request_id)

    # 记录请求开始
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host
    )

    # 处理请求
    response = await call_next(request)

    # 记录请求完成
    logger.info(
        "request_completed",
        status_code=response.status_code
    )

    # 添加请求 ID 到响应头
    response.headers["X-Request-ID"] = request_id

    # 清理上下文
    structlog.contextvars.clear_contextvars()

    return response

# backend/api/app.py
app.middleware("http")(request_tracking_middleware)
```

---

### 1.2 配置数据库连接池

**优先级**: CRITICAL
**预计时间**: 1 天

```python
# backend/utils/db.py
from motor.motor_asyncio import AsyncIOMotorClient
from backend.config import MONGODB_URL

def get_mongo_client() -> AsyncIOMotorClient:
    """创建配置好的 MongoDB 客户端"""
    return AsyncIOMotorClient(
        MONGODB_URL,
        # 连接池配置
        maxPoolSize=50,             # 最大连接数
        minPoolSize=10,             # 最小连接数
        maxIdleTimeMS=30000,        # 空闲连接超时 30秒
        connectTimeoutMS=5000,      # 连接超时 5秒
        serverSelectionTimeoutMS=5000,  # 服务器选择超时 5秒
        waitQueueTimeoutMS=5000,    # 等待队列超时 5秒

        # 读写配置
        retryWrites=True,
        w="majority",               # 写关注级别

        # 认证
        authSource="admin",
        authMechanism="SCRAM-SHA-256"
    )

mongo_client = get_mongo_client()
```

---

### 1.3 防御 NoSQL 注入

**优先级**: CRITICAL
**预计时间**: 2 天

**1) 创建白名单验证器**
```python
# backend/utils/validators.py
from typing import Literal
from fastapi import HTTPException

ALLOWED_FILTER_FIELDS = {"ad_id", "adset_id", "campaign_id"}
ALLOWED_LEVELS = {"ad", "adset", "campaign", "account"}
ALLOWED_BREAKDOWNS = {
    "country",
    "hourly_stats_aggregated_by_advertiser_time_zone",
    "hourly_stats_aggregated_by_audience_time_zone"
}

def validate_filter_field(field_name: str):
    """验证聚合字段名"""
    if field_name not in ALLOWED_FILTER_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid filter field: {field_name}. Allowed: {ALLOWED_FILTER_FIELDS}"
        )
    return field_name

def validate_level(level: str) -> Literal["ad", "adset", "campaign", "account"]:
    """验证层级参数"""
    if level not in ALLOWED_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level: {level}. Allowed: {ALLOWED_LEVELS}"
        )
    return level

def validate_breakdown(breakdown: str):
    """验证 breakdown 参数"""
    if breakdown and breakdown not in ALLOWED_BREAKDOWNS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid breakdown: {breakdown}. Allowed: {ALLOWED_BREAKDOWNS}"
        )
    return breakdown
```

**2) 应用到服务层**
```python
# backend/api/services/insights_service.py
from utils.validators import validate_filter_field, validate_level

if object_filter:
    field_name, normalized_ids = object_filter
    field_name = validate_filter_field(field_name)  # ✅ 验证
    match_stage[field_name] = {"$in": normalized_ids}

# 聚合查询
level = validate_level(level)  # ✅ 验证
group_stage = {
    "_id": f"${level}_id",
    # ...
}
```

---

### 1.4 Facebook API 速率限制保护

**优先级**: CRITICAL
**预计时间**: 2 天

**1) 安装 tenacity**
```bash
uv add tenacity
```

**2) 创建重试装饰器**
```python
# backend/utils/facebook_retry.py
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from facebook_business.exceptions import FacebookRequestError
import structlog

logger = structlog.get_logger(__name__)

def is_rate_limit_error(exception):
    """检查是否是速率限制错误"""
    if isinstance(exception, FacebookRequestError):
        error_code = exception.api_error_code()
        return error_code == 80004  # Rate limit
    return False

def facebook_api_retry(
    max_attempts: int = 3,
    min_wait: int = 4,
    max_wait: int = 10
):
    """Facebook API 重试装饰器"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(FacebookRequestError) | retry_if_exception(is_rate_limit_error),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True
    )
```

**3) 应用到 API 调用**
```python
# backend/utils/insight_tool.py
from utils.facebook_retry import facebook_api_retry

@facebook_api_retry(max_attempts=3, min_wait=4, max_wait=10)
def get_insight(adobject, fields, **params):
    """获取 Insights 数据（带重试）"""
    try:
        return adobject.get_insights(
            fields=fields,
            params=params
        )
    except FacebookRequestError as exc:
        logger.error(
            "facebook_api_error",
            error_code=exc.api_error_code(),
            error_message=exc.api_error_message(),
            error_subcode=exc.api_error_subcode()
        )
        raise
```

---

### 1.5 修复内存泄漏

**优先级**: HIGH
**预计时间**: 1 天

```python
# backend/api/services/insights_service.py
from cachetools import TTLCache

# 替换无限增长的字典
# ❌ _from_last_cache: dict[str, tuple[float, dict[str, Any]]] = {}
# ✅ 使用 TTLCache
_from_last_cache = TTLCache(maxsize=1000, ttl=60)  # 最多 1000 条，60 秒 TTL

# 使用时无需修改代码，TTLCache 实现了字典接口
cached_value = _from_last_cache.get(cache_key)
_from_last_cache[cache_key] = (time.time(), result)
```

---

### 1.6 修复并发安全问题

**优先级**: HIGH
**预计时间**: 2 天

```python
# backend/utils/fb_api_flyweight_factory.py
import asyncio
from typing import Dict
from facebook_business.api import FacebookAdsApi

class FacebookAdsApiFlyweightFactory:
    """Facebook API 客户端缓存工厂（线程安全）"""

    def __init__(self):
        self._cache: Dict[str, FacebookAdsApi] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get(self, ad_account_id: str) -> FacebookAdsApi:
        """获取或创建 API 客户端（双重检查锁）"""

        # 快速路径：已缓存
        if ad_account_id in self._cache:
            return self._cache[ad_account_id]

        # 获取或创建锁
        async with self._global_lock:
            if ad_account_id not in self._locks:
                self._locks[ad_account_id] = asyncio.Lock()

        # 慢速路径：双重检查锁
        async with self._locks[ad_account_id]:
            # 再次检查缓存（其他协程可能已创建）
            if ad_account_id not in self._cache:
                self._cache[ad_account_id] = await self.create(ad_account_id)

        return self._cache[ad_account_id]

    async def create(self, ad_account_id: str) -> FacebookAdsApi:
        """创建 API 客户端"""
        # ... 原有逻辑
```

---

## 2. 短期改进项（1个月）

### 2.1 优化 N+1 查询

**预计时间**: 3 天

```python
# backend/api/services/insights_service.py
async def _attach_entity_names(
    insights: list[dict],
    account_id: str
) -> list[dict]:
    """附加实体名称（优化版）"""

    # 收集所有需要查询的实体 ID
    all_entity_filters = []

    ad_ids = {i["ad_id"] for i in insights if i.get("ad_id")}
    if ad_ids:
        all_entity_filters.append({
            "entity_type": "ad",
            "entity_id": {"$in": list(ad_ids)}
        })

    adset_ids = {i["adset_id"] for i in insights if i.get("adset_id")}
    if adset_ids:
        all_entity_filters.append({
            "entity_type": "adset",
            "entity_id": {"$in": list(adset_ids)}
        })

    campaign_ids = {i["campaign_id"] for i in insights if i.get("campaign_id")}
    if campaign_ids:
        all_entity_filters.append({
            "entity_type": "campaign",
            "entity_id": {"$in": list(campaign_ids)}
        })

    # ✅ 单次查询获取所有实体名称
    if all_entity_filters:
        docs = await AdEntityNamesDocument.find(
            AdEntityNamesDocument.account_id == account_id,
            {"$or": all_entity_filters}
        ).to_list()

        # 构建查找表
        name_lookup = {
            (doc.entity_type, doc.entity_id): doc.entity_name
            for doc in docs
        }

        # 附加名称
        for insight in insights:
            if insight.get("ad_id"):
                insight["ad_name"] = name_lookup.get(("ad", insight["ad_id"]))
            if insight.get("adset_id"):
                insight["adset_name"] = name_lookup.get(("adset", insight["adset_id"]))
            if insight.get("campaign_id"):
                insight["campaign_name"] = name_lookup.get(("campaign", insight["campaign_id"]))

    return insights
```

---

### 2.2 敏感信息脱敏

**预计时间**: 2 天

**1) 日志脱敏**
```python
# backend/utils/logger.py
def redact_sensitive_data(event_dict):
    """脱敏敏感字段"""
    sensitive_fields = {
        "access_token",
        "app_secret",
        "password",
        "api_key"
    }

    for key in sensitive_fields:
        if key in event_dict:
            event_dict[key] = "***REDACTED***"

    return event_dict

# 添加到 structlog 处理器
structlog.configure(
    processors=[
        redact_sensitive_data,  # ✅ 添加脱敏处理器
        # ... 其他处理器
    ]
)
```

**2) 使用 secrets manager**
```python
# backend/config.py
import os
from typing import Optional

# ❌ 不要硬编码密码
# MONGODB_URL = f"mongodb://{username}:{password}@..."

# ✅ 从环境变量读取
MONGODB_URL = os.getenv("MONGODB_URL")

# ✅ 或使用 AWS Secrets Manager
def get_mongodb_url() -> str:
    if os.getenv("ENV") == "production":
        import boto3
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId='prod/mongodb/url')
        return response['SecretString']
    else:
        return os.getenv("MONGODB_URL", "mongodb://localhost:27017")

MONGODB_URL = get_mongodb_url()
```

---

### 2.3 添加输入验证和边界检查

**预计时间**: 3 天

```python
# backend/utils/validators.py
from datetime import datetime, timedelta
from fastapi import HTTPException

MAX_DATE_RANGE_DAYS = 365
MAX_TOTAL_RECORDS = 10000

def validate_date_range(
    since: str,
    until: str,
    max_days: int = MAX_DATE_RANGE_DAYS
) -> tuple[datetime, datetime]:
    """验证日期范围"""

    try:
        since_date = datetime.strptime(since, "%Y-%m-%d")
        until_date = datetime.strptime(until, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {exc}"
        )

    if until_date < since_date:
        raise HTTPException(
            status_code=400,
            detail="until date must be >= since date"
        )

    if (until_date - since_date).days > max_days:
        raise HTTPException(
            status_code=400,
            detail=f"Date range cannot exceed {max_days} days"
        )

    return since_date, until_date

async def validate_record_count(
    account_id: str,
    since: str,
    until: str,
    max_records: int = MAX_TOTAL_RECORDS
):
    """验证记录数量"""

    total_records = await InsightsDailyDocument.count_documents({
        "account_id": account_id,
        "date_start": {"$gte": since, "$lte": until}
    })

    if total_records > max_records:
        raise HTTPException(
            status_code=400,
            detail=f"Query would return {total_records} records (max: {max_records}). Please narrow your date range."
        )

# backend/api/routers/insights.py
from utils.validators import validate_date_range, validate_record_count

@router.get("/insights")
async def query_insights(
    since: str,
    until: str,
    # ...
):
    # ✅ 验证日期范围
    since_date, until_date = validate_date_range(since, until)

    # ✅ 验证记录数量
    await validate_record_count(account_id, since, until)

    # 继续查询...
```

---

### 2.4 实现事务处理

**预计时间**: 2 天

```python
# backend/api/services/fb_auth_service.py
from motor.motor_asyncio import AsyncIOMotorClientSession

async def sync_accounts_with_transaction(
    auth_doc: FbAppAuthDocument,
    payload: SyncAccountsPayload
):
    """同步账户（事务版本）"""

    async with mongo_client.start_session() as session:
        async with session.start_transaction():
            synced_count = 0

            for raw_account in payload.accounts:
                account_id = raw_account["id"].replace("act_", "")

                # 查找现有账户
                existing_account = await ADAccountDocument.find_one(
                    ADAccountDocument.account_id == account_id,
                    session=session  # ✅ 传递 session
                )

                if existing_account:
                    # 更新
                    existing_account.name = raw_account["name"]
                    existing_account.fb_app_auth = auth_doc
                    await existing_account.save(session=session)  # ✅ 传递 session
                else:
                    # 创建
                    new_doc = ADAccountDocument(
                        account_id=account_id,
                        name=raw_account["name"],
                        fb_app_auth=auth_doc
                    )
                    await new_doc.insert(session=session)  # ✅ 传递 session

                synced_count += 1

            return synced_count
```

---

## 3. 中期改进项（2-3个月）

### 3.1 实现权限系统

**预计时间**: 1 周

**1) 创建权限检查依赖**
```python
# backend/api/dependencies/permissions.py
from fastapi import Depends, HTTPException
from api.dependencies.auth import get_current_user
from utils.db import ADAccountDocument, BIUserAdAccountLink

async def check_account_permission(
    account_id: str,
    user_id: str = Depends(get_current_user),
    required_role: str = "viewer"
) -> ADAccountDocument:
    """检查用户对广告账户的权限"""

    # 查找账户
    account = await ADAccountDocument.find_one(
        ADAccountDocument.account_id == account_id.replace("act_", "")
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # 查找用户权限
    link = await BIUserAdAccountLink.find_one(
        BIUserAdAccountLink.user_id == user_id,
        BIUserAdAccountLink.account_id == account_id
    )

    if not link:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this account"
        )

    # 检查角色
    role_hierarchy = {"owner": 3, "editor": 2, "viewer": 1}
    if role_hierarchy.get(link.role, 0) < role_hierarchy.get(required_role, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions (required: {required_role}, you have: {link.role})"
        )

    return account
```

**2) 应用到路由**
```python
# backend/api/routers/insights.py
from api.dependencies.permissions import check_account_permission

@router.get("/insights")
async def query_insights(
    ad_account_id: str,
    # ✅ 添加权限检查
    account: ADAccountDocument = Depends(
        lambda ad_account_id=ad_account_id: check_account_permission(ad_account_id, required_role="viewer")
    ),
    # ...
):
    # 继续查询...
```

---

### 3.2 添加 API 限流

**预计时间**: 3 天

**1) 安装 slowapi**
```bash
uv add slowapi
```

**2) 配置限流**
```python
# backend/api/app.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 创建限流器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# backend/api/routers/insights.py
from fastapi import Request
from slowapi import Limiter

@router.get("/insights")
@limiter.limit("60/minute")  # ✅ 每分钟 60 次
async def query_insights(request: Request, ...):
    # ...
```

**3) Redis 分布式限流**
```python
# backend/api/middleware/rate_limit.py
import redis.asyncio as aioredis
from fastapi import HTTPException

class DistributedRateLimiter:
    """Redis 分布式限流器"""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        """检查是否允许请求"""

        current = int(time.time())
        window_start = current - window_seconds

        # 使用 Redis sorted set
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # 移除过期记录
        pipe.zadd(key, {str(current): current})      # 添加当前请求
        pipe.zcount(key, window_start, current)      # 计数
        pipe.expire(key, window_seconds)             # 设置过期

        _, _, count, _ = await pipe.execute()

        return count <= max_requests

# 使用
limiter = DistributedRateLimiter(redis_client)
is_allowed = await limiter.is_allowed(
    key=f"rate_limit:{user_id}",
    max_requests=60,
    window_seconds=60
)
if not is_allowed:
    raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

---

### 3.3 完善健康检查端点

**预计时间**: 2 天

```python
# backend/api/routers/health.py
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
import structlog

router = APIRouter()
logger = structlog.get_logger(__name__)

@router.get("/health", include_in_schema=False)
async def health_check():
    """健康检查（详细版）"""

    checks = {
        "mongodb": await check_mongodb(),
        "redis": await check_redis(),
        "facebook_api": await check_facebook_api_quota(),
    }

    is_healthy = all(checks.values())
    status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if is_healthy else "unhealthy",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat(),
            "version": os.getenv("APP_VERSION", "unknown")
        }
    )

async def check_mongodb() -> bool:
    """检查 MongoDB 连接"""
    try:
        await mongo_client.admin.command("ping")
        return True
    except Exception as exc:
        logger.error("mongodb_health_check_failed", exc_info=exc)
        return False

async def check_redis() -> bool:
    """检查 Redis 连接"""
    try:
        await redis_client.ping()
        return True
    except Exception as exc:
        logger.error("redis_health_check_failed", exc_info=exc)
        return False

async def check_facebook_api_quota() -> bool:
    """检查 Facebook API 配额"""
    try:
        # 获取任意账户的 API 配额
        # ...
        return True
    except Exception as exc:
        logger.error("facebook_api_health_check_failed", exc_info=exc)
        return False
```

---

## 4. 长期改进项（持续）

### 4.1 添加单元测试

**预计时间**: 持续（每个新功能都添加测试）

**1) 配置 pytest**
```toml
# backend/pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
asyncio_mode = "auto"

[tool.coverage.run]
source = ["api", "utils", "baseline"]
omit = ["tests/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

**2) 编写测试**
```python
# tests/test_insights_service.py
import pytest
from unittest.mock import AsyncMock, patch
from api.services.insights_service import InsightsService

@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB 客户端"""
    with patch("utils.db.mongo_client") as mock:
        yield mock

@pytest.mark.asyncio
async def test_query_insights_mongo_only(mock_mongo_client):
    """测试 MongoDB 查询"""

    # Arrange
    mock_mongo_client.find.return_value.to_list = AsyncMock(return_value=[
        {"ad_id": "123", "date_start": "2025-01-01", "spend": 100.5}
    ])

    # Act
    result = await InsightsService.query_insights_mongo_only(
        account_id="123",
        since="2025-01-01",
        until="2025-01-31"
    )

    # Assert
    assert len(result) > 0
    assert result[0]["ad_id"] == "123"
    assert result[0]["spend"] == 100.5
```

**3) 运行测试**
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_insights_service.py

# 生成覆盖率报告
pytest --cov=api --cov-report=html
```

---

### 4.2 配置化硬编码常量

**预计时间**: 2 天

```python
# backend/config.py
import os
from typing import Optional

class Settings:
    """应用配置"""

    # 数据库
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # 缓存
    FROM_LAST_CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL", "60"))
    MAX_ENTITY_NAME_BATCH_SIZE: int = int(os.getenv("MAX_ENTITY_BATCH", "50"))

    # Insights 同步
    REALTIME_LOOKBACK_DAYS: int = int(os.getenv("REALTIME_LOOKBACK_DAYS", "3"))
    INSIGHTS_ASYNC_THRESHOLD_DAYS: int = int(os.getenv("INSIGHTS_ASYNC_THRESHOLD_DAYS", "7"))

    # 数据存储
    INSIGHTS_DATA_PATH: str = os.getenv("INSIGHTS_DATA_PATH", "/data/insights")

    # 日期范围限制
    MAX_DATE_RANGE_DAYS: int = int(os.getenv("MAX_DATE_RANGE_DAYS", "365"))
    MAX_TOTAL_RECORDS: int = int(os.getenv("MAX_TOTAL_RECORDS", "10000"))

    # API 限流
    API_RATE_LIMIT: str = os.getenv("API_RATE_LIMIT", "60/minute")

    # 日志
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")  # json or text

    # 应用
    APP_VERSION: str = os.getenv("APP_VERSION", "unknown")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

settings = Settings()

# 使用
from backend.config import settings

cache_ttl = settings.FROM_LAST_CACHE_TTL_SECONDS
```

---

### 4.3 优化 CORS 配置

**预计时间**: 1 天

```python
# backend/api/app.py
import os
from fastapi.middleware.cors import CORSMiddleware

# 从环境变量读取允许的源
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")

# 开发环境默认值
if not ALLOWED_ORIGINS or ALLOWED_ORIGINS == [""]:
    ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],  # ✅ 明确指定
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-User-Id",
        "X-User-Email",
        "X-User-Name",
        "X-Request-ID",
        "X-Requested-With"
    ],  # ✅ 明确指定
    max_age=3600,  # 预检请求缓存 1 小时
)
```

---

### 4.4 代码重构

**预计时间**: 持续

#### 提取通用函数

```python
# backend/utils/date_helpers.py
from datetime import datetime
from fastapi import HTTPException

def parse_date(date_str: str, field_name: str) -> datetime:
    """解析日期字符串"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name}: {date_str}")

def validate_date_range(
    since: str,
    until: str,
    max_days: int = 365
) -> tuple[datetime, datetime]:
    """验证日期范围"""
    since_date = parse_date(since, "since")
    until_date = parse_date(until, "until")

    if until_date < since_date:
        raise HTTPException(400, "until date must be >= since date")

    if (until_date - since_date).days > max_days:
        raise HTTPException(400, f"Date range cannot exceed {max_days} days")

    return since_date, until_date
```

#### 拆分大文件

```python
# 拆分 insights_service.py (1887 行)
# services/insights/
#   __init__.py
#   query.py          # MongoDB/Redis 查询
#   sync.py           # 数据同步
#   aggregation.py    # 数据聚合
#   entity_names.py   # 实体名称
#   async_jobs.py     # 异步任务
```

---

### 4.5 添加类型注解

**预计时间**: 1 周

**1) 配置 mypy**
```ini
# mypy.ini
[mypy]
python_version = 3.12
strict = True
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
disallow_any_unimported = False

[mypy-facebook_business.*]
ignore_missing_imports = True

[mypy-motor.*]
ignore_missing_imports = True
```

**2) 添加类型注解**
```python
# ❌ 之前
def _build_default_context(binding):
    if binding is None:
        return {}
    # ...

# ✅ 之后
from typing import Optional
from utils.db import RuleBindingDocument

def _build_default_context(
    binding: Optional[RuleBindingDocument]
) -> dict[str, Any]:
    if binding is None:
        return {}
    # ...
```

**3) 运行 mypy**
```bash
mypy backend/
```

---

## 5. 监控和可观测性

### 5.1 集成 Sentry

**预计时间**: 1 天

```python
# backend/api/app.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("ENVIRONMENT", "development"),
    release=os.getenv("APP_VERSION", "unknown"),
    traces_sample_rate=0.1,  # 10% 的请求追踪
    integrations=[
        FastApiIntegration()
    ]
)
```

---

### 5.2 集成 Prometheus

**预计时间**: 2 天

```python
# backend/api/app.py
from prometheus_fastapi_instrumentator import Instrumentator

# 自动添加 Prometheus 指标
Instrumentator().instrument(app).expose(app)

# 访问 /metrics 查看指标
```

---

## 6. CI/CD 配置

### 6.1 GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mongodb:
        image: mongo:latest
        ports:
          - 27017:27017

      redis:
        image: redis:latest
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: |
          cd backend
          uv sync

      - name: Run tests
        run: |
          cd backend
          uv run pytest --cov=api --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./backend/coverage.xml

      - name: Lint
        run: |
          cd backend
          uv run ruff check .

      - name: Type check
        run: |
          cd backend
          uv run mypy api/

      - name: Security scan
        run: |
          cd backend
          uv run bandit -r api/
```

---

## 7. 总结

### 优先级时间表

| 阶段 | 时间 | 任务 | 预期效果 |
|------|------|------|----------|
| **立即** | 1-2周 | Critical 问题修复 | 生产环境安全稳定 |
| **短期** | 1个月 | High 问题修复 | 性能和安全提升 |
| **中期** | 2-3个月 | Medium 问题改进 | 功能完善和可维护性 |
| **长期** | 持续 | Low 问题优化 | 代码质量和可扩展性 |

### 关键指标

- **测试覆盖率**: 从 0% → 80%
- **代码质量**: Ruff + mypy + bandit 通过
- **安全性**: 所有 CRITICAL 问题修复
- **性能**: N+1 查询优化，响应时间减少 30%
- **可观测性**: Sentry + Prometheus 监控

---

**文档版本**: 1.0
**最后更新**: 2025-12-05
**相关文档**: [03_potential_issues.md](./03_potential_issues.md)
