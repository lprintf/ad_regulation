# 规则引擎 (Rules Engine)

基于注册表的规则系统，支持代码定义规则和自动发现机制。

## 架构概览

```
rules/
├── __init__.py          # 入口，导出核心 API
├── base.py              # RuleBase 基类 + RuleResult
├── registry.py          # 规则注册表 + 自动发现
└── builtin/             # 内置规则
    ├── __init__.py
    ├── ml_auto_stop.py  # ML 自动停止规则
    └── demo_spend_guard.py  # 花费守卫规则
```

## 核心组件

### RuleBase (base.py)

规则基类，所有规则必须继承此类。

```python
from rules.base import RuleBase, RuleResult
from rules.registry import register_rule

@register_rule
class MyRule(RuleBase):
    name = "my_rule"
    description = "规则描述"
    version = "1.0.0"
    tags = ["custom"]
    
    parameters_schema = {
        "threshold": {
            "type": "number",
            "default": 0.5,
            "label": "阈值",
            "description": "判断阈值",
        }
    }
    
    async def evaluate(self) -> RuleResult:
        threshold = self.get_param("threshold", 0.5)
        # 规则逻辑...
        return RuleResult(
            decision="continue",  # continue, stop_recommended, stop_executed, skip, error
            reasons=["表现良好"],
            metrics={"spend": 100.0},
        )
```

### RuleResult

规则执行结果数据类：

| 字段 | 类型 | 说明 |
|------|------|------|
| decision | str | 决策: `continue`, `stop_recommended`, `stop_executed`, `skip`, `error` |
| actions | list[dict] | 建议或执行的操作 |
| reasons | list[str] | 决策原因 |
| metrics | dict | 评估指标 |
| notes | list[str] | 备注信息 |
| logs | list[str] | 执行日志 |

### 注册表 (registry.py)

```python
from rules.registry import (
    RULE_REGISTRY,      # 全局规则字典
    register_rule,      # 注册装饰器
    discover_rules,     # 自动发现
    get_rule_class,     # 获取规则类
    list_rules,         # 列出所有规则元数据
    get_rule_metadata,  # 获取单个规则元数据
)
```

## 内置规则

### ml_auto_stop

基于 ML 模型预测广告停止概率。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| evaluation_date | string | "" | 评估日期 (YYYY-MM-DD)，空为当前日期 |
| lookback_days | integer | 10 | 数据回溯天数 (7-30) |
| stop_probability_threshold | number | 0.7 | 停止概率阈值 (0.5-0.95) |
| dry_run | boolean | true | 试运行模式 |

### demo_spend_guard

素材测试规则，花费达标后评估 CTR/CPC。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| evaluation_date | string | "" | 评估日期 |
| lookback_days | integer | 14 | 数据回溯天数 |
| spend_threshold | number | 3.0 | 最低花费阈值 (USD) |
| ctr_threshold | number | 1.0 | 最低 CTR (%) |
| north_america_cpc_threshold | number | 3.0 | 北美 CPC 阈值 (USD) |
| rest_of_world_cpc_threshold | number | 1.5 | 其他地区 CPC 阈值 (USD) |
| dry_run | boolean | true | 试运行模式 |

## 使用示例

### 初始化规则系统

```python
from rules import init_rules

init_rules()  # 自动发现并注册 builtin 下的规则
```

### 列出可用规则

```python
from rules import list_rules

for rule_meta in list_rules():
    print(f"{rule_meta['name']}: {rule_meta['description']}")
```

### 执行规则

```python
from rules import get_rule_class
from utils.db import RuleBindingDocument

# 获取规则类
rule_cls = get_rule_class("ml_auto_stop")

# 创建规则实例
rule = rule_cls(
    binding=binding_doc,  # RuleBindingDocument
    params={"lookback_days": 14, "dry_run": True}
)

# 执行规则
result = await rule.execute()
print(f"Decision: {result.decision}")
print(f"Reasons: {result.reasons}")
```

## 添加自定义规则

1. 在 `rules/builtin/` 下创建新文件
2. 继承 `RuleBase` 并实现 `evaluate()` 方法
3. 使用 `@register_rule` 装饰器注册

```python
# rules/builtin/my_custom_rule.py
from rules.base import RuleBase, RuleResult
from rules.registry import register_rule

@register_rule
class MyCustomRule(RuleBase):
    name = "my_custom_rule"
    description = "自定义规则"
    version = "1.0.0"
    tags = ["custom"]
    
    parameters_schema = {
        "param1": {"type": "string", "default": "value", "label": "参数1"},
    }
    
    async def evaluate(self) -> RuleResult:
        # 可直接调用服务
        from api.services.insights_service import InsightsService
        
        data = await InsightsService.query_insights_mongo_redis(...)
        
        # 返回结果
        return RuleResult(decision="continue", reasons=["OK"])
```

规则会在下次 `init_rules()` 时自动发现并注册。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /rules/available | 列出所有可用规则 |
| GET | /rules/available/{rule_name} | 获取规则详情 |
| POST | /rules/bindings | 创建规则绑定 |
| GET | /rules/bindings | 列出规则绑定 |
| PATCH | /rules/bindings/{id} | 更新绑定 |
| DELETE | /rules/bindings/{id} | 删除绑定 |
| POST | /rules/execute | 手动触发执行 |
| GET | /rules/executions | 获取执行日志 |
