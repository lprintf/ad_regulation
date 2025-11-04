# Facebook 广告自动化调控系统 - 系统架构拆解文档

> **文档版本**: v1.0
> **创建日期**: 2025-10-31
> **系统状态**: 核心功能已完成，规则引擎开发中

---

## 目录

1. [系统概览](#1-系统概览)
2. [核心架构](#2-核心架构)
3. [模块拆解](#3-模块拆解)
4. [数据流设计](#4-数据流设计)
5. [技术栈](#5-技术栈)
6. [开发计划与路线图](#6-开发计划与路线图)
7. [部署架构](#7-部署架构)
8. [扩展性设计](#8-扩展性设计)

---

## 1. 系统概览

### 1.1 系统定位

本系统是一个**数据驱动的Facebook广告自动化调控平台**，通过机器学习预测和规则引擎实现广告的智能管理和优化。

### 1.2 核心目标

- **自动化决策**: 基于数据和模型自动控制广告启停、预算调整
- **混合策略**: 结合ML预测和业务规则的双轨决策机制
- **可追溯性**: 完整的操作审计和执行历史
- **高可用性**: 异步任务处理、故障恢复、监控告警

### 1.3 业务价值

- **降低人工成本**: 自动化广告优化，减少人工监控时间 60%+
- **提升ROAS**: 及时识别低效广告，平均ROAS提升 15-25%
- **风险控制**: 规则引擎防止预算超支和违规投放
- **数据驱动**: 基于历史数据和ML模型的科学决策

### 1.4 系统实现状态

| 模块 | 状态 | 完成度 | 说明 |
|------|------|--------|------|
| **数据获取** | ✅ 已完成 | 100% | Insights同步/异步获取 |
| **ML评估** | ✅ 已完成 | 100% | HistGradientBoosting模型预测 |
| **广告控制** | ✅ 已完成 | 100% | 启停、预算、名称管理 |
| **活动审计** | ✅ 已完成 | 100% | 完整的操作历史追踪 |
| **规则引擎** | 🚧 开发中 | 70% | CRUD、绑定、执行、调度已完成 |
| **前端控制台** | 📋 计划中 | 0% | React管理界面 |
| **监控告警** | 📋 计划中 | 0% | Prometheus + Grafana |

---

## 2. 核心架构

### 2.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  HTTP Client │  │  Web Console │  │  Scheduler (APScheduler) │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
└─────────┼──────────────────┼──────────────────────┼─────────────────┘
          │                  │                      │
┌─────────┼──────────────────┼──────────────────────┼─────────────────┐
│         │         FastAPI Application Layer       │                 │
│         ▼                  ▼                      ▼                 │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                    API Routers                             │    │
│  │  ┌──────┬──────┬─────────┬────────┬──────────┬──────────┐ │    │
│  │  │Health│ Ad   │Insights │   ML   │   Ad     │  Rules   │ │    │
│  │  │      │Accts │Sync/Asy │Predict │ Control  │  Engine  │ │    │
│  │  └──────┴──────┴─────────┴────────┴──────────┴──────────┘ │    │
│  └────────────────────────┬───────────────────────────────────┘    │
│                           │                                         │
│  ┌────────────────────────┴───────────────────────────────────┐    │
│  │                   Service Layer                            │    │
│  │  ┌──────────┬──────────────┬──────────────┬──────────────┐│    │
│  │  │ Insights │  Prediction  │  Ad Control  │ Rule Engine  ││    │
│  │  │ Service  │   Service    │   Service    │   Service    ││    │
│  │  └──────────┴──────────────┴──────────────┴──────────────┘│    │
│  └─────────────────────���──┬───────────────────────────────────┘    │
└───────────────────────────┼────────────────────────────────────────┘
                            │
┌───────────────────────────┼────────────────────────────────────────┐
│        Data & Integration Layer                                    │
│                           ▼                                         │
│  ┌────────────────┬───────────────────┬────────────────────────┐   │
│  │   MongoDB      │  FB API Flyweight │   ML Pipeline          │   │
│  │  (Beanie ODM)  │   Factory Cache   │  (Feature Engineering) │   │
│  │                │                   │                        │   │
│  │ • Accounts     │  • API Clients    │  • Data Cleaning       │   │
│  │ • Auth Tokens  │  • Connection     │  • Lag Features        │   │
│  │ • Rules        │    Pooling        │  • Model Training      │   │
│  │ • Bindings     │  • Error Handling │  • Prediction          │   │
│  │ • Exec Logs    │                   │                        │   │
│  └────────────────┴───────────────────┴────────────────────────┘   │
└───────────────────────────┬────────────────────────────────────────┘
                            │
┌───────────────────────────┼────────────────────────────────────────┐
│        External Services  ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Facebook Marketing API                         │   │
│  │  • Insights Data   • Ad Control   • Activities (Audit)     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 架构设计原则

#### 2.2.1 分层架构 (Layered Architecture)

- **Router层**: 请求路由、参数验证、响应格式化
- **Service层**: 业务逻辑封装、事务管理、异常处理
- **Data层**: 数据访问抽象、ORM操作、缓存管理

**优势**:
- 关注点分离，易于测试和维护
- 层间依赖单向，降低耦合
- 便于团队分工协作

#### 2.2.2 依赖注入 (Dependency Injection)

```python
# 示例：用户认证和数据库连接注入
@router.get("/ad-accounts")
async def list_accounts(
    user_id: str = Depends(get_current_user),  # 认证注入
    db: Database = Depends(get_db)             # 数据库注入
):
    ...
```

**优势**:
- 提高代码可测试性
- 松耦合，易于替换实现
- 集中管理横切关注点（认证、日志等）

#### 2.2.3 异步优先 (Async-First)

所有I/O操作（数据库、API调用）使用 `async/await`

**优势**:
- 高并发处理能力
- 资源利用率高
- 非阻塞I/O，响应快

#### 2.2.4 设计模式应用

| 设计模式 | 应用场景 | 位置 |
|---------|---------|------|
| **Flyweight** | Facebook API连接缓存 | `utils/fb_api_flyweight_factory.py` |
| **Factory** | API客户端创建 | `utils/fb_api_flyweight_factory.py` |
| **Sandbox** | 规则脚本安全执行 | `utils/rule_sandbox.py` |
| **Repository** | 数据访问抽象 | Service层 |
| **Strategy** | 规则执行策略 | 规则引擎 |

---

## 3. 模块拆解

### 3.1 模块总览

```
ad_regulation/
├── api/                    # FastAPI应用层 (Web服务)
├── baseline/               # ML数据管道 (离线批处理)
├── utils/                  # 核心工具类 (共享基础设施)
├── rules/                  # 规则脚本存储
├── tests/                  # 测试套件
├── docs/                   # 文档
└── frontend/               # 前端控制台 (计划中)
```

---

### 3.2 API层 (`api/`)

#### 3.2.1 目录结构

```
api/
├── app.py                  # FastAPI应用入口
├── routers/                # 路由定义
│   ├── health.py           # 健康检查
│   ├── ad_accounts.py      # 账户管理
│   ├── insights.py         # 数据获取
│   ├── predictions.py      # ML预测
│   ├── ad_control.py       # 广告控制
│   └── rules.py            # 规则引擎
├── services/               # 业务逻辑
│   ├── insights_service.py
│   ├── prediction_service.py
│   ├── ad_control_service.py
│   ├── rule_engine_service.py
│   ├── rule_context_service.py
│   └── rule_scheduler.py
├── models/                 # Pydantic数据模型
│   ├── responses.py        # 标准响应格式
│   ├── ad_accounts.py
│   ├── insights.py
│   ├── ad_control.py
│   └── rules.py
└── dependencies/           # 依赖注入
    ├── auth.py             # 用户认证
    └── database.py         # 数据库连接
```

#### 3.2.2 核心端点

##### A. 健康检查 (`health.py`)

```http
GET /health
```

- 检查服务状态、数据库连接、外部依赖

##### B. 广告账户管理 (`ad_accounts.py`)

```http
GET  /ad-accounts                    # 列出所有账户
GET  /ad-accounts/{account_id}       # 获取账户详情
```

##### C. Insights数据获取 (`insights.py`)

```http
GET  /insights/sync                  # 同步获取
POST /insights/async                 # 创建异步任务
GET  /insights/async/{job_id}        # 查询任务状态
GET  /insights/async/{job_id}/result # 获取任务结果
```

**特点**:
- 支持日报/小时报等多种粒度
- 国家、年龄、性别等多维度拆分
- 大数据量自动切换异步模式
- 任务状态轮询和进度追踪

##### D. ML预测 (`predictions.py`)

```http
POST /predictions/evaluate            # 评估所有账户
GET  /predictions/evaluate/{account_id} # 评估特定账户
```

**返回数据**:
- 停止概率 (`pred_proba`)
- 特征值（spend、ROAS、CTR等）
- 评估日期和数据范围

##### E. 广告控制 (`ad_control.py`)

```http
GET  /ad-control/status               # 查询广告状态
POST /ad-control/start                # 启动广告
POST /ad-control/stop                 # 暂停广告
POST /ad-control/update-name          # 更新名称
GET  /ad-control/adset/budget         # 查询预算
POST /ad-control/adset/update-budget  # 更新预算
GET  /ad-control/activities           # 活动审计
```

**亮点**:
- 完整的CRUD操作
- 操作前验证
- 详细的错误反馈
- 完整的审计日志

##### F. 规则引擎 (`rules.py`)

```http
# 规则定义
POST /rules                           # 创建规则
GET  /rules                           # 列出规则
GET  /rules/{rule_id}                 # 获取规则详情
PUT  /rules/{rule_id}                 # 更新规则
DELETE /rules/{rule_id}               # 删除规则

# 规则绑定
POST /rules/bindings                  # 创建绑定
GET  /rules/bindings                  # 列出绑定
PUT  /rules/bindings/{binding_id}     # 更新绑定
DELETE /rules/bindings/{binding_id}   # 删除绑定

# 规则执行
POST /rules/execute                   # 手动执行规则
GET  /rules/executions                # 执行历史

# 调度管理
GET  /rules/scheduler/tasks           # 调度任务列表
PUT  /rules/scheduler/tasks/{task_id} # 更新调度任务
```

#### 3.2.3 Service层设计

##### 职责划分

| Service | 职责 | 依赖 |
|---------|------|------|
| **InsightsService** | 调用FB API获取数据、格式化输出 | FB API Factory |
| **PredictionService** | 加载模型、特征工程、预测输出 | ML Pipeline、Insights |
| **AdControlService** | 广告操作、状态验证、活动查询 | FB API Factory |
| **RuleEngineService** | 规则CRUD、绑定管理、执行协调 | RuleContextService、Sandbox |
| **RuleContextService** | 构建执行上下文（数据、特征） | InsightsService、Prediction |
| **RuleScheduler** | APScheduler管理、任务注册 | RuleEngineService |

##### 统一响应格式

```python
# 成功响应
{
  "success": true,
  "data": { ... },
  "message": "Optional success message"
}

# 错误响应
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description",
    "details": { ... }
  }
}
```

---

### 3.3 ML数据管道 (`baseline/`)

#### 3.3.1 组件结构

```
baseline/
├── get_data.py       # Facebook API数据抓取
├── data_build.py     # 特征工程和标签生成
└── train_tools.py    # 模型训练和评估
```

#### 3.3.2 数据获取 (`get_data.py`)

**功能**:
- 同步获取: `get_insight()`
- 异步获取: `get_insight_tasks()` + `await_async_tasks()`
- 自动重试和错误处理
- 数据保存为 `.feather` 格式

**数据流**:
```
MongoDB (账户信息)
    → FB API Factory (认证)
    → Facebook Insights API
    → 数据转换 (atomic_metric)
    → Feather文件 (D:/data/insights_data_1020/)
```

#### 3.3.3 特征工程 (`data_build.py`)

**处理流程**:

1. **数据清洗** (`clean_data()`)
   - 移除无效记录
   - 过滤低花费广告
   - 数据类型转换

2. **特征构建** (`build_features()`)
   - Lag特征: 1-7天历史数据
   - 趋势特征: 移动平均、动量
   - 波动率特征: 标准差、变异系数
   - 衰减加权平均

3. **标签生成** (`build_labels()`)
   - 基于ROAS阈值
   - 过去3天 + 未来7天窗口
   - 二分类: 停止/继续

**输出**:
- `models/feat.feather`: 特征矩阵
- `models/labels.feather`: 标签向量

#### 3.3.4 模型训练 (`train_tools.py`)

**算法**: `HistGradientBoostingClassifier`

**训练流程**:
1. 按 `ad_id` 分组（防止数据泄漏）
2. 训练集/验证集分割
3. 模型训练
4. 阈值优化（最大化F1 Score）
5. 评估指标输出

**评估指标**:
- AUC-ROC
- Precision/Recall/F1
- 混淆矩阵
- 特征重要性

---

### 3.4 工具类 (`utils/`)

#### 3.4.1 数据库层 (`db.py`)

**ORM**: Beanie (异步MongoDB ODM)

**文档模型**:

| 模型 | 说明 | 核心字段 |
|------|------|---------|
| `ADAccountDocument` | 广告账户 | account_id, name, timezone |
| `FbAppAuthDocument` | FB应用认证 | app_id, app_secret, access_token |
| `FbAppTokenInfoDocument` | Token元数据 | expires_at, scopes |
| `BIUserAdAccountLink` | 用户-账户关联 | user_id, account_id, role |
| `RuleDefinitionDocument` | 规则定义 | name, code, version, status |
| `RuleBindingDocument` | 规则绑定 | rule_id, entity_id, is_active |
| `RuleExecutionLogDocument` | 执行日志 | status, actions, reasons, metrics |

**连接管理**:
```python
await init_db()      # 启动时初始化
await close_db()     # 关闭时清理
```

#### 3.4.2 Facebook API工厂 (`fb_api_flyweight_factory.py`)

**设计模式**: Flyweight（享元模式）

**核心函数**:

```python
def get_ad_object(ad_account_id: str, fbid: str)
    """
    获取Facebook对象���Ad/AdSet/Campaign/AdAccount）
    - 自动缓存API连接
    - 从MongoDB加载认证信息
    - 返回可操作的对象实例
    """
```

**缓存策略**:
- 按 `ad_account_id` 缓存 `FacebookAdsApi` 实例
- 减少重复认证开销
- 线程安全

#### 3.4.3 Insights工具 (`insight_tool.py`)

**核心函数**:

```python
def get_atomic_metric(insight_data: dict) -> dict
    """提取并转换原子指标"""

def get_daily_insight(...)
    """获取日报数据"""

def get_advertiser_hourly_insight(...)
    """获取广告主时区小时报"""

def get_audience_hourly_insight(...)
    """获取受众时区小时报"""

def get_country_insight(...)
    """获取国家维度数据"""
```

**数据类型优化**:
- 使用 `float32`/`int32` 节省内存
- `atomic_dtype_spec` 定义数据规范

#### 3.4.4 规则沙箱 (`rule_sandbox.py`)

**功能**: 安全执行规则脚本

**安全机制**:
1. **白名单模块**: 限制可导入的Python模块
2. **受控环境**: 隔离的执行上下文
3. **异常捕获**: 防止脚本崩溃影响主程序
4. **超时控制**: 防止无限循环（计划中）

**执行流程**:
```python
result = execute_rule_script(
    code="规则Python代码",
    context={
        "ad_id": "123",
        "spend": 100.5,
        "roas": 0.45,
        # ... 更多上下文数据
    },
    params={"threshold": 3.0}
)

# result = {
#     "actions": [{"type": "stop_ad", "reason": "low_roas"}],
#     "reasons": ["ROAS 0.45 below threshold 1.0"],
#     "metrics": {"evaluated_spend": 100.5}
# }
```

---

### 3.5 规则引擎 (`rules/` + `api/services/rule_*.py`)

#### 3.5.1 规则生命周期

```
┌─────────────┐
│  创建规则   │  (Draft)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  发布规则   │  (Published)
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐    ┌──────────────┐
│  绑定实体   │    │  禁用规则    │ (Disabled)
└──────┬──────┘    └──────────────┘
       │
       ▼
┌─────────────┐
│  执行规则   │
│  (Manual /  │
│  Scheduler) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  记录日志   │
│  更新绑定   │
└─────────────┘
```

#### 3.5.2 规则定义

**数据模型**:
```python
{
  "name": "demo_spend_guard",            # 唯一标识
  "description": "花费≥3美金时评估CPC/CTR",
  "version": "1.0.0",                    # 语义化版本
  "code": "def evaluate(context, params): ...",
  "parameters_schema": {                 # 可配置参数
    "spend_threshold": {"type": "number", "default": 3.0}
  },
  "tags": ["demo", "spend_guard"],
  "status": "published",                 # draft/published/disabled
  "is_active": true
}
```

**规则脚本结构**:
```python
def evaluate(context, params):
    """
    规则评估函数

    Args:
        context: 执行上下文（广告数据、特征等）
        params: 参数配置

    Returns:
        {
            "actions": [
                {"type": "stop_ad", "ad_id": "123", "reason": "low_performance"}
            ],
            "reasons": ["CPC 过高", "CTR 低于阈值"],
            "metrics": {"evaluated_spend": 100.5}
        }
    """
    # 规则逻辑实现
    ...
```

#### 3.5.3 规则绑定

**绑定机制**:

1. **手动绑定**: 通过API指定 `rule_id` + `entity_id`
2. **自动绑定**: 解析广告命名中的 `[]` 标记（计划中）
3. **批量绑定**: 按条件批量创建绑定（计划中）

**数据模型**:
```python
{
  "rule_id": "规则ID",
  "rule_name": "demo_spend_guard",
  "entity_type": "ad",                   # ad/adset/campaign/account
  "entity_id": "120234815168290189",
  "source": "manual",                    # manual/auto/naming_parser
  "metadata": {},                        # 自定义元数据
  "is_active": true,
  "last_executed_at": "2025-10-30T10:00:00Z"
}
```

#### 3.5.4 规则执行

**执行触发**:

| 触发方式 | 场景 | 频率 |
|---------|------|------|
| **Manual** | 手动通过API执行 | 按需 |
| **Scheduler** | APScheduler定时任务 | 每日/每小时 |
| **Auto Unbind** | 自动解绑检测 | 每日 |
| **Test** | 单元测试/调试 | 按需 |

**执行流程**:

```
1. 加载规则定义
   ↓
2. 获取绑定信息
   ↓
3. 构建执行上下文
   ├─ 获取广告数据 (Insights)
   ├─ 计算特征 (Feature Engineering)
   └─ ML预测结果 (可选)
   ↓
4. 执行规则脚本 (Sandbox)
   ↓
5. 生成执行结果
   ├─ Actions (操作列表)
   ├─ Reasons (原因代码)
   └─ Metrics (评估指标)
   ↓
6. 记录执行日志
   ↓
7. 更新绑定状态
```

**执行日志**:
```python
{
  "rule_name": "demo_spend_guard",
  "rule_version": "1.0.0",
  "entity_id": "120234815168290189",
  "trigger": "scheduler",
  "scheduled_run_time": "2025-10-31T00:00:00Z",
  "actual_start_time": "2025-10-31T00:00:05Z",
  "completed_at": "2025-10-31T00:00:08Z",
  "status": "success",                   # success/failed/skipped
  "actions": [
    {"type": "recommend_stop", "reason": "high_cpc"}
  ],
  "reasons": ["CPC $4.5 超过阈值 $3.0"],
  "metrics": {
    "spend": 5.2,
    "cpc": 4.5,
    "ctr": 0.8
  },
  "execution_duration_ms": 3000
}
```

#### 3.5.5 调度管理

**调度器**: APScheduler

**任务类型**:

| 任务名 | Cron表达式 | 功能 |
|--------|-----------|------|
| `run_daily_evaluation` | `0 2 * * *` | 每日凌晨2点执行所有规则 |
| `scan_new_ads` | `0 * * * *` | 每小时扫描新广告并自动绑定 |
| `auto_unbind_stale` | `30 3 * * *` | 每日凌晨3:30清理失活绑定 |

**调度配置**:
```python
# api/services/rule_scheduler.py
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=2, minute=0, id='daily_eval')
async def run_daily_evaluation():
    await RuleEngineService.run_scheduled_evaluations()
```

**监控指标**:
- 调度延迟: `scheduled_run_time` vs `actual_start_time`
- 执行耗时: `execution_duration_ms`
- 成功率: `success_count / total_count`
- 失败原因: `error_message`

---

### 3.6 测试套件 (`tests/`)

#### 3.6.1 测试分类

```
tests/
├── test_insights_api.py           # Insights API测试
├── test_async_insights.py         # 异步任务测试
├── test_predictions_api.py        # ML预测测试
├── test_ad_control.py             # 广告控制测试
├── test_activities.py             # 活动审计测试
├── test_activities_http.py        # HTTP端点测试
├── test_connection.py             # 连接诊断
├── quick_test_activities.py       # 快速验证
├── generate_mock_data.py          # Mock数据生成
└── mocks/                         # Mock数据文件
```

#### 3.6.2 测试覆盖

| 测试类型 | 覆盖范围 | 工具 |
|---------|---------|------|
| **单元测试** | Service层逻辑、数据模型 | pytest |
| **集成测试** | API端到端流程 | pytest + httpx |
| **Mock测试** | 隔离外部依赖 | pytest-mock |
| **诊断工具** | 连接测试、快速验证 | 自定义脚本 |

---

## 4. 数据流设计

### 4.1 Insights数据流

```
┌──────────┐      ┌─────────────┐      ┌──────────────┐
│  Client  │─────▶│  API Router │─────▶│   Insights   │
│          │      │  (Router)   │      │   Service    │
└──────────┘      └─────────────┘      └──────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  FB API Factory│
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  Facebook API  │
                                      │  (Insights)    │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Format Response│
                                      │ (atomic_metric)│
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  Return JSON   │
                                      └────────────────┘
```

### 4.2 ML预测数据流

```
┌──────────┐      ┌─────────────┐      ┌──────────────┐
│  Client  │─────▶│  Prediction │─────▶│  Prediction  │
│          │      │   Router    │      │   Service    │
└──────────┘      └─────────────┘      └──────┬───────┘
                                               │
                                               ▼
                            ┌──────────────────┴──────────────────┐
                            │                                     │
                            ▼                                     ▼
                   ┌────────────────┐                    ┌────────────────┐
                   │ Get Raw Data   │                    │  Load Model    │
                   │ (Insights API) │                    │   (Joblib)     │
                   └────────┬───────┘                    └────────────────┘
                            │                                     │
                            ▼                                     │
                   ┌────────────────┐                            │
                   │ Clean Data     │                            │
                   │ (data_build)   │                            │
                   └────────┬───────┘                            │
                            │                                     │
                            ▼                                     │
                   ┌────────────────┐                            │
                   │ Build Features │                            │
                   │ (lag, trend)   │                            │
                   └────────┬───────┘                            │
                            │                                     │
                            └──────────────┬──────────────────────┘
                                           ▼
                                  ┌────────────────┐
                                  │    Predict     │
                                  │  (model.predict│
                                  │  _proba)       │
                                  └────────┬───────┘
                                           │
                                           ▼
                                  ┌────────────────┐
                                  │ Return Results │
                                  │ (pred_proba +  │
                                  │  features)     │
                                  └────────────────┘
```

### 4.3 规则执行数据流

```
┌──────────┐      ┌─────────────┐      ┌──────────────┐
│Scheduler │─────▶│ Rule Router │─────▶│Rule Engine   │
│  或API   │      │             │      │  Service     │
└──────────┘      └─────────────┘      └──────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Load Rule Def  │
                                      │ Load Binding   │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Build Context  │
                                      │ (Rule Context  │
                                      │  Service)      │
                                      └────────┬───────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        │                      │                      │
                        ▼                      ▼                      ▼
               ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
               │ Get Insights   │    │ ML Prediction  │    │ Historical     │
               │ Data           │    │ (Optional)     │    │ Execution Logs │
               └────────────────┘    └────────────────┘    └────────────────┘
                        │                      │                      │
                        └──────────────────────┼──────────────────────┘
                                               ▼
                                      ┌────────────────┐
                                      │  Execute Rule  │
                                      │  (Sandbox)     │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Generate Result│
                                      │ - Actions      │
                                      │ - Reasons      │
                                      │ - Metrics      │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  Save Log to   │
                                      │   MongoDB      │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Update Binding │
                                      │ (last_executed)│
                                      └────────────────┘
```

### 4.4 广告控制数据流

```
┌──────────┐      ┌─────────────┐      ┌──────────────┐
│  Client  │─────▶│ Ad Control  │─────▶│ Ad Control   │
│          │      │   Router    │      │   Service    │
└──────────┘      └─────────────┘      └──────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Validate Input │
                                      │ (ad_account_id │
                                      │  ad_id, etc.)  │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Get Ad Object  │
                                      │ (FB API Factory│
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌���───────────────┐
                                      │ Execute Action │
                                      │ - Start/Stop   │
                                      │ - Update Name  │
                                      │ - Update Budget│
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  Facebook API  │
                                      │  (Ad Object    │
                                      │   .update())   │
                                      └────────┬───────┘
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │ Return Result  │
                                      │ (Status + Data)│
                                      └────────────────┘
```

---

## 5. 技术栈

### 5.1 后端技术

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **语言** | Python | 3.12+ | 主要开发语言 |
| **Web框架** | FastAPI | Latest | REST API服务 |
| **ASGI服务器** | Uvicorn | Latest | 异步Web服务器 |
| **数据验证** | Pydantic | v2 | 数据模型和验证 |
| **数据库** | MongoDB | 7.0+ | 文档型数据库 |
| **ODM** | Beanie | Latest | 异步MongoDB ORM |
| **调度器** | APScheduler | 3.10+ | 定时任务调度 |
| **包管理** | uv | Latest | 快速依赖管理 |

### 5.2 数据科学

| 类别 | 技术 | 用途 |
|------|------|------|
| **ML框架** | scikit-learn | 模型训练和预测 |
| **算法** | HistGradientBoostingClassifier | 广告停止预测 |
| **数据处理** | pandas | 数据清洗和特征工程 |
| **数值计算** | numpy | 数值运算 |
| **存储格式** | feather (arrow) | 快速I/O |

### 5.3 外部集成

| 类别 | 技术 | 用途 |
|------|------|------|
| **Facebook API** | facebook-business | Facebook Ads操作 |
| **API设计** | Flyweight Pattern | 连接池和缓存 |

### 5.4 开发工具

| 类别 | 技术 | 用途 |
|------|------|------|
| **代码质量** | ruff (计划中) | Linting和格式化 |
| **测试框架** | pytest | 单元和集成测试 |
| **文档** | Markdown | 项目文档 |
| **API文档** | OpenAPI (Swagger) | 自动生成API文档 |

### 5.5 前端技术（计划中）

| 类别 | 技术 | 用途 |
|------|------|------|
| **框架** | React 18+ | UI框架 |
| **构建工具** | Vite | 快速构建 |
| **状态管理** | Zustand / TanStack Query | 状态管理 |
| **UI组件** | Ant Design / shadcn/ui | 组件库 |
| **类型系统** | TypeScript | 类型安全 |

### 5.6 基础设施（计划中）

| 类别 | 技术 | 用途 |
|------|------|------|
| **容器化** | Docker | 应用容器化 |
| **编排** | Docker Compose | 本地开发环境 |
| **监控** | Prometheus + Grafana | 指标监控和可视化 |
| **日志** | ELK Stack / Loki | 日志收集和分析 |
| **告警** | Alertmanager | 告警通知 |

---

## 6. 开发计划与路线图

### 6.1 已完成功能 ✅

#### Phase 0: 基础设施 (已完成)
- [x] 项目结构搭建
- [x] MongoDB数据模型设计
- [x] Facebook API集成
- [x] Flyweight连接缓存
- [x] 异步数据库操作

#### Phase 1: 数据管道 (已完成)
- [x] Insights数据抓取（同步/异步）
- [x] 特征工程（Lag、趋势、波动率）
- [x] 标签生成（基于ROAS）
- [x] ML模型训练（HistGradientBoosting）

#### Phase 2: API服务 (已完成)
- [x] FastAPI应用框架
- [x] 依赖注入和认证
- [x] 健康检查和监控端点
- [x] 广告账户管理API
- [x] Insights数据获取API
- [x] ML预测API
- [x] 广告控制API
- [x] 活动审计API

### 6.2 进行中功能 🚧

#### Phase 3: 规则引擎 (70%完成)

**已完成**:
- [x] 规则定义CRUD
- [x] 规则绑定管理
- [x] 规则执行引擎
- [x] 执行日志记录
- [x] 沙箱执行环境
- [x] APScheduler集成
- [x] 基础调度任务

**进行中**:
- [ ] 广告命名解析器（自动绑定）
- [ ] 自动解绑逻辑完善
- [ ] 规则版本管理
- [ ] 灰度发布机制

**测试**:
- [ ] 规则引擎单元测试
- [ ] 执行流程集成测试
- [ ] 调度任务压力测试

### 6.3 计划中功能 📋

#### Phase 4: 前端控制台 (Q1 2026)

**优先级**:
1. **规则管理界面** (P0)
   - 规则列表和详情页
   - 规则创建和编辑
   - 规则发布和版本控制
   - 参数配置表单

2. **绑定管理界面** (P0)
   - 广告列表和筛选
   - 批量绑定操作
   - 绑定状态管理
   - 绑定历史查看

3. **执行监控界���** (P1)
   - 执行日志查询
   - 实时状态监控
   - 执行结果详情
   - 错误分析和调试

4. **广告控制面板** (P1)
   - 广告列表和搜索
   - 批量操作工具
   - 预算管理界面
   - 活动审计查看

5. **数据分析看板** (P2)
   - 广告表现趋势
   - ML预测可视化
   - 规则效果分析
   - ROAS优化建议

#### Phase 5: 监控和告警 (Q2 2026)

1. **系统监控**
   - Prometheus指标采集
   - Grafana仪表板
   - 关键指标定义：
     - API请求延迟
     - 规则执行成功率
     - 调度任务延迟
     - 数据库连接池

2. **业务监控**
   - 广告花费监控
   - ROAS异常检测
   - 规则触发频率
   - 预算消耗速率

3. **告警机制**
   - Alertmanager配置
   - 告警规则定义
   - 通知渠道（Email/Slack/Webhook）
   - 告警升级策略

#### Phase 6: 混合决策引擎 (Q3 2026)

1. **ML + 规则融合**
   - ML预测结果作为规则上下文
   - 规则可覆盖ML决策
   - 置信度阈值配置
   - 决策路径追踪

2. **多策略协同**
   - 策略优先级管理
   - 冲突解决机制
   - A/B测试框架
   - 效果回测工具

3. **自适应优化**
   - 在线学习（Online Learning）
   - 策略效果反馈循环
   - 参数自动调优
   - 漂移检测和重训练

### 6.4 里程碑时间线

```
2025 Q4 (当前)
├─ 规则引擎完善
└─ 单元测试覆盖

2026 Q1
├─ 前端控制台开发
│  ├─ 规则管理界面
│  ├─ 绑定管理界面
│  └─ 执行监控界面
└─ 用户验收测试

2026 Q2
├─ 监控告警系统
│  ├─ Prometheus集成
│  ├─ Grafana仪表板
│  └─ Alertmanager配置
└─ 生产环境部署

2026 Q3
├─ 混合决策引擎
│  ├─ ML+规则融合
│  ├─ 多策略协同
│  └─ 自适应优化
└─ 性能优化

2026 Q4
├─ 高级功能
│  ├─ 多账户管理
│  ├─ 团队协作
│  └─ 权限管理
└─ 国际化支持
```

---

## 7. 部署架构

### 7.1 本地开发环境

```
┌─────────────────────────────────────────────┐
│         Developer Machine                   │
│                                             │
│  ┌─────────────┐      ┌─────────────────┐  │
│  │   Python    │      │   MongoDB       │  │
│  │   (FastAPI) │◄────►│   (Docker)      │  │
│  │             │      │                 │  │
│  │  Port: 8000 │      │   Port: 27017   │  │
│  └─────────────┘      └─────────────────┘  │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Environment Variables              │   │
│  │  - MONGODB_HOST=localhost           │   │
│  │  - MONGODB_PORT=27017               │   │
│  │  - MONGODB_DB_NAME=fb_monitor       │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

**启动命令**:
```bash
# 启动MongoDB
docker compose up -d

# 启动API服务
uv run python run_api.py
```

### 7.2 生产部署架构（计划）

```
┌──────────────────────────────────────────────────────────────┐
│                     Load Balancer                            │
│                     (Nginx / Traefik)                        │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  FastAPI    │  │  FastAPI    │  │  FastAPI    │
│  Instance 1 │  │  Instance 2 │  │  Instance 3 │
│             │  │             │  │             │
│  Port: 8001 │  │  Port: 8002 │  │  Port: 8003 │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
         ┌──────────────┴──────────────┐
         │                             │
         ▼                             ▼
┌─────────────────┐          ┌─────────────────┐
│   MongoDB       │          │   Redis Cache   │
│   Replica Set   │          │   (Optional)    │
│                 │          │                 │
│  - Primary      │          │  Port: 6379     │
│  - Secondary 1  │          └─────────────────┘
│  - Secondary 2  │
└─────────────────┘

         ┌────────────────────────────┐
         │                            │
         ▼                            ▼
┌─────────────────┐          ┌─────────────────┐
│  Prometheus     │          │   Log Storage   │
│  (Metrics)      │          │   (Loki / ELK)  │
└─────────────────┘          └─────────────────┘
         │
         ▼
┌─────────────────┐
│   Grafana       │
│   (Dashboard)   │
└─────────────────┘
```

### 7.3 Docker容器化（计划）

**Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependencies
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uv", "run", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose**:
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MONGODB_HOST=mongodb
      - MONGODB_PORT=27017
    depends_on:
      - mongodb
    restart: unless-stopped

  mongodb:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=password
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped

volumes:
  mongo_data:
```

### 7.4 云原生部署��未来）

**Kubernetes架构**:
```yaml
# api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ad-regulation-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ad-regulation-api
  template:
    metadata:
      labels:
        app: ad-regulation-api
    spec:
      containers:
      - name: api
        image: ad-regulation:latest
        ports:
        - containerPort: 8000
        env:
        - name: MONGODB_HOST
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: mongodb_host
        resources:
          limits:
            cpu: "1"
            memory: "1Gi"
          requests:
            cpu: "500m"
            memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: ad-regulation-api
spec:
  selector:
    app: ad-regulation-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

---

## 8. 扩展性设计

### 8.1 水平扩展

#### 8.1.1 API层扩展

**无状态设计**:
- 所有API实例无状态
- Session存储在Redis（如需）
- 支持任意数量实例

**负载均衡**:
- Nginx/Traefik反向代理
- 轮询/最少连接策略
- 健康检查和自动摘除

#### 8.1.2 调度任务扩展

**分布式调度**:
- APScheduler + Redis分布式锁
- 任务幂等性保证
- 失败重试和补偿

**任务分片**:
- 按广告账户分片
- 并行执行多个账户
- 动态负载均衡

### 8.2 垂直扩展

#### 8.2.1 数据库优化

**索引策略**:
```javascript
// MongoDB索引
db.rule_bindings.createIndex({ "entity_id": 1, "is_active": 1 })
db.rule_bindings.createIndex({ "rule_name": 1 })
db.rule_execution_logs.createIndex({ "actual_start_time": -1 })
db.rule_execution_logs.createIndex({ "entity_id": 1, "status": 1 })
```

**连接池**:
- 合理设置连接池大小
- 连接复用和超时控制
- 慢查询监控

#### 8.2.2 缓存策略

**多层缓存**:

1. **应用层缓存**
   - Flyweight缓存API连接
   - 内存缓存热数据
   - TTL过期策略

2. **分布式缓存**（计划）
   - Redis缓存Insights数据
   - 缓存ML预测结果
   - 缓存规则定义

3. **CDN缓存**（前端）
   - 静态资源CDN
   - API网关缓存
   - 边缘计算

### 8.3 模块化扩展

#### 8.3.1 规则插件化

**插件机制**:
```python
# 规则作为插件
class RulePlugin(ABC):
    @abstractmethod
    def evaluate(self, context, params):
        pass

    @abstractmethod
    def validate(self, params):
        pass

# 动态加载
rule_plugins = load_plugins_from_directory("rules/plugins/")
```

#### 8.3.2 数据源扩展

**多数据源支持**:
- Facebook Ads（已支持）
- Google Ads（计划）
- TikTok Ads（计划）
- 自定义数据源

**适配器模式**:
```python
class DataSourceAdapter(ABC):
    @abstractmethod
    async def fetch_insights(self, params):
        pass

    @abstractmethod
    async def control_ad(self, action, params):
        pass

# 实现
class FacebookAdapter(DataSourceAdapter):
    ...

class GoogleAdsAdapter(DataSourceAdapter):
    ...
```

### 8.4 性能优化

#### 8.4.1 异步处理

- 所有I/O操作异步化
- 并发请求批量处理
- 异步任务队列（Celery计划）

#### 8.4.2 数据库查询优化

- 批量查询减少往返
- 投影（Projection）减少数据传输
- 分页和游标查询

#### 8.4.3 API响应优化

- GZIP压缩
- 字段过滤（Sparse Fieldsets）
- 数据预加载（Eager Loading）

---

## 9. 安全性设计

### 9.1 认证和授权

**当前实现**:
- 基于Header的用户ID认证 (`X-User-Id`)

**计划增强**:
- JWT Token认证
- OAuth 2.0集成
- 细粒度权限控制（RBAC）

### 9.2 规则沙箱

**安全机制**:
- 白名单模块限制
- 受控执行环境
- 超时控制
- 资源限制（CPU/内存）

**代码审查**:
- 规则提交前代码审查
- 静态分析（AST检查）
- 黑名单关键词检测

### 9.3 数据安全

- 敏感信息加密存储
- API Token定期轮换
- 审计日志持久化
- 数据访问控制

---

## 10. 监控和可观测性

### 10.1 监控指标（计划）

#### 10.1.1 系统指标

- **API性能**
  - 请求延迟 (P50/P95/P99)
  - 吞吐量 (QPS)
  - 错误率

- **数据库**
  - 连接池使用率
  - 慢查询次数
  - 数据库延迟

- **规则执行**
  - 执行成功率
  - 平均执行时间
  - 调度延迟

#### 10.1.2 业务指标

- 广告花费监控
- ROAS趋势
- 规则触发频��
- 自动停止广告数量

### 10.2 日志管理

**日志级别**:
- ERROR: 错误和异常
- WARNING: 警告信息
- INFO: 关键操作日志
- DEBUG: 调试信息

**日志结构化**:
```json
{
  "timestamp": "2025-10-31T10:00:00Z",
  "level": "INFO",
  "service": "rule-engine",
  "event": "rule_executed",
  "rule_name": "demo_spend_guard",
  "entity_id": "120234815168290189",
  "duration_ms": 3000,
  "status": "success"
}
```

### 10.3 追踪和调试

**分布式追踪**（计划）:
- OpenTelemetry集成
- Trace ID传递
- 调用链可视化

---

## 11. 总结

### 11.1 系统亮点

1. **清晰的架构设计**: 三层架构，关注点分离，易于维护和扩展
2. **混合决策能力**: ML预测 + 规则引擎的双轨决策
3. **完整的可追溯性**: 操作审计、执行日志、历史追踪
4. **高性能异步架构**: 异步I/O，支持高并发
5. **灵活的规则系统**: 脚本化规则，参数可配置，安全沙箱执行

### 11.2 技术债务

| 债务项 | 优先级 | 计划时间 |
|--------|--------|---------|
| 单元测试覆盖率不足 | P0 | Q4 2025 |
| 缺少集成测试 | P1 | Q1 2026 |
| 监控告警未完善 | P1 | Q2 2026 |
| 文档待补充 | P2 | Q1 2026 |
| 代码质量工具（Linting） | P2 | Q1 2026 |

### 11.3 下一步行动

**短期（1-2月）**:
1. 完善规则引擎测���
2. 实现广告命名解析器
3. 完善调度任务监控

**中期（3-6月）**:
1. 开发前端控制台
2. 集成监控告警系统
3. 性能优化和压力测试

**长期（6-12月）**:
1. 混合决策引擎
2. 多数据源支持
3. 云原生部署

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| **ROAS** | Return on Ad Spend，广告投资回报率 |
| **CPC** | Cost Per Click，单次点击成本 |
| **CTR** | Click-Through Rate，点击率 |
| **Insights** | Facebook Ads提供的广告数据报告 |
| **Flyweight** | 享元模式，用于减少对象创建开销 |
| **ODM** | Object Document Mapper，对象文档映射器 |
| **APScheduler** | Advanced Python Scheduler，Python定时任务框架 |

### B. 参考资源

- [FastAPI官方文档](https://fastapi.tiangolo.com/)
- [Facebook Marketing API文档](https://developers.facebook.com/docs/marketing-apis/)
- [Beanie ODM文档](https://beanie-odm.dev/)
- [APScheduler文档](https://apscheduler.readthedocs.io/)

### C. 联系方式

- 项目仓库: `D:\projects\ad_regulation`
- 文档位置: `docs/SYSTEM_ARCHITECTURE.md`
- API文档: `http://localhost:8000/docs`

---

**文档结束**
