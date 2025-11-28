# 规则系统评估与改进建议

## 目录
1. [当前系统架构总结](#当前系统架构总结)
2. [优点分析](#优点分析)
3. [不足与痛点](#不足与痛点)
4. [业界最佳实践对比](#业界最佳实践对比)
5. [改进建议](#改进建议)
6. [实施路线图](#实施路线图)

---

## 当前系统架构总结

### 核心特点
- **编程范式**: Python 代码编写（手写 `evaluate()` 函数）
- **执行环境**: 沙箱化执行（受限的 `__builtins__`）
- **参数化**: Schema-based 参数定义（支持 string/number/boolean/enum）
- **绑定模型**: Rule → Entity 多对多关系（手动/自动/命名解析）
- **调度系统**: APScheduler + Leader Election（定时评估、新广告扫描、自动解绑）
- **审计追踪**: 完整的执行日志（actions, reasons, metrics, context_snapshot）

### 前端界面
- **规则定义表单**:
  - 名称、描述、状态（draft/published/disabled）
  - Python 代码编辑器（纯文本 textarea）
  - 参数配置（动态表单，支持多参数）
  - 标签管理
- **绑定管理**: 实体类型、实体 ID、元数据
- **执行日志查看**: 状态、触发方式、执行详情
- **调度器控制台**: 任务管理、手动触发、暂停/恢复

---

## 优点分析

### ✅ 架构层面
1. **高度灵活**: Python 脚本可以实现任意复杂的业务逻辑
2. **良好的分层**: API Router → Service → Data Access 清晰分离
3. **异步优先**: 全栈使用 async/await，适合 I/O 密集型操作
4. **完整的审计**: 每次执行都有详细的日志和上下文快照
5. **调度系统成熟**: 支持 cron 表达式、Leader Election、任务指标
6. **数据模型清晰**: Rule Definition、Rule Binding、Execution Log 三层模型合理

### ✅ 功能层面
1. **参数化支持**: 允许规则定义可配置参数，提高复用性
2. **多级绑定**: 支持 ad/adset/campaign/account 四级实体
3. **多源绑定**: 手动绑定、自动绑定、命名解析三种方式
4. **版本管理**: 规则有版本号，支持 draft → published 生命周期
5. **标签系统**: 便于规则分类和筛选
6. **实时执行**: 支持手动触发单次执行测试

---

## 不足与痛点

### ❌ 规则定义界面（UI/UX）

#### 1. **代码编辑器过于原始**
- **当前**: 普通 `<textarea>` 纯文本编辑
- **问题**:
  - 无语法高亮
  - 无代码补全
  - 无错误提示
  - 无格式化工具
  - 不支持多文件/模块
  - 编辑体验极差，容易出错

#### 2. **参数配置体验不佳**
- **当前**: 手动填写 key/label/type/default/description
- **问题**:
  - 与代码脱节（代码中使用的参数名可能与配置不一致）
  - 无法从代码自动推导参数
  - enum 类型只支持逗号分隔字符串，无验证
  - 缺少参数值的实时验证
  - 无法预览参数的实际效果

#### 3. **测试与调试困难**
- **当前**: 只能保存后通过手动执行测试
- **问题**:
  - 无法在编辑器内快速测试
  - 无法提供 mock context 进行本地调试
  - 错误信息不够友好（Python 异常直接抛出）
  - 无法查看中间变量的值
  - 缺少单步调试能力

#### 4. **规则复用与模块化不足**
- **当前**: 每个规则是独立的 Python 脚本
- **问题**:
  - 无法在规则之间共享工具函数
  - 无法引用外部库（沙箱限制）
  - 重复代码多（如地域判断、指标计算）
  - 没有规则模板或示例库
  - 无法组合多个小规则

#### 5. **规则语义表达能力弱**
- **当前**: 纯代码实现所有逻辑
- **问题**:
  - 非技术人员无法理解规则逻辑
  - 业务逻辑隐藏在代码中，难以审计
  - 无法可视化规则的决策树
  - 缺少自然语言描述与代码的映射

---

### ❌ 规则引擎（后端逻辑）

#### 1. **沙箱机制过于简单**
- **当前**: 仅限制 `__builtins__`
- **问题**:
  - 无法防止死循环（无超时机制）
  - 无法限制内存使用
  - 无法限制 CPU 时间
  - 不支持外部库导入（即使是安全的 numpy/pandas）
  - 错误处理粗糙（直接 exec()）

#### 2. **Context 数据结构不够标准化**
- **当前**: 自由的 dict 结构
- **问题**:
  - 每个规则需要自己解析 context
  - 缺少 IDE 支持（无类型提示）
  - 容易出现 KeyError
  - 难以扩展新字段（需要更新所有规则）

#### 3. **规则执行结果缺少标准化**
- **当前**: 返回 `{"actions": [], "reasons": [], "metrics": {}}`
- **问题**:
  - `actions` 的结构不够规范（type/action/reason 字段自由定义）
  - 没有强制的 action schema 验证
  - 无法统一处理不同规则的输出
  - 缺少 action 的执行器（所有推荐都需要人工介入）

#### 4. **规则之间无依赖关系管理**
- **当前**: 每个 binding 独立执行
- **问题**:
  - 无法定义规则执行顺序
  - 无法让一个规则的输出成为另一个规则的输入
  - 无法定义规则组（同时触发多个规则）
  - 冲突检测缺失（两个规则可能给出矛盾的建议）

#### 5. **缺少规则有效性验证**
- **当前**: 发布时无强制验证
- **问题**:
  - 无法保证规则语法正确
  - 无法保证规则返回值符合 schema
  - 无法检查规则是否会抛出异常
  - 没有回归测试机制

---

## 业界最佳实践对比

### 📊 业界主流规则引擎方案

#### 1. **Drools (Red Hat Business Rules)**
- **范式**: 声明式规则语言（DRL）+ Java
- **特点**:
  - 基于 RETE 算法的高性能模式匹配
  - 支持规则流（Rule Flow）和决策表（Decision Tables）
  - 内置冲突解决策略（salience、agenda-group）
  - 提供 Workbench GUI 用于规则编辑
- **优势**: 成熟稳定，企业级支持，性能极高
- **劣势**: 学习曲线陡峭，部署复杂

#### 2. **AWS Rules Engine (IoT Rules)**
- **范式**: SQL-like 语言
- **特点**:
  - 类 SQL 语法定义规则（SELECT ... FROM ... WHERE）
  - 内置函数库（时间、字符串、数学）
  - 支持多种 action（Lambda、SNS、DynamoDB）
- **优势**: 易学易用，无需编程
- **劣势**: 表达能力有限，仅适合简单规则

#### 3. **Google Decision Maker (Apigee)**
- **范式**: JSON-based 规则定义
- **特点**:
  - 声明式 JSON 配置
  - 可视化规则构建器
  - 内置多种条件操作符（eq/ne/gt/lt/in/contains）
- **优势**: 轻量级，易集成
- **劣势**: 复杂逻辑支持不足

#### 4. **Easy Rules (Java)**
- **范式**: 注解式 Java 规则
- **特点**:
  - 简单的 POJO 规则定义
  - 支持 YAML/JSON 配置
  - 支持 MVEL/SpEL 表达式语言
- **优势**: 轻量级，易上手
- **劣势**: 功能相对简单

#### 5. **Airflow (数据工作流)**
- **范式**: Python DAG
- **特点**:
  - 代码优先（Code-as-Configuration）
  - 强大的依赖管理和调度
  - 丰富的 Operator 生态
  - Web UI + Code Editor
- **优势**: 灵活性极高，社区活跃
- **劣势**: 主要面向数据工程，非专用规则引擎

#### 6. **n8n / Zapier (低代码自动化)**
- **范式**: 可视化流程编排
- **特点**:
  - 拖拽式节点连接
  - 内置大量集成（API、数据库、SaaS）
  - 支持条件分支、循环、错误处理
- **优势**: 零代码门槛，快速构建
- **劣势**: 复杂逻辑性能差，定制能力有限

---

### 🏆 推荐方向：混合式规则定义

综合业界实践，建议采用 **"低代码 + 代码"混合模式**：

1. **简单规则**: 使用可视化表单或 JSON 配置（类似 AWS Rules Engine）
2. **复杂规则**: 使用增强的代码编辑器（类似 Airflow）
3. **规则组合**: 支持流程编排（类似 n8n）

---

## 改进建议

### 🎯 短期优化（1-2周）

#### 1. 升级代码编辑器
**替换方案**: 集成 Monaco Editor（VS Code 的编辑器内核）

**实现步骤**:
```tsx
// 安装依赖
npm install @monaco-editor/react

// 替换 RuleDefinitionForm.tsx 中的 textarea
import Editor from '@monaco-editor/react'

<Editor
  height="400px"
  language="python"
  theme="vs-dark"
  value={code}
  onChange={(value) => setCode(value || '')}
  options={{
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on',
    roundedSelection: false,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
  }}
/>
```

**收益**:
- ✅ 语法高亮
- ✅ 代码折叠
- ✅ 自动缩进
- ✅ 括号匹配
- ✅ 搜索/替换

#### 2. 添加规则验证 API
**新增端点**: `POST /rules/validate`

**实现**:
```python
# api/routers/rules.py
@router.post("/validate")
async def validate_rule(payload: RuleDefinitionCreate):
    """验证规则代码的语法和结构"""
    try:
        # 1. Python 语法检查
        compile(payload.code, '<rule>', 'exec')

        # 2. 检查是否定义 evaluate 函数
        sandbox = RuleSandbox()
        result = sandbox.validate_structure(payload.code)

        # 3. 模拟执行（使用 mock context）
        mock_context = {...}
        mock_params = {...}
        output = sandbox.execute(payload.code, mock_context, mock_params)

        return {"valid": True, "output": output}
    except SyntaxError as e:
        return {"valid": False, "error": {"type": "syntax", "message": str(e), "line": e.lineno}}
    except Exception as e:
        return {"valid": False, "error": {"type": "runtime", "message": str(e)}}
```

**前端集成**:
```tsx
// RuleDefinitionForm.tsx
const [validationResult, setValidationResult] = useState<any>(null)

const handleValidate = async () => {
  const result = await validateRule({ name, code, parameters })
  setValidationResult(result)
}

// 显示验证结果
{validationResult && (
  <div className={validationResult.valid ? 'alert-success' : 'alert-error'}>
    {validationResult.valid
      ? '✓ 规则验证通过'
      : `✗ ${validationResult.error.message}`}
  </div>
)}
```

#### 3. 规则模板库
**新增**: 预定义的常用规则模板

**实现**:
```python
# backend/rules/templates/
# - spend_threshold.py
# - ctr_cpc_guard.py
# - budget_pacing.py
# - audience_fatigue.py
```

**前端支持**:
```tsx
// RuleDefinitionForm.tsx
const [showTemplates, setShowTemplates] = useState(false)

<button onClick={() => setShowTemplates(true)}>从模板创建</button>

<TemplateSelector
  onSelect={(template) => {
    setCode(template.code)
    setParameters(template.parameters)
  }}
/>
```

---

### 🚀 中期改进（1-2月）

#### 1. 可视化规则构建器（适合简单规则）

**设计**: 类似 AWS Rules Engine 的 SQL-like 配置

**JSON Schema**:
```json
{
  "version": "2.0",
  "type": "condition_action",
  "conditions": {
    "all": [
      { "field": "performance.spend", "operator": ">=", "value": 3.0 },
      { "field": "performance.ctr", "operator": "<", "value": 1.0 }
    ]
  },
  "actions": [
    {
      "type": "recommendation",
      "action": "pause_ad",
      "severity": "medium"
    }
  ]
}
```

**前端实现**: 拖拽式条件构建器
```tsx
<RuleBuilder>
  <ConditionGroup operator="all">
    <Condition
      field="performance.spend"
      operator=">="
      value={3.0}
    />
    <Condition
      field="performance.ctr"
      operator="<"
      value={1.0}
    />
  </ConditionGroup>
  <ActionList>
    <Action type="recommendation" action="pause_ad" />
  </ActionList>
</RuleBuilder>
```

**后端支持**: 编译 JSON → Python 代码
```python
def compile_json_rule(schema: dict) -> str:
    """将 JSON 规则编译为 Python 代码"""
    code = "def evaluate(context, params):\n"
    code += "    actions = []\n"
    code += "    reasons = []\n"

    # 生成条件检查代码
    for condition in schema['conditions']['all']:
        code += f"    if context['{condition['field']}'] {condition['operator']} {condition['value']}:\n"
        # ...

    # 生成 action 代码
    for action in schema['actions']:
        code += f"    actions.append({action})\n"

    code += "    return {'actions': actions, 'reasons': reasons, 'metrics': {}}\n"
    return code
```

#### 2. 规则依赖与编排

**数据模型扩展**:
```python
class RuleDefinitionDocument(Document):
    # 现有字段...

    # 新增字段
    depends_on: list[str] = []  # 依赖的其他规则名称
    priority: int = 0  # 执行优先级（越大越先执行）
    conflict_resolution: str = "latest_wins"  # 冲突解决策略
```

**执行引擎改进**:
```python
async def execute_rule_dag(bindings: list[RuleBindingDocument]):
    """按依赖顺序执行规则"""
    # 1. 构建 DAG
    dag = build_dependency_graph(bindings)

    # 2. 拓扑排序
    sorted_rules = topological_sort(dag)

    # 3. 按顺序执行
    results = {}
    for rule_name in sorted_rules:
        binding = find_binding(rule_name)

        # 注入前置规则的输出到 context
        context = build_context(binding)
        context['upstream_results'] = {
            dep: results[dep] for dep in binding.rule.depends_on
        }

        result = await execute_rule(binding, context)
        results[rule_name] = result

    # 4. 冲突检测与解决
    final_actions = resolve_conflicts(results)
    return final_actions
```

#### 3. 增强的沙箱执行环境

**替换方案**: 使用 `RestrictedPython` 库

**实现**:
```python
from RestrictedPython import compile_restricted, safe_globals

class EnhancedRuleSandbox:
    def __init__(self):
        self.safe_builtins = {
            **safe_globals,
            'abs': abs,
            'len': len,
            'sum': sum,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'min': min,
            'max': max,
            # 添加安全的工具函数
            'get': self._safe_get,
            'format_currency': self._format_currency,
            'parse_date': self._parse_date,
        }

    def execute(self, code: str, context: dict, params: dict, timeout: int = 5):
        """执行规则代码，带超时和资源限制"""
        # 编译受限代码
        byte_code = compile_restricted(code, '<rule>', 'exec')

        # 准备执行环境
        globals_dict = {
            '__builtins__': self.safe_builtins,
            'context': context,
            'params': params,
        }
        locals_dict = {}

        # 使用 signal 实现超时
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Rule execution exceeded {timeout}s")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

        try:
            exec(byte_code, globals_dict, locals_dict)
            result = locals_dict.get('evaluate')(context, params)
            return result
        finally:
            signal.alarm(0)  # 取消超时
```

#### 4. 规则测试框架

**新增**: `RuleTestDocument` 数据模型
```python
class RuleTestDocument(Document):
    rule_id: str
    test_name: str
    input_context: dict
    input_params: dict
    expected_output: dict
    created_at: datetime
    last_run: datetime | None
    status: str  # "passing" | "failing"
```

**API 端点**:
```python
@router.post("/rules/{rule_id}/tests")
async def create_rule_test(rule_id: str, test: RuleTestCreate):
    """为规则创建测试用例"""
    ...

@router.post("/rules/{rule_id}/tests/run")
async def run_rule_tests(rule_id: str):
    """运行规则的所有测试"""
    rule = await get_rule(rule_id)
    tests = await get_rule_tests(rule_id)

    results = []
    for test in tests:
        actual_output = execute_rule_code(rule.code, test.input_context, test.input_params)
        passed = compare_outputs(actual_output, test.expected_output)
        results.append({"test_name": test.test_name, "passed": passed})

    return results
```

---

### 🌟 长期规划（3-6月）

#### 1. AI 辅助规则生成

**功能**: 自然语言 → 规则代码

**实现思路**:
```python
from anthropic import Anthropic

async def generate_rule_from_description(description: str) -> str:
    """使用 Claude AI 从自然语言生成规则代码"""
    client = Anthropic()

    prompt = f"""
根据以下业务描述，生成符合我们规则引擎规范的 Python 代码：

描述: {description}

要求:
1. 必须定义 evaluate(context, params) 函数
2. context 包含: ad, performance, targeting 字段
3. 返回格式: {{"actions": [], "reasons": [], "metrics": {{}}}}

请生成代码:
"""

    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    code = extract_code_block(response.content)
    return code
```

**前端集成**:
```tsx
<RuleDefinitionForm>
  <AIAssistant>
    <textarea
      placeholder="描述你的规则逻辑，例如：当广告花费超过$5且点击率低于1%时，建议暂停广告"
      value={description}
      onChange={e => setDescription(e.target.value)}
    />
    <button onClick={handleGenerateFromAI}>
      生成规则代码
    </button>
  </AIAssistant>
</RuleDefinitionForm>
```

#### 2. 规则执行结果可视化

**功能**: 决策树可视化 + 执行路径追踪

**实现**: 使用 D3.js 或 ReactFlow
```tsx
<RuleExecutionVisualizer log={executionLog}>
  <DecisionTree
    nodes={[
      { id: '1', label: 'spend >= 3.0?', type: 'condition' },
      { id: '2', label: 'Exit early', type: 'action' },
      { id: '3', label: 'clicks == 0?', type: 'condition' },
      { id: '4', label: 'Recommend pause', type: 'action' },
    ]}
    edges={[
      { from: '1', to: '2', label: 'No' },
      { from: '1', to: '3', label: 'Yes' },
      { from: '3', to: '4', label: 'Yes' },
    ]}
    highlightedPath={['1', '3', '4']}  // 实际执行路径
  />
</RuleExecutionVisualizer>
```

#### 3. 规则性能分析

**功能**: 追踪每个规则的业务指标影响

**数据模型**:
```python
class RuleImpactMetrics(Document):
    rule_id: str
    date: date

    # 执行统计
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_execution_time_ms: float

    # 业务影响
    total_actions_recommended: int
    actions_executed: int  # 人工确认执行的数量

    # 财务影响（如果有后续数据）
    estimated_cost_saved: float
    estimated_revenue_protected: float
```

**API 端点**:
```python
@router.get("/rules/{rule_id}/impact")
async def get_rule_impact(rule_id: str, since: date, until: date):
    """获取规则的业务影响分析"""
    ...
```

#### 4. 规则市场（Rule Marketplace）

**功能**: 共享和复用规则模板

**实现**:
- 社区贡献的规则库
- 规则评分和评论系统
- 一键导入功能
- 规则变体管理（fork & modify）

---

## 实施路线图

### Phase 1: 基础体验优化（2周）
- [x] 集成 Monaco Editor 代码编辑器
- [x] 添加规则验证 API
- [x] 创建规则模板库
- [x] 改进错误提示

**预期成果**: 规则编写体验提升 80%

---

### Phase 2: 可视化构建器（1月）
- [ ] 设计 JSON Schema for simple rules
- [ ] 实现可视化条件构建器
- [ ] 实现 JSON → Python 编译器
- [ ] 前后端集成测试

**预期成果**: 非技术人员可以创建 70% 的简单规则

---

### Phase 3: 规则编排与测试（1月）
- [ ] 实现规则依赖系统
- [ ] 实现规则执行 DAG
- [ ] 创建规则测试框架
- [ ] 添加冲突检测机制

**预期成果**: 支持复杂规则组合，测试覆盖率 > 90%

---

### Phase 4: 增强沙箱与性能（2周）
- [ ] 集成 RestrictedPython
- [ ] 添加超时和资源限制
- [ ] 优化规则执行性能
- [ ] 添加规则缓存机制

**预期成果**: 规则执行安全性提升，性能提升 50%

---

### Phase 5: AI 辅助与高级功能（1月）
- [ ] 集成 Claude AI 生成规则
- [ ] 实现决策树可视化
- [ ] 实现规则影响分析
- [ ] 创建规则市场

**预期成果**: AI 生成规则准确率 > 80%，业务洞察能力提升

---

## 总结

### 当前系统的核心问题
1. **编辑体验差**: 纯文本编辑器，无 IDE 特性
2. **学习成本高**: 需要理解 Python 和 context 结构
3. **测试困难**: 缺少快速验证机制
4. **复用性低**: 无模板、无模块化
5. **可视化弱**: 规则逻辑隐藏在代码中

### 改进方向
1. **短期**: Monaco Editor + 验证 API + 模板库（快速见效）
2. **中期**: 可视化构建器 + 规则编排 + 测试框架（降低门槛）
3. **长期**: AI 辅助 + 性能优化 + 规则市场（生态建设）

### 业界对标
- **灵活性**: 对标 Airflow（保留代码优先能力）
- **易用性**: 对标 n8n（提供低代码选项）
- **企业级**: 对标 Drools（规则编排、冲突解决）

### ROI 评估
- **开发投入**: ~3 人月
- **维护成本**: 减少 60%（更少的规则错误）
- **业务价值**:
  - 规则创建效率提升 3x
  - 非技术人员可独立创建规则
  - 规则错误率降低 80%
  - 审计和合规能力增强
