# 规则系统重构方案

**文档版本**: 2.0  
**更新日期**: 2025-12-06  
**状态**: ✅ 已完成实施  
**前提条件**: 不允许用户自定义规则代码，所有规则由开发者编写

> **实施完成 (2025-12-06)**:
> - 规则系统已迁移到代码注册模式
> - 移除 metadata 字段，使用 ad_account_id + rule_config_id
> - 前端规则管理页已合并规则定义和规则绑定功能
> - 支持从规则详情页和广告详情页查看已绑定实体和执行日志

---

## 一、重构目标

| 目标 | 说明 |
|------|------|
| **简化架构** | 移除沙箱执行层，直接使用 Python 模块 |
| **ML 深度集成** | 规则可直接 import 和调用 ML 模型 |
| **Async 原生支持** | 规则可直接 await API 调用 |
| **类型安全** | IDE 完整支持，类型检查 |
| **热重载** | 开发模式下文件修改即生效 |

---

## 二、架构对比

### 2.1 当前架构（Before）

```
┌─────────────────────────────────────────────────────────────┐
│                     当前规则执行流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Scheduler 触发                                           │
│         ↓                                                    │
│  2. 从 MongoDB 读取 RuleDefinitionDocument.code              │
│         ↓                                                    │
│  3. RuleContextService 预构建 context（包括 ML 预测）          │
│         ↓                                                    │
│  4. rule_sandbox.execute_rule_script(code, context, params)  │
│         ↓                                                    │
│  5. exec(code) → evaluate(context, params)                   │
│         ↓                                                    │
│  6. 保存 RuleExecutionLogDocument                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘

问题:
- exec() 每次重编译代码
- 沙箱限制无法直接 import
- ML 预测必须预注入 context
- 不支持 async/await
- 无 IDE 支持
```

### 2.2 目标架构（After）

```
┌─────────────────────────────────────────────────────────────┐
│                     重构后规则执行流程                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Scheduler 触发                                           │
│         ↓                                                    │
│  2. 从 RULE_REGISTRY 获取规则类                               │
│         ↓                                                    │
│  3. 实例化规则: rule = RuleClass(binding, params)            │
│         ↓                                                    │
│  4. await rule.execute()  ← 规则内部自行获取数据              │
│         ↓                                                    │
│  5. 保存 RuleExecutionLogDocument                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘

优势:
- 模块只加载一次（importlib 缓存）
- 直接 import ML 模型、API 客户端
- 原生 async/await 支持
- 完整 IDE 类型提示
```

---

## 三、目录结构设计

```
backend/
├── rules/
│   ├── __init__.py           # 规则注册表 RULE_REGISTRY
│   ├── base.py               # 基类 RuleBase
│   ├── registry.py           # 注册装饰器和发现逻辑
│   │
│   ├── builtin/              # 内置规则
│   │   ├── __init__.py
│   │   ├── demo_spend_guard.py
│   │   └── ml_auto_stop.py
│   │
│   └── scripts/              # [废弃] 旧规则脚本，迁移后删除
│       └── ...
│
├── api/
│   ├── services/
│   │   ├── rule_engine_service.py   # 重构：使用 RULE_REGISTRY
│   │   ├── rule_context_service.py  # [废弃] 逻辑移入规则内部
│   │   └── rule_scheduler.py        # 保留，调整调用方式
│   │
│   └── models/
│       └── rules.py                 # 简化：移除 code 字段
│
├── utils/
│   └── rule_sandbox.py              # [删除]
│
└── ...
```

---

## 四、核心组件设计

### 4.1 规则基类 `rules/base.py`

```python
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from utils.db import RuleBindingDocument


@dataclass
class RuleResult:
    """规则执行结果"""
    decision: str                              # continue, stop_recommended, stop_executed, skip, error
    actions: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


class RuleBase(ABC):
    """规则基类 - 所有规则必须继承此类"""

    # 类级别元数据（子类必须定义）
    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    tags: ClassVar[list[str]] = []

    # 参数 schema（用于前端渲染和验证）
    parameters_schema: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        binding: RuleBindingDocument | None = None,
        params: dict[str, Any] | None = None,
    ):
        self.binding = binding
        self.params = params or {}
        self.logger = logging.getLogger(f"rule.{self.name}")
        self._logs: list[str] = []

    def log(self, message: str, level: str = "INFO"):
        """记录执行日志"""
        entry = f"[{level}] {message}"
        self._logs.append(entry)
        getattr(self.logger, level.lower(), self.logger.info)(message)

    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数，优先使用运行时 params，其次使用 schema 默认值"""
        if key in self.params:
            return self.params[key]
        schema = self.parameters_schema.get(key, {})
        return schema.get("default", default)

    @abstractmethod
    async def evaluate(self) -> RuleResult:
        """
        执行规则评估 - 子类必须实现

        规则内部可以:
        - 直接调用 InsightsService 获取数据
        - 直接加载 ML 模型进行预测
        - 直接调用 Facebook API
        - 使用 async/await
        """
        raise NotImplementedError

    async def execute(self) -> RuleResult:
        """执行入口（带日志收集）"""
        try:
            result = await self.evaluate()
            result.logs = self._logs
            return result
        except Exception as exc:
            self.log(f"Rule execution failed: {exc}", "ERROR")
            return RuleResult(
                decision="error",
                reasons=[f"Execution error: {exc}"],
                logs=self._logs,
            )
```

### 4.2 规则注册表 `rules/registry.py`

```python
from __future__ import annotations

import importlib
import pkgutil
from typing import Type

from rules.base import RuleBase

# 全局规则注册表
RULE_REGISTRY: dict[str, Type[RuleBase]] = {}


def register_rule(cls: Type[RuleBase]) -> Type[RuleBase]:
    """装饰器：注册规则到全局注册表"""
    if not hasattr(cls, 'name') or not cls.name:
        raise ValueError(f"Rule class {cls.__name__} must define 'name' class variable")
    
    if cls.name in RULE_REGISTRY:
        raise ValueError(f"Rule '{cls.name}' already registered")
    
    RULE_REGISTRY[cls.name] = cls
    return cls


def discover_rules(package_name: str = "rules.builtin") -> None:
    """自动发现并导入指定包下的所有规则模块"""
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package_name}.{module_name}")


def get_rule_class(name: str) -> Type[RuleBase]:
    """获取规则类"""
    if name not in RULE_REGISTRY:
        raise ValueError(f"Rule '{name}' not found in registry")
    return RULE_REGISTRY[name]


def list_rules() -> list[dict]:
    """列出所有已注册规则的元数据"""
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "version": cls.version,
            "tags": cls.tags,
            "parameters_schema": cls.parameters_schema,
        }
        for cls in RULE_REGISTRY.values()
    ]
```

### 4.3 示例规则 `rules/builtin/ml_auto_stop.py`

```python
"""
ML 自动停止规则 - 基于机器学习模型预测广告表现
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, ClassVar

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@register_rule
class MLAutoStopRule(RuleBase):
    """ML 自动停止规则"""

    name: ClassVar[str] = "ml_auto_stop"
    description: ClassVar[str] = "基于 ML 模型预测广告停止概率，自动评估广告表现"
    version: ClassVar[str] = "2.0.0"
    tags: ClassVar[list[str]] = ["ml", "auto_stop", "prediction"]

    parameters_schema: ClassVar[dict[str, Any]] = {
        "evaluation_date": {
            "type": "string",
            "label": "评估日期",
            "description": "规则评估的时间点，格式：YYYY-MM-DD",
            "default": "",
            "required": False,
        },
        "lookback_days": {
            "type": "integer",
            "default": 10,
            "label": "数据回溯天数",
            "min": 7,
            "max": 30,
        },
        "stop_probability_threshold": {
            "type": "number",
            "default": 0.7,
            "label": "停止概率阈值",
            "min": 0.5,
            "max": 0.95,
        },
        "dry_run": {
            "type": "boolean",
            "default": True,
            "label": "试运行模式",
        },
    }

    async def evaluate(self) -> RuleResult:
        """执行 ML 预测评估"""
        from api.services.insights_service import InsightsService
        from baseline.data_build import build_features, clean_data
        from baseline.train_tools import load_model
        import pandas as pd
        import numpy as np
        import os

        # 获取参数
        lookback_days = self.get_param("lookback_days", 10)
        threshold = self.get_param("stop_probability_threshold", 0.7)
        dry_run = self.get_param("dry_run", True)

        # 获取绑定信息
        if not self.binding:
            return RuleResult(decision="error", reasons=["No binding provided"])

        ad_account_id = self.binding.metadata.get("ad_account_id")
        ad_id = self.binding.entity_id

        self.log(f"Evaluating ad {ad_id} with lookback={lookback_days} days")

        # 确定评估日期
        eval_date_str = self.get_param("evaluation_date")
        if eval_date_str:
            reference_date = datetime.strptime(eval_date_str, "%Y-%m-%d")
        else:
            reference_date = datetime.utcnow()

        # 直接调用 InsightsService 获取数据
        since = reference_date - timedelta(days=lookback_days)
        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since.strftime("%Y-%m-%d"),
                until=reference_date.strftime("%Y-%m-%d"),
                level="ad",
                time_increment=1,
                object_ids=[ad_id],
            )
        except Exception as exc:
            self.log(f"Failed to fetch insights: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Data fetch failed: {exc}"])

        insights_records = insights_data.get("insights", [])
        if not insights_records:
            self.log("No insights data available", "WARNING")
            return RuleResult(decision="skip", reasons=["No insights data"])

        # 直接加载 ML 模型
        model_path = "models/model.feather"
        if not os.path.exists(model_path):
            self.log(f"Model not found: {model_path}", "ERROR")
            return RuleResult(decision="error", reasons=["ML model not found"])

        # 构建特征并预测
        df = self._build_dataframe(insights_records, ad_id)
        df_clean = clean_data(df)
        if df_clean.empty:
            return RuleResult(decision="skip", reasons=["Insufficient data after cleaning"])

        features = build_features(df_clean, iloc_index=-1)
        model_package = load_model(model_path)
        model = model_package["model"] if isinstance(model_package, dict) else model_package
        feature_names = model_package.get("feature_names", []) if isinstance(model_package, dict) else []

        X = features[feature_names].fillna(0) if feature_names else features.drop(["ad_id", "date"], axis=1).fillna(0)
        stop_proba = float(model.predict_proba(X)[0, 1])

        self.log(f"ML prediction: stop_probability={stop_proba:.2%}")

        # 决策逻辑
        metrics = {"ml_stop_probability": stop_proba}
        actions = []
        reasons = []

        if stop_proba >= threshold:
            decision = "stop_recommended" if dry_run else "stop_executed"
            reasons.append(f"停止概率 {stop_proba:.1%} >= 阈值 {threshold:.1%}")
            if not dry_run:
                actions.append({
                    "action": "pause_ad",
                    "entity_id": ad_id,
                    "confidence": stop_proba,
                })
        else:
            decision = "continue"
            reasons.append(f"停止概率 {stop_proba:.1%} < 阈值 {threshold:.1%}")

        return RuleResult(
            decision=decision,
            actions=actions,
            reasons=reasons,
            metrics=metrics,
        )

    def _build_dataframe(self, records: list[dict], ad_id: str) -> pd.DataFrame:
        """将 insights 记录转换为 DataFrame"""
        import pandas as pd
        rows = []
        for record in records:
            m = record.get("metrics", {})
            rows.append({
                "ad_id": ad_id,
                "date": record.get("date"),
                "spend": float(m.get("spend") or 0),
                "impressions": int(m.get("impressions") or 0),
                "clicks": int(m.get("clicks") or 0),
                # ... 其他字段
            })
        return pd.DataFrame(rows)
```

### 4.4 重构后的 RuleEngineService

```python
# api/services/rule_engine_service.py (核心变更部分)

from rules.registry import get_rule_class, discover_rules, list_rules

class RuleEngineService:
    
    @staticmethod
    async def execute_rule(request: RuleExecutionRequest) -> RuleExecutionLogResponse:
        """执行规则 - 重构后版本"""
        
        # 获取绑定
        binding = await RuleBindingDocument.get(request.binding_id)
        if not binding:
            raise ValueError("Binding not found")

        # 从注册表获取规则类（不再从数据库读取代码）
        rule_class = get_rule_class(binding.rule_name)
        
        # 实例化规则
        rule = rule_class(binding=binding, params=request.params)
        
        # 执行（原生 async）
        start_time = datetime.utcnow()
        result = await rule.execute()
        completed_at = datetime.utcnow()
        
        # 保存执行日志
        log_doc = RuleExecutionLogDocument(
            rule_name=rule.name,
            rule_version=rule.version,
            binding=binding,
            status="success" if result.decision != "error" else "failed",
            actions=result.actions,
            reasons=result.reasons,
            metrics=result.metrics,
            execution_logs=result.logs,
            execution_duration_ms=int((completed_at - start_time).total_seconds() * 1000),
            # ...
        )
        await log_doc.insert()
        
        return _serialize_execution(log_doc)

    @staticmethod
    async def list_available_rules() -> list[dict]:
        """列出所有可用规则（从注册表读取，不再从数据库）"""
        return list_rules()
```

---

## 五、数据库模型变更

### 5.1 保留的 Document

```python
# RuleBindingDocument - 保留，略作调整
class RuleBindingDocument(Document):
    rule_name: str                    # 规则名称（用于查找注册表）
    entity_type: str                  # ad/adset/campaign/account
    entity_id: str
    is_active: bool = True
    metadata: dict = {}               # 包含 ad_account_id 等
    params_override: dict = {}        # 参数覆盖（新增，替代原 metadata 中的参数）
    created_at: datetime
    updated_at: datetime
    last_executed_at: datetime | None

# RuleExecutionLogDocument - 保留
class RuleExecutionLogDocument(Document):
    rule_name: str
    rule_version: str
    binding: Link[RuleBindingDocument] | None
    # ... 其他字段保持不变
```

### 5.2 废弃的 Document

```python
# RuleDefinitionDocument - 废弃
# 理由：代码不再存数据库，元数据由 Python 类定义
```

---

## 六、迁移步骤

### Phase 1: 准备工作（无破坏性变更）

1. **创建新目录结构**
   ```bash
   mkdir -p backend/rules/builtin
   touch backend/rules/__init__.py
   touch backend/rules/base.py
   touch backend/rules/registry.py
   ```

2. **实现基类和注册表**
   - 编写 `RuleBase` 抽象类
   - 编写 `register_rule` 装饰器
   - 编写 `discover_rules` 自动发现

3. **迁移现有规则**
   - 将 `rules/scripts/ml_auto_stop.py` 改写为类形式
   - 将 `rules/scripts/demo_spend_guard.py` 改写为类形式

### Phase 2: 双轨运行（兼容期）

4. **修改 RuleEngineService**
   - 优先从 `RULE_REGISTRY` 查找规则
   - 若未找到，回退到数据库 + 沙箱（兼容）

5. **修改前端（可选）**
   - 规则列表 API 改为读取注册表
   - 移除"创建规则"功能（如果有）

### Phase 3: 清理（移除旧代码）

6. **删除废弃代码**
   - 删除 `utils/rule_sandbox.py`
   - 删除 `RuleDefinitionDocument`
   - 删除 `rules/scripts/` 目录
   - 删除 `RuleContextService`（逻辑已移入规则内部）

7. **更新 API**
   - 移除 `/rules` CRUD 端点（改为只读列表）
   - 更新 `/rules/bindings` 保留

---

## 七、前端影响

| 功能 | 变更 |
|------|------|
| 规则列表 | API 改为 `/rules/available`，返回注册表元数据 |
| 规则详情 | 只读展示（name, description, parameters_schema） |
| 创建规则 | **移除**（如果有此功能） |
| 编辑规则代码 | **移除** |
| 规则绑定 | 保留，下拉选择可用规则名 |
| 参数配置 | 保留，基于 `parameters_schema` 渲染表单 |
| 执行日志 | 保留 |

---

## 八、风险与回滚

### 风险

| 风险 | 缓解措施 |
|------|---------|
| 规则迁移错误 | Phase 2 双轨运行，可随时回退 |
| 热重载问题 | Granian 已支持，无额外风险 |
| 现有绑定失效 | 确保新规则 `name` 与旧 `rule_name` 一致 |

### 回滚方案

```bash
# Phase 3 之前可随时回滚
git checkout -- backend/api/services/rule_engine_service.py
# 重启服务即可
```

---

## 九、时间估算

| 阶段 | 预计耗时 | 说明 |
|------|---------|------|
| Phase 1 | 2-3 天 | 基础设施 + 规则迁移 |
| Phase 2 | 1-2 天 | 双轨运行 + 测试 |
| Phase 3 | 1 天 | 清理 + 文档更新 |
| **总计** | **4-6 天** | |

---

## 十、数据库维护

### 清除旧版绑定数据

重构后 `RuleBindingDocument` 结构变更（移除 `metadata`，新增 `ad_account_id` 等广告层级字段），旧数据不兼容需清除：

```bash
# 清除 rule_bindings 集合
export $(grep -v '^#' .env | xargs) && \
docker exec -it fb-http-mongodb-1 mongosh $MONGODB_DB_NAME \
  -u $MONGO_INITDB_ROOT_USERNAME \
  -p $MONGO_INITDB_ROOT_PASSWORD \
  --authenticationDatabase admin \
  --eval "db.rule_bindings.deleteMany({})"
```

---

## 十一、相关文档

- [当前规则系统代码](../../backend/utils/rule_sandbox.py)
- [现有规则脚本](../../backend/rules/scripts/)
- [重构准备概览](./README.md)
