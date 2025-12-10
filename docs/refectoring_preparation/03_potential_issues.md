# 潜在问题和技术债务分析

**文档版本**: 1.0
**最后更新**: 2025-12-05
**严重程度**: CRITICAL (严重) / HIGH (高危) / MEDIUM (中危) / LOW (低危)

---

## 🔴 CRITICAL - 严重问题（需立即修复）

### 1. 缺少全局异常处理和日志系统

**位置**: `/backend/api/services/insights_service.py`, `/backend/api/services/ad_control_service.py`

**问题描述**:
- 大量使用 `print()` 而不是 proper logging
- 异常信息直接暴露给用户，可能泄露敏感信息
- 缺少结构化日志
- 无请求追踪 ID

**示例代码**:
```python
# insights_service.py:378-382
except Exception as exc:
    if historical_records:
        print(  # ❌ 应该用 logger
            f"Error fetching realtime insights for account {account_id}: {exc}"
        )
```

**影响**:
- 生产环境难以追踪问题
- 敏感信息（账号 ID、Token 片段）可能泄露
- 缺少审计追踪
- 无法做分布式日志聚合

**修复建议**:
```python
import logging
import structlog

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger(__name__)

try:
    # ...
except FacebookRequestError as exc:
    logger.error(
        "failed_to_fetch_insights",
        account_id=account_id,
        error_code=exc.api_error_code(),
        error_message=str(exc),
        exc_info=True
    )
    raise HTTPException(status_code=500, detail="Failed to fetch insights")
```

---

### 2. 数据库连接未配置连接池参数

**位置**: `/backend/utils/db.py:312`

**问题描述**:
```python
mongo_client = AsyncMongoClient(mongodb_url)  # ❌ 无连接池配置
```

- 未配置连接池参数
- 无最大连接数限制
- 无连接超时控制
- 可能导致连接耗尽

**影响**:
- 高并发下数据库连接耗尽
- 性能下降
- 服务不稳定
- 可能导致 MongoDB 拒绝服务

**修复建议**:
```python
mongo_client = AsyncMongoClient(
    mongodb_url,
    maxPoolSize=50,             # 最大连接数
    minPoolSize=10,             # 最小连接数
    maxIdleTimeMS=30000,        # 空闲连接超时
    connectTimeoutMS=5000,      # 连接超时
    serverSelectionTimeoutMS=5000,  # 服务器选择超时
    waitQueueTimeoutMS=5000,    # 等待队列超时
)
```

---

### 3. NoSQL 注入风险

**位置**: `/backend/api/services/insights_service.py:1243-1252`

**问题描述**:
```python
match_stage: dict[str, Any] = {
    "account_id": account_id_without_prefix,  # ✅ Safe
    "date_start": {
        "$gte": date_lower,
        "$lte": date_upper,
    },
}
if object_filter:
    field_name, normalized_ids = object_filter
    match_stage[field_name] = {"$in": normalized_ids}  # ⚠️ field_name 未验证
```

**影响**:
- NoSQL 注入风险
- 攻击者可能构造恶意 `field_name`
- 数据泄露
- 潜在的 DoS 攻击

**攻击示例**:
```python
# 攻击者可能传入
field_name = "$where"
# 导致执行任意 JavaScript
```

**修复建议**:
```python
ALLOWED_FILTER_FIELDS = {"ad_id", "adset_id", "campaign_id"}

if object_filter:
    field_name, normalized_ids = object_filter
    if field_name not in ALLOWED_FILTER_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid filter field: {field_name}"
        )
    match_stage[field_name] = {"$in": normalized_ids}
```

---

### 4. Facebook API 调用无速率限制保护

**位置**: `/backend/utils/insight_tool.py`, `/backend/api/services/insights_service.py`

**问题描述**:
- Entity sync 有重试机制，但其他 API 调用没有
- 无全局速率限制器
- 可能触发 Facebook API ban
- 错误 80004 (Rate Limit Exceeded) 处理不一致

**示例**:
```python
# insights_service.py:354
insights = get_insight(  # ❌ 无速率限制
    adobject=ad_object,
    fields=api_fields,
    # ...
)
```

**影响**:
- API 配额耗尽
- 账号被 Facebook 限制
- 服务中断
- 无法恢复数据获取

**修复建议**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from facebook_business.exceptions import FacebookRequestError

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(FacebookRequestError)
)
def get_insight_with_retry(...):
    try:
        return get_insight(...)
    except FacebookRequestError as exc:
        if exc.api_error_code() == 80004:  # Rate limit
            logger.warning("rate_limit_exceeded", retry_after=10)
            raise  # 触发重试
        raise
```

---

### 5. SQL/NoSQL 注入风险（聚合查询）

**位置**: `/backend/api/services/insights_service.py:1270-1360`

**问题描述**:
```python
# 聚合管道未验证 level 参数
group_stage = {
    "_id": f"${level}_id",  # ⚠️ level 未验证
    # ...
}
```

**影响**:
- 攻击者可能注入任意字段名
- MongoDB 聚合管道注入
- 数据泄露

**修复建议**:
```python
ALLOWED_LEVELS = {"ad", "adset", "campaign"}

if level not in ALLOWED_LEVELS:
    raise HTTPException(status_code=400, detail=f"Invalid level: {level}")

group_stage = {
    "_id": f"${level}_id",
    # ...
}
```

---

## 🟠 HIGH - 高危问题

### 6. 内存泄漏风险 - 无限增长的缓存

**位置**: `/backend/api/services/insights_service.py:32`

**问题描述**:
```python
_from_last_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_from_last_cache_lock = asyncio.Lock()
```

- 缓存无大小限制
- 无 LRU 淘汰机制
- 长期运行后可能导致内存耗尽

**影响**:
- 内存泄漏
- OOM (Out of Memory)
- 服务崩溃
- 需要频繁重启

**修复建议**:
```python
from cachetools import TTLCache

_from_last_cache = TTLCache(maxsize=1000, ttl=60)  # 最多 1000 条，60 秒 TTL
```

---

### 7. 并发安全问题 - Race Condition

**位置**: `/backend/utils/fb_api_flyweight_factory.py:19-22`

**问题描述**:
```python
async def get(self, ad_account_id: str) -> FacebookAdsApi:
    if ad_account_id not in self._cache:  # ⚠️ Race condition
        self._cache[ad_account_id] = await self.create(ad_account_id)
    return self._cache[ad_account_id]
```

**场景**:
```
时间  协程A                 协程B
T1    check not in cache
T2                          check not in cache
T3    create API client
T4                          create API client (重复)
T5    store in cache
T6                          overwrite cache
```

**影响**:
- 多个协程同时调用会创建多个 API 实例
- 资源浪费
- 潜在的不一致状态
- Facebook API 配额浪费

**修复建议**:
```python
import asyncio
from typing import Dict

class FacebookAdsApiFlyweightFactory:
    def __init__(self):
        self._cache: Dict[str, FacebookAdsApi] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get(self, ad_account_id: str) -> FacebookAdsApi:
        # 快速路径：已缓存
        if ad_account_id in self._cache:
            return self._cache[ad_account_id]

        # 获取或创建锁
        async with self._global_lock:
            if ad_account_id not in self._locks:
                self._locks[ad_account_id] = asyncio.Lock()

        # 慢速路径：双重检查锁
        async with self._locks[ad_account_id]:
            if ad_account_id not in self._cache:
                self._cache[ad_account_id] = await self.create(ad_account_id)

        return self._cache[ad_account_id]
```

---

### 8. N+1 查询问题

**位置**: `/backend/api/services/insights_service.py:1069-1093`

**问题描述**:
```python
# 为每种 entity_type 单独查询
async def _load_names(entity_type, ids):
    if not ids:
        return
    docs = await AdEntityNamesDocument.find(
        AdEntityNamesDocument.account_id == account_id,
        AdEntityNamesDocument.entity_type == entity_type,
        In(AdEntityNamesDocument.entity_id, list(ids)),
    ).to_list()  # ⚠️ 对 ad level，需要 3 次查询
```

**场景**:
```
ad level 查询:
  1. 查询所有 ad_id 的名称
  2. 查询所有 adset_id 的名称
  3. 查询所有 campaign_id 的名称

总共 3 次数据库查询
```

**影响**:
- 数据库负载增加
- 响应延迟
- 可扩展性差
- 高并发下性能瓶颈

**修复建议**:
```python
# 单次查询获取所有实体名称
all_entity_filters = []
if ad_ids:
    all_entity_filters.append({
        "entity_type": "ad",
        "entity_id": {"$in": list(ad_ids)}
    })
if adset_ids:
    all_entity_filters.append({
        "entity_type": "adset",
        "entity_id": {"$in": list(adset_ids)}
    })
if campaign_ids:
    all_entity_filters.append({
        "entity_type": "campaign",
        "entity_id": {"$in": list(campaign_ids)}
    })

if all_entity_filters:
    docs = await AdEntityNamesDocument.find(
        AdEntityNamesDocument.account_id == account_id,
        {"$or": all_entity_filters}
    ).to_list()
```

---

### 9. 敏感信息泄露

**位置**: `/backend/api/services/fb_auth_service.py:388`, `/backend/config.py:12`

**问题描述**:
```python
# fb_auth_service.py:388
logger.info(
    f"Token changed: {auth_doc.access_token[-4:] if auth_doc.access_token else 'N/A'} -> {refreshed_token[-4:]}"
)  # ⚠️ Token 片段可能泄露

# config.py:12
MONGODB_URL = f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@..."
# ⚠️ 密码在代码中明文
```

**影响**:
- Token 信息可能泄露
- 数据库密码在日志中
- 安全审计风险
- 可能导致账号被盗

**修复建议**:
```python
# 1. 不要在日志中记录任何 token 片段
logger.info("token_refreshed", account_id=auth_doc.id)  # 仅记录 ID

# 2. 使用环境变量
MONGODB_URL = os.getenv("MONGODB_URL")  # 从环境变量读取完整 URL

# 3. 使用 secrets manager
from aws_secretsmanager import get_secret
MONGODB_PASSWORD = get_secret("prod/mongodb/password")
```

---

### 10. 缺少输入验证和边界检查

**位置**: `/backend/api/routers/insights.py:723-724`

**问题描述**:
```python
page: Annotated[int, Query(description="Page number (1-indexed)", ge=1)] = 1,
page_size: Annotated[int, Query(description="Records per page", ge=1, le=100)] = 50,
```

- 虽然有 `le=100` 限制，但仍可能导致大量数据查询
- **缺少日期范围限制**（可查询任意时间跨度）
- 无总记录数限制

**影响**:
- DoS 攻击风险（查询 10 年数据）
- 数据库过载
- 内存溢出
- 响应超时

**攻击示例**:
```bash
# 查询 10 年数据
curl "http://api/insights?since=2015-01-01&until=2025-12-31&page_size=100"
```

**修复建议**:
```python
from datetime import datetime, timedelta

MAX_DATE_RANGE_DAYS = 365
MAX_TOTAL_RECORDS = 10000

since_date = InsightsService._parse_date(since, "since date")
until_date = InsightsService._parse_date(until, "until date")

# 日期范围限制
if (until_date - since_date).days > MAX_DATE_RANGE_DAYS:
    raise HTTPException(
        status_code=400,
        detail=f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days"
    )

# 总记录数限制
total_records = await InsightsDailyDocument.count_documents({
    "account_id": account_id,
    "date_start": {"$gte": since, "$lte": until}
})
if total_records > MAX_TOTAL_RECORDS:
    raise HTTPException(
        status_code=400,
        detail=f"Query would return {total_records} records (max: {MAX_TOTAL_RECORDS}). Please narrow your date range."
    )
```

---

## 🟡 MEDIUM - 中危问题

### 11. 缺少事务处理

**位置**: `/backend/api/services/fb_auth_service.py:233-306`

**问题描述**:
```python
# fb_auth_service.py:288-305
for raw_account in payload.accounts:
    existing_account = await ADAccountDocument.find_one(...)
    if existing_account:
        existing_account.name = raw_account["name"]
        existing_account.fb_app_auth = auth_doc
        await existing_account.save()  # ⚠️ 无事务保护
    else:
        new_doc = ADAccountDocument(...)
        await new_doc.insert()
```

**场景**:
```
处理 10 个账户:
  1-5 成功
  6 失败 (网络错误)
  7-10 未执行

结果: 数据���一致
```

**影响**:
- 部分成功/部分失败场景
- 数据不一致
- 难以回滚
- 需要手动修复

**修复建议**:
```python
from motor.motor_asyncio import AsyncIOMotorClientSession

async with mongo_client.start_session() as session:
    async with session.start_transaction():
        for raw_account in payload.accounts:
            existing_account = await ADAccountDocument.find_one(
                ADAccountDocument.account_id == raw_account["id"],
                session=session
            )
            if existing_account:
                existing_account.name = raw_account["name"]
                await existing_account.save(session=session)
            else:
                new_doc = ADAccountDocument(...)
                await new_doc.insert(session=session)
```

---

### 12. 未处理的 Promise/Future

**位置**: `/backend/api/services/entity_names_sync_service.py:49`

**问题描述**:
```python
asyncio.create_task(_run(operations))  # ⚠️ Fire-and-forget，无异常处理
```

**影响**:
- 后台任务失败无感知
- 错误被吞噬
- 难以调试
- 内存泄漏（未 await 的 Task）

**修复建议**:
```python
# 方法 1: 添加异常回调
task = asyncio.create_task(_run(operations))

def handle_task_exception(t: asyncio.Task):
    try:
        t.result()
    except Exception as exc:
        logger.error("background_task_failed", exc_info=exc)

task.add_done_callback(handle_task_exception)

# 方法 2: 使用任务组（Python 3.11+）
async with asyncio.TaskGroup() as tg:
    tg.create_task(_run(operations))
```

---

### 13. 硬编码配置值

**位置**: Multiple files

**问题示例**:
```python
# insights_service.py:31
FROM_LAST_CACHE_TTL_SECONDS = 60  # ❌ 硬编码

# entity_names_sync_service.py:20
MAX_ENTITY_NAME_BATCH_SIZE = 50  # ❌ 硬编码

# insights_sync_service.py
REALTIME_LOOKBACK_DAYS = 3  # ❌ 硬编码
INSIGHTS_ASYNC_THRESHOLD_DAYS = 7  # ❌ 硬编码

# Note: Data storage has been migrated to MongoDB (InsightsDocument)
```

**影响**:
- 难以配置
- 环境迁移困难
- 缺乏灵活性
- 无法动态调整

**修复建议**:
```python
# config.py
import os

FROM_LAST_CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "60"))
MAX_ENTITY_NAME_BATCH_SIZE = int(os.getenv("MAX_ENTITY_BATCH", "50"))
REALTIME_LOOKBACK_DAYS = int(os.getenv("REALTIME_LOOKBACK_DAYS", "3"))
INSIGHTS_ASYNC_THRESHOLD_DAYS = int(os.getenv("INSIGHTS_ASYNC_THRESHOLD_DAYS", "7"))
INSIGHTS_DATA_PATH = os.getenv("INSIGHTS_DATA_PATH", "/data/insights")
```

---

### 14. 缺少重试机制和超时控制

**位置**: `/backend/api/services/insights_service.py:354-363`

**问题描述**:
```python
insights = get_insight(
    adobject=ad_object,
    fields=api_fields,
    level=fetch_level,
    since=realtime_since.strftime("%Y-%m-%d"),
    until=until_date.strftime("%Y-%m-%d"),
    time_increment=time_increment,
    breakdowns=breakdowns or "",
    is_async=False,
)  # ⚠️ 无超时控制，无重试
```

**影响**:
- 请求挂起
- 资源耗尽
- 用户体验差
- 无法从临时错误中恢复

**修复建议**:
```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def get_insight_with_retry_and_timeout(...):
    try:
        insights = await asyncio.wait_for(
            asyncio.to_thread(
                get_insight,
                adobject=ad_object,
                # ...
            ),
            timeout=30.0  # 30秒超时
        )
        return insights
    except asyncio.TimeoutError:
        logger.error("insight_fetch_timeout", account_id=account_id)
        raise HTTPException(status_code=504, detail="Request timeout")
```

---

### 15. CORS 配置过于宽松

**位置**: `/backend/api/app.py:127-140`

**问题描述**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # ⚠️ 允许所有方法
    allow_headers=["*"],  # ⚠️ 允许所有头
)
```

**影响**:
- CSRF 攻击风险
- 过度暴露 API
- 安全隐患
- 不符合最小权限原则

**修复建议**:
```python
import os

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # 仅允许需要的方法
    allow_headers=["Content-Type", "Authorization", "X-User-Id", "X-Requested-With"],
    max_age=3600,
)
```

---

## 🟢 LOW - 低危问题

### 16. 代码重复（DRY 原则违反）

**位置**: Multiple files

**示例**:
- `insights_service.py` 中的聚合逻辑重复
- 多处使用相同的日期验证逻辑
- Entity serialization 代码重复

**修复建议**:
提取通用函数到 `utils/` 模块

```python
# utils/date_helpers.py
def parse_date(date_str: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"Invalid {field_name}: {date_str}")

def validate_date_range(since: str, until: str, max_days: int = 365):
    since_date = parse_date(since, "since")
    until_date = parse_date(until, "until")

    if until_date < since_date:
        raise HTTPException(400, "until date must be >= since date")

    if (until_date - since_date).days > max_days:
        raise HTTPException(400, f"Date range cannot exceed {max_days} days")

    return since_date, until_date
```

---

### 17. 缺少类型注解

**位置**: Multiple files

**示例**:
```python
# rule_engine_service.py:630
def _build_default_context(binding):  # ❌ 缺少类型
    if binding is None:
        return {}
```

**修复建议**:
启用 `mypy` 并添加完整类型注解

```python
from typing import Optional

def _build_default_context(binding: Optional[RuleBindingDocument]) -> dict[str, Any]:
    if binding is None:
        return {}
    # ...
```

**mypy 配置**:
```ini
# mypy.ini
[mypy]
python_version = 3.12
strict = True
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
```

---

### 18. 过长的函数和文件

**位置**:
- `insights_service.py` (1887 行)
- `insights.py` (1500 行)
- `InsightsDataPage.tsx` (2507 行)

**建议**:
- 拆分成更小的模块和类
- 遵循单一职责原则
- 提取可复用组件

**重构示例**:
```python
# 拆分 insights_service.py
# services/insights/query.py
# services/insights/sync.py
# services/insights/aggregation.py
# services/insights/entity_names.py
```

---

### 19. 缺少单元测试

**影响**:
代码质量无保障，重构困难

**建议**:
- 使用 `pytest` 添加单元测试
- 目标覆盖率 > 80%
- 使用 `pytest-asyncio` for async tests
- 使用 `pytest-mock` for mocking

**测试示例**:
```python
# tests/test_insights_service.py
import pytest
from api.services.insights_service import InsightsService

@pytest.mark.asyncio
async def test_query_insights_mongo_only(mock_mongo):
    # Arrange
    mock_mongo.return_value = [...]

    # Act
    result = await InsightsService.query_insights_mongo_only(
        account_id="123",
        since="2025-01-01",
        until="2025-01-31"
    )

    # Assert
    assert len(result) > 0
    assert result[0]["account_id"] == "123"
```

---

### 20. 依赖版本管理

**位置**: `/backend/pyproject.toml`

**问题**:
```toml
dependencies = [
    "apscheduler>=3.10.4",  # ⚠️ 无上限版本
    "beanie>=2.0.0",
    "facebook-business>=23.0.3",
    # ...
]
```

**影响**:
- 可能引入不兼容的依赖版本
- 构建不可重现
- 安全漏洞

**建议**:
```toml
dependencies = [
    "apscheduler>=3.10.4,<4.0.0",
    "beanie>=2.0.0,<3.0.0",
    "facebook-business>=23.0.3,<24.0.0",
]
```

**使用 dependabot**:
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
```

---

## 📋 修复优先级建议

### 立即修复（1-2 周）:
1. **全局异常处理和日志** (#1) - CRITICAL
2. **数据库连接池** (#2) - CRITICAL
3. **NoSQL 注入防护** (#3, #5) - CRITICAL
4. **Facebook API 速率限制** (#4) - CRITICAL
5. **内存泄漏** (#6) - HIGH
6. **并发安全** (#7) - HIGH

### 短期修复（1 个月）:
7. **N+1 查询** (#8) - HIGH
8. **敏感信息保护** (#9) - HIGH
9. **输入验证** (#10) - HIGH
10. **事务处理** (#11) - MEDIUM

### 中期改进（2-3 个月）:
11-15. 未处理 Promise、硬编码、重试机制、CORS (#12-15) - MEDIUM

### 长期优化（持续）:
16-20. 代码重构、测试覆盖、依赖管理 (#16-20) - LOW

---

## 🛠️ 推荐工具

### 静态分析
- **mypy**: 类型检查
- **ruff**: 快速 linting (替代 flake8 + isort)
- **bandit**: 安全扫描
- **safety**: 依赖漏洞检查

### 监控和追踪
- **Sentry**: 错误追踪和性能监控
- **Prometheus + Grafana**: 指标监控
- **OpenTelemetry**: 分布式追踪
- **ELK Stack**: 日志聚合

### 测试
- **pytest**: 单元测试
- **pytest-asyncio**: 异步测试
- **pytest-cov**: 覆盖率报告
- **locust**: 负载测试
- **playwright**: E2E 测试（前端）

### CI/CD
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          pytest --cov=api --cov-report=xml
      - name: Lint
        run: ruff check .
      - name: Type check
        run: mypy api/
      - name: Security scan
        run: bandit -r api/
```

---

## 总结

本代码库实现了复杂的 Facebook 广告自动化功能，但存在多个**严重的生产环境风险**。建议立即解决 Critical 和 High 级别的问题，并建立持续的代码审查和测试流程。

**关键改进领域**:
1. ✅ 错误处理和日志系统
2. ✅ 数据库和并发安全
3. ✅ API 速率限制和重试机制
4. ✅ 安全防护（注入、敏感信息）
5. ✅ 代码质量和可维护性

**预计修复时间**:
- Critical 问题: 1-2 周
- High 问题: 3-4 周
- Medium 问题: 2-3 个月
- Low 问题: 持续改进

---

**文档版本**: 1.0
**最后更新**: 2025-12-05
**下一篇**: [04_refactoring_recommendations.md](./04_refactoring_recommendations.md)
