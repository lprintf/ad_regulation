# 规则系统优化实施进度

## ✅ 已完成（后端部分）

### 1. 规则复制功能
**文件**: `backend/api/models/rules.py`, `backend/api/routers/rules.py`, `backend/api/services/rule_engine_service.py`

**新增 API 端点**:
```
POST /rules/definitions/{rule_id}/clone
```

**功能**:
- 克隆现有规则
- 修改规则名称和版本
- 覆盖默认参数（parameter_overrides）
- 保留原规则的代码和标签
- 新规则默认为 draft 状态

**示例请求**:
```json
POST /rules/definitions/67890/clone
{
  "new_name": "spend_guard_保守",
  "new_version": "1.0.1",
  "parameter_overrides": {
    "spend_threshold": 2.0,
    "ctr_threshold": 0.8,
    "dry_run": false
  },
  "description": "保守策略：快速止损，适用于新账户",
  "created_by": "user123"
}
```

---

### 2. 时间旅行测试参数
**文件**: `backend/api/models/rules.py`

**RuleExecutionRequest 新增字段**:
```python
test_mode: bool = False              # 启用测试模式
test_date: date | None = None        # 模拟日期 (YYYY-MM-DD)
test_lookback_days: int | None = None # 覆盖回看天数
```

**用途**:
- 使用历史数据回测规则
- 不记录执行日志（测试模式）
- 验证参数设置的合理性

**示例请求**:
```json
POST /rules/execute
{
  "binding_id": "abc123",
  "params": {
    "spend_threshold": 5.0,
    "ctr_threshold": 1.2
  },
  "test_mode": true,
  "test_date": "2025-11-15",
  "test_lookback_days": 7
}
```

---

### 3. 增强的参数 Schema
**文件**: `backend/rules/scripts/demo_spend_guard.py`

**完整的参数定义**:
```python
PARAMETERS_SCHEMA = {
    "spend_threshold": {
        "type": "number",
        "label": "花费阈值（美元）",           # 显示名称
        "description": "广告花费达到此金额后才开始评估",  # 详细说明
        "default": 3.0,                    # 默认值
        "min": 0.0,                        # 最小值
        "max": 1000.0,                     # 最大值
        "step": 0.5,                       # 步进值
        "unit": "USD",                     # 单位
        "required": True,                   # 是否必填
        "hint": "建议设置为 3-10 美元，避免过早判断"  # 业务提示
    },
    # ... 其他参数
}
```

**支持的字段**:
- `label`: 用户友好的显示名称
- `description`: 参数的业务含义
- `min` / `max` / `step`: 数值范围和步进
- `unit`: 单位（USD, %, 天等）
- `hint`: 业务最佳实践提示
- `required`: 是否必填

**参数类型**:
- `number`: 浮点数（如 3.5）
- `integer`: 整数（如 7）
- `boolean`: 布尔值（true/false）

---

## 🚧 待实施（前端部分）

### 4. 智能参数表单组件
**目标文件**: `frontend/src/features/rule-bindings/SmartParameterForm.tsx`

**功能**:
- 根据 schema 自动生成表单
- 显示 label、description、unit、hint
- 实时验证（min/max/step/required）
- 支持 number、integer、boolean 类型

### 5. 规则复制 UI
**目标文件**: `frontend/src/features/rule-definitions/RuleDefinitionsPage.tsx`

**功能**:
- 每个规则添加"复制"按钮
- 弹出表单：新名称、版本、参数覆盖
- 调用 `POST /rules/definitions/{id}/clone`

### 6. 时间旅行测试 UI
**目标文件**: `frontend/src/features/rule-bindings/RuleBindingTestPanel.tsx`

**功能**:
- 绑定详情页添加"运行测试"按钮
- 显示日期选择器（模拟时间点）
- 显示参数调整表单
- 显示测试结果（actions, reasons, metrics）

### 7. Insights 页面快捷托管
**目标文件**: `frontend/src/features/insights-data/InsightsDataPage.tsx`

**功能**:
- 每行数据添加"托管"按钮
- 点击后打开绑定表单（预填 entity_id 和 account_id）
- 选择规则 + 调整参数
- 创建绑定

---

## 📊 总体进度

| 任务 | 状态 | 预计剩余时间 |
|-----|------|------------|
| 1. 规则复制功能（API） | ✅ 完成 | - |
| 2. 时间旅行测试参数 | ✅ 完成 | - |
| 3. 增强参数 schema | ✅ 完成 | - |
| 4. 智能参数表单组件 | 🔵 待开始 | 2-3小时 |
| 5. 规则复制 UI | 🔵 待开始 | 1小时 |
| 6. 时间旅行测试 UI | 🔵 待开始 | 2小时 |
| 7. Insights 快捷托管 | 🔵 待开始 | 1小时 |

**当前进度**: 40% (后端完成 100%, 前端 0%)

---

## 🧪 测试后端功能

### 测试规则复制
```bash
# 1. 获取现有规则 ID
curl -X GET "http://localhost:8000/api/rules/definitions" \
  -H "X-User-Id: test-user"

# 2. 克隆规则
curl -X POST "http://localhost:8000/api/rules/definitions/{rule_id}/clone" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: test-user" \
  -d '{
    "new_name": "spend_guard_test",
    "new_version": "1.0.1",
    "parameter_overrides": {
      "spend_threshold": 5.0,
      "ctr_threshold": 1.5
    },
    "description": "测试克隆规则",
    "created_by": "test-user"
  }'
```

### 测试时间旅行
```bash
curl -X POST "http://localhost:8000/api/rules/execute" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: test-user" \
  -d '{
    "binding_id": "your-binding-id",
    "test_mode": true,
    "test_date": "2025-11-15",
    "test_lookback_days": 7
  }'
```

---

## 📝 下一步

1. **智能参数表单组件**（最优先）
   - 这是核心体验改进
   - 其他功能都依赖这个组件

2. **规则绑定测试面板**
   - 集成智能表单 + 时间旅行测试
   - 让用户能方便地回测参数

3. **规则复制 UI**
   - 简单的表单弹窗
   - 依赖智能表单组件

4. **Insights 快捷托管**
   - 集成现有的 RuleBindingModal
   - 预填字段即可

---

## 🎯 核心价值

完成后用户可以：
1. **快速复制规则** → 调整参数 → 创建不同策略版本（保守/平衡/激进）
2. **时间旅行测试** → 用历史数据验证参数 → 避免误判
3. **智能表单** → 看到参数说明和建议 → 配置时间从 5 分钟降到 1 分钟
4. **一键托管** → 在 Insights 页面直接绑定规则 → 操作流畅
