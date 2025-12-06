# 前端架构详细分析

**文档版本**: 2.0
**最后更新**: 2025-12-06

> **重要更新 (2025-12-06)**: 页面结构已重构，从7个独立页面合并为4个功能模块页面：
> - 广告管理 (`/ads`) - 原 Insights 数据浏览
> - 规则管理 (`/rules`) - 合并规则定义 + 规则绑定
> - 调度管理 (`/scheduler`) - 合并调度监控 + 执行日志
> - 账号管理 (`/accounts`) - 合并 FB 授权 + 数据同步

---

## 1. 技术栈概览

### 核心框架
- **React**: 18.3.1 (最新稳定版)
- **TypeScript**: 5.6.3 (严格模式)
- **Vite**: 6.0.5 (极速构建)

### 状态管理
- **TanStack React Query**: 5.59.20 (服务端状态)
- **React Hooks**: useState/useRef (本地状态)
- **无 Redux**: 轻量化架构

### UI 与样式
- **Ant Design**: 5.23.1 (企��级组件库)
- **自定义 CSS**: CSS Layers 分层设计
- **Recharts**: 3.3.0 (数据可视化)

### 工具库
- **React Router DOM**: 6.28.0 (路由)
- **Axios**: 1.7.9 (HTTP 客户端)
- **clsx**: 2.1.1 (动态 className)

### 代码规模
- **总代码**: ~2,500+ 行 TypeScript/TSX
- **功能页面**: 4 个（每个包含多个标签页）
- **可复用组件**: 8 个
- **生产构建**: ~1.1M (gzip 后 ~350KB)

---

## 2. 项目结构

```
frontend/src/
├── api/                        # API 客户端层
│   ├── adAccounts.ts           # 广告账号 API
│   ├── facebookAuth.ts         # Facebook 授权 API
│   ├── insights.ts             # Insights 数据查询
│   ├── ruleEngine.ts           # 规则引擎 API
│   └── user.ts                 # 用户信息 API
│
├── components/                 # 可复用组件
│   ├── layout/                 # 布局组件
│   │   ├── AppLayout.tsx       # 主布局（侧边栏+内容区）
│   │   ├── Sidebar.tsx         # 侧边栏导航
│   │   ├── Topbar.tsx          # 顶部导航栏
│   │   └── UserInfo.tsx        # 用户信息展示
│   ├── AdAccountSelect.tsx     # 智能广告账号选择器
│   └── DateTimelineSelector.tsx# 日���范围选择器
│
├── features/                   # 功能模块（按业务划分）
│   ├── insights-data/          # Insights 数据浏览
│   │   └── InsightsDataPage.tsx  (2507行)
│   ├── insights-sync/          # 数据同步管理
│   │   └── InsightsSyncPage.tsx
│   ├── rule-definitions/       # 规则定义
│   │   └── RuleDefinitionsPage.tsx
│   ├── rule-bindings/          # 规则绑定
│   │   └── RuleBindingsPage.tsx
│   ├── execution-logs/         # 执行日志
│   │   └── ExecutionLogsPage.tsx
│   ├── scheduler/              # 调度监控
│   │   └── SchedulerPage.tsx
│   └── facebook-auth/          # FB 授权管理
│       └── FacebookAuthPage.tsx
│
├── lib/                        # 工具函数
│   ├── apiClient.ts            # Axios 配置与拦截器
│   ├── apiResponse.ts          # 响应解包工具
│   └── datetime.ts             # 时间格式化
│
├── types/                      # TypeScript 类型定义
│   ├── rule-engine.ts          # 规则引擎类型
│   ├── insights.ts             # Insights 类型
│   ├── ad-accounts.ts          # 广告账号类型
│   └── facebook-auth.ts        # Facebook 授权类型
│
├── App.tsx                     # 路由配置
├── main.tsx                    # 应用入口
└── index.css                   # 全局样式（CSS Layers）
```

---

## 3. 核心功能页面分析

### 3.1 Insights 数据浏览页面 (InsightsDataPage.tsx, 2507行)

这是系统**最复杂的页面**，提供强大的数据分析能力。

#### 核心特性

##### 1) 多层级数据聚合
```typescript
type HierarchyLevel = 'account' | 'campaign' | 'adset' | 'ad'

// 用户可切换四个层级
activeLevel: HierarchyLevel = 'ad'

// 聚合逻辑
const aggregatedInsights = useMemo(() => {
  switch (activeLevel) {
    case 'account':
      return aggregateByAccount(allInsights)
    case 'campaign':
      return aggregateByCampaign(allInsights)
    case 'adset':
      return aggregateByAdset(allInsights)
    case 'ad':
      return allInsights  // 原始数据
  }
}, [activeLevel, allInsights])
```

##### 2) 智能实体名称同步
```typescript
// 自动检测未命名实体
const unnamedEntities = insights.filter(
  insight => !insight.ad_name || !insight.adset_name || !insight.campaign_name
)

// 批量同步名称
if (unnamedEntities.length > 0) {
  const entityIds = [...new Set(unnamedEntities.map(i => i.ad_id))]
  await syncEntityNames(adAccountId, entityIds, 'ad')

  // 强制刷新缓存
  queryClient.invalidateQueries({ queryKey: ['insights', adAccountId] })
  refetch()
}
```

**同步策略**:
- 前端检测 `entity_name === null`
- 批量请求后端 API (`POST /insights/entity-name-syncs`)
- 后端调用 Facebook API 获取名称
- 缓存到 MongoDB (`AdEntityNamesDocument`)
- 前端强制刷新 React Query 缓存

##### 3) 灵活数据源切换
```typescript
type DataSource =
  | 'mongodb-only'          // 仅 MongoDB 历史数据
  | 'mongodb-redis'         // MongoDB + Redis 混合
  | 'realtime'              // 实时 Facebook API
  | 'mongodb-from-last'     // MongoDB + 增量填充

// 用户可动态切换
const [dataSource, setDataSource] = useState<DataSource>('mongodb-redis')
```

##### 4) 高级表格功能
```typescript
// 列配置（存储到 localStorage）
const [columnOrder, setColumnOrder] = useState<string[]>([...])
const [columnWidths, setColumnWidths] = useState<Record<string, number>>({...})
const [visibleMetricKeys, setVisibleMetricKeys] = useState<Set<string>>(...)

// 分页
const [currentPage, setCurrentPage] = useState(1)
const pageSize = 20

// Sticky 列
<th className="sticky-column">ID</th>

// 自定义列宽
<th style={{ width: columnWidths[key] || 120 }}>
  <ResizeHandle onResize={(newWidth) => setColumnWidths({...})} />
</th>
```

##### 5) 趋势图表集成
```typescript
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts'

// 点击日期 → 测试规则
const handleDateClick = (date: string) => {
  localStorage.setItem('rule_test_context', JSON.stringify({
    adId: selectedAdId,
    testDate: date
  }))
  navigate('/rules/bindings')
}

<LineChart data={timelineData}>
  <Line dataKey="spend" stroke="#8884d8" />
  <Line dataKey="roas" stroke="#82ca9d" />
  <XAxis dataKey="date" onClick={handleDateClick} />
</LineChart>
```

#### 状态管理架构

```typescript
// 分页状态
const [currentPage, setCurrentPage] = useState(1)

// 层级选择
const [activeLevel, setActiveLevel] = useState<HierarchyLevel>('ad')

// 多选筛选（每个层级独立维护）
const [selectedEntityIds, setSelectedEntityIds] = useState<
  Record<HierarchyLevel, Set<string>>
>({
  account: new Set(),
  campaign: new Set(),
  adset: new Set(),
  ad: new Set()
})

// 同步状态追踪
const [syncingEntityIds, setSyncingEntityIds] = useState<Set<string>>(new Set())
const syncedQueriesRef = useRef<Set<string>>(new Set())  // 避免重复同步

// 表格配置
const [columnOrder, setColumnOrder] = useState<string[]>([...])
const [columnWidths, setColumnWidths] = useState<Record<string, number>>({...})
const [visibleMetricKeys, setVisibleMetricKeys] = useState<Set<string>>(...)
```

#### 性能优化

```typescript
// 1. useMemo 缓存聚合数据
const aggregatedInsights = useMemo(() => {
  return aggregateByLevel(allInsights, activeLevel)
}, [allInsights, activeLevel])

// 2. useMemo 缓存时间线
const timelineData = useMemo(() => {
  return buildTimeline(selectedInsights)
}, [selectedInsights])

// 3. React Query 自动缓存
const { data: insights } = useQuery({
  queryKey: ['insights', adAccountId, since, until],
  queryFn: () => fetchInsights(...),
  staleTime: 10_000  // 10 秒缓存
})

// 4. 分页减少 DOM 节点
const paginatedData = useMemo(() => {
  const start = (currentPage - 1) * pageSize
  return aggregatedInsights.slice(start, start + pageSize)
}, [aggregatedInsights, currentPage])
```

---

### 3.2 规则定义页面 (RuleDefinitionsPage.tsx)

#### 功能清单
- 规则 CRUD（创建/读取/更新/删除）
- 版本控制（规则克隆）
- 参数化配置（JSON Schema 定义参数）
- 状态管理（Draft/Published/Disabled）
- 标签系统（多标签分类）
- 搜索过滤（名称/描述/标签/状态）

#### 核���数据结构

```typescript
interface RuleDefinition {
  id: string
  name: string
  description: string
  code: string                    // Python 脚本
  parameters_schema: ParametersSchema  // JSON Schema
  status: 'draft' | 'published' | 'disabled'
  version: number
  tags: string[]
  created_by: string
  created_at: string
  updated_at: string
}

interface ParametersSchema {
  [key: string]: {
    type: 'number' | 'string' | 'boolean'
    label: string
    description?: string
    default?: any
    min?: number
    max?: number
  }
}
```

#### 表单模式切换

```typescript
type CurrentView = 'list' | 'form'

const [currentView, setCurrentView] = useState<CurrentView>('list')
const [editingRule, setEditingRule] = useState<RuleDefinition | null>(null)

// 创建规则
const handleCreate = () => {
  setEditingRule(null)
  setCurrentView('form')
}

// 编辑规则
const handleEdit = (rule: RuleDefinition) => {
  setEditingRule(rule)
  setCurrentView('form')
}

// 返回列表
const handleBack = () => {
  setCurrentView('list')
  setEditingRule(null)
}
```

#### Breadcrumb 导航

```typescript
<Breadcrumb>
  <Breadcrumb.Item>规则定义</Breadcrumb.Item>
  {currentView === 'form' && (
    <Breadcrumb.Item>
      {editingRule ? `编辑规则: ${editingRule.name}` : '创建新规则'}
    </Breadcrumb.Item>
  )}
</Breadcrumb>
```

---

### 3.3 规则绑定页面 (RuleBindingsPage.tsx)

#### 三视图切换

```typescript
type CurrentView = 'list' | 'form' | 'execution'

const [currentView, setCurrentView] = useState<CurrentView>('list')

// list: 绑定列表
// form: 创建/编辑绑定表单
// execution: 规则测试面板
```

#### 智能参数表单

```typescript
// 根据 parameters_schema 动态渲染表单
const renderParameterField = (key: string, schema: RuleParameter) => {
  switch (schema.type) {
    case 'number':
      return (
        <input
          type="number"
          min={schema.min}
          max={schema.max}
          defaultValue={schema.default}
          onChange={(e) => setParameters({
            ...parameters,
            [key]: parseFloat(e.target.value)
          })}
        />
      )

    case 'boolean':
      return (
        <input
          type="checkbox"
          defaultChecked={schema.default}
          onChange={(e) => setParameters({
            ...parameters,
            [key]: e.target.checked
          })}
        />
      )

    case 'string':
      return (
        <input
          type="text"
          defaultValue={schema.default}
          onChange={(e) => setParameters({
            ...parameters,
            [key]: e.target.value
          })}
        />
      )
  }
}
```

#### 规则测试面板 (RuleBindingTestPanel)

```typescript
// 从 Insights 趋势图传入测试日期
useEffect(() => {
  const testContext = localStorage.getItem('rule_test_context')
  if (testContext) {
    const { adId, testDate } = JSON.parse(testContext)
    setTestAdId(adId)
    setTestDate(testDate)
    localStorage.removeItem('rule_test_context')  // 清理
  }
}, [])

// 执行规则测试
const handleTest = async () => {
  const result = await testRuleBinding(bindingId, testDate)

  // 显示执行结果
  setTestResult({
    status: result.execution_status,
    actions: result.actions_taken,
    context: result.context_snapshot,
    execution_time: result.duration_ms
  })
}
```

---

### 3.4 执行日志页面 (ExecutionLogsPage.tsx)

#### 展示内容

```typescript
interface RuleExecutionLog {
  id: string
  rule_binding_id: string
  rule_name: string
  entity_id: string

  // 执行信息
  execution_status: 'success' | 'failed' | 'skipped'
  execution_trigger: 'manual' | 'scheduler' | 'auto_unbind' | 'test'

  // 执行结果
  actions_taken: Array<{
    type: 'stop_ad' | 'start_ad' | 'adjust_budget' | 'send_alert'
    entity_id: string
    params?: any
  }>

  // 错误信息
  error_message?: string

  // 上下文快照
  context_snapshot: {
    ad_data: Array<{
      date: string
      spend: number
      roas: number
      // ...
    }>
    prediction?: {
      stop_probability: number
      features: Record<string, number>
    }
    params: Record<string, any>
  }

  // 时间信息
  executed_at: string
  duration_ms: number
}
```

#### 日志筛���

```typescript
// 按状态筛选
const [statusFilter, setStatusFilter] = useState<ExecutionStatus | 'all'>('all')

// 按触发方式筛选
const [triggerFilter, setTriggerFilter] = useState<ExecutionTrigger | 'all'>('all')

// 按日期范围筛选
const [dateRange, setDateRange] = useState<[string, string]>([...])

// 筛选逻辑
const filteredLogs = logs.filter(log => {
  if (statusFilter !== 'all' && log.execution_status !== statusFilter) return false
  if (triggerFilter !== 'all' && log.execution_trigger !== triggerFilter) return false
  if (log.executed_at < dateRange[0] || log.executed_at > dateRange[1]) return false
  return true
})
```

---

### 3.5 调度监控页面 (SchedulerPage.tsx)

#### 监控指标

```typescript
interface SchedulerTask {
  id: string
  name: string
  trigger: string                 // Cron 表达式
  status: 'running' | 'paused' | 'error'

  // 运行统计
  next_run_time: string
  last_run_time: string
  total_runs: number
  failed_runs: number

  // 性能指标
  avg_delay_seconds: number       // 平均延迟
  max_delay_seconds: number       // 最大延迟

  // 错误信息
  last_error_message?: string
}
```

#### 任务操作

```typescript
// 暂停/恢复任务
const handlePauseTask = async (taskId: string) => {
  await pauseSchedulerTask(taskId)
  refetch()
}

const handleResumeTask = async (taskId: string) => {
  await resumeSchedulerTask(taskId)
  refetch()
}

// 手动触发任务
const handleTriggerTask = async (taskId: string) => {
  await triggerSchedulerTask(taskId)
  refetch()
}
```

---

### 3.6 数据同步页面 (InsightsSyncPage.tsx)

#### 同步概览

```typescript
interface SyncOverviewItem {
  account_id: string
  account_name: string

  // MongoDB 覆盖范围
  obs_since: string               // 最早日期
  obs_until: string               // 最新日期
  last_synced_date: string        // 最后同步日期

  // Redis 缓存覆盖范围
  redis_cache_since: string
  redis_cache_until: string

  // 同步状态
  sync_status: 'up-to-date' | 'outdated' | 'never-synced'
  last_sync_time: string
}
```

#### 同步历史

```typescript
interface SyncHistoryRecord {
  id: string
  account_id: string
  sync_type: 'mongodb' | 'redis' | 'full'
  status: 'running' | 'completed' | 'failed'

  // 同步范围
  since: string
  until: string

  // 统计
  records_synced: number
  records_failed: number

  // 时间信息
  started_at: string
  completed_at?: string
  duration_seconds?: number

  // 错误信息
  error_message?: string
}
```

#### 手动触发同步

```typescript
// 单账户同步
const handleSyncAccount = async (accountId: string) => {
  await triggerAccountSync(accountId, 'mongodb')
  refetch()
}

// 批量同步
const handleSyncAll = async () => {
  const accountIds = overviewData.map(item => item.account_id)
  await Promise.all(
    accountIds.map(id => triggerAccountSync(id, 'mongodb'))
  )
  refetch()
}
```

---

## 4. 状态管理架构

### 4.1 React Query 配置

```typescript
// main.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,  // 窗口聚焦时不自动刷新
      staleTime: 10_000,            // 10 秒内认为数据是新鲜的
      retry: 1,                     // 失败后重试 1 次
    },
    mutations: {
      retry: 0,                     // Mutation 不重试
    }
  }
})

root.render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>
)
```

### 4.2 服务端状态管理

```typescript
// 使用 useQuery 获取数据
const { data, isLoading, error, refetch } = useQuery({
  queryKey: ['insights', adAccountId, since, until, level, dataSource],
  queryFn: async () => {
    const response = await fetchInsights(adAccountId, since, until, level, dataSource)
    return response.data
  },
  staleTime: 10_000,
  enabled: !!adAccountId  // 仅当 adAccountId 存在时才执行查询
})

// 使用 useMutation 修改数据
const mutation = useMutation({
  mutationFn: (data) => createRuleDefinition(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['ruleDefinitions'] })
    message.success('规则创建成功')
  },
  onError: (error) => {
    message.error(`创建失败: ${error.message}`)
  }
})
```

### 4.3 本地状态管理

```typescript
// 使用 useState 管理页面级状态
const [currentPage, setCurrentPage] = useState(1)
const [activeLevel, setActiveLevel] = useState<HierarchyLevel>('ad')
const [columnOrder, setColumnOrder] = useState<string[]>([...])

// 使用 useRef 管理不触发重渲染的状态
const syncedQueriesRef = useRef<Set<string>>(new Set())

// 使用 localStorage 持久化用户偏好
useEffect(() => {
  const savedConfig = localStorage.getItem('insights_table_config')
  if (savedConfig) {
    const { columnOrder, columnWidths } = JSON.parse(savedConfig)
    setColumnOrder(columnOrder)
    setColumnWidths(columnWidths)
  }
}, [])

useEffect(() => {
  localStorage.setItem('insights_table_config', JSON.stringify({
    columnOrder,
    columnWidths
  }))
}, [columnOrder, columnWidths])
```

### 4.4 为什么不使用 Redux？

1. **React Query 覆盖服务端状态**: 90% 的状态是服务端数据
2. **页面状态独立**: 各页面状态不需要全局共享
3. **减少样板代码**: 无需 actions/reducers/store 配置
4. **提升开发效率**: 更少的概念和模式

---

## 5. API 集成设计

### 5.1 统一 API 客户端

```typescript
// lib/apiClient.ts
import axios from 'axios'

const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL
const VITE_DEFAULT_USER_ID = import.meta.env.VITE_DEFAULT_USER_ID

const apiClient = axios.create({
  baseURL: VITE_API_BASE_URL ?? '/api',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'frontend-rule-engine'
  },
  timeout: 60000  // 60 秒超时
})

// 请求拦截器：自动注入用户 ID
apiClient.interceptors.request.use((config) => {
  config.headers.set('X-User-Id', VITE_DEFAULT_USER_ID ?? 'dev-user')
  return config
})

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 跳转到登录页
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

### 5.2 响应解包工具

```typescript
// lib/apiResponse.ts

/**
 * 提取响应数据（处理多种后端响应格式）
 */
export function extractResponseData<T>(response: any): T {
  // 格式 1: { data: { data: [...] } }
  if (response.data?.data !== undefined) {
    return response.data.data
  }

  // 格式 2: { data: [...] }
  if (Array.isArray(response.data)) {
    return response.data
  }

  // 格式 3: { data: { items: [...] } }
  if (response.data?.items !== undefined) {
    return response.data.items
  }

  // 默认返回 response.data
  return response.data
}

/**
 * 提取分页响应
 */
export function extractPaginatedResponse<T>(
  response: any,
  mapFn?: (item: any) => T
): PaginatedResult<T> {
  const data = extractResponseData(response)

  return {
    items: mapFn ? data.items.map(mapFn) : data.items,
    total: data.total ?? data.items.length,
    page: data.page ?? 1,
    page_size: data.page_size ?? data.items.length
  }
}

/**
 * 提取单个对象
 */
export function extractSingleObject<T>(response: any): T {
  if (response.data?.data !== undefined) {
    return response.data.data
  }
  return response.data
}
```

### 5.3 API 模块划分

```typescript
// api/insights.ts
export const fetchInsights = async (
  adAccountId: string,
  since: string,
  until: string,
  level: string,
  dataSource: string
): Promise<InsightsDataResponse> => {
  const response = await apiClient.get('/insights', {
    params: { ad_account_id: adAccountId, since, until, level }
  })
  return extractResponseData(response)
}

export const syncEntityNames = async (
  adAccountId: string,
  entityIds: string[],
  entityType: 'ad' | 'adset' | 'campaign'
): Promise<void> => {
  await apiClient.post('/insights/entity-name-syncs', {
    ad_account_id: adAccountId,
    entity_ids: entityIds,
    entity_type: entityType
  })
}

// api/ruleEngine.ts
export const fetchRuleDefinitions = async (): Promise<RuleDefinition[]> => {
  const response = await apiClient.get('/rules/definitions')
  return extractResponseData(response)
}

export const createRuleDefinition = async (
  data: CreateRuleDefinitionRequest
): Promise<RuleDefinition> => {
  const response = await apiClient.post('/rules/definitions', data)
  return extractSingleObject(response)
}
```

---

## 6. UI/UX 设计模式

### 6.1 CSS Layers 分层架构

```css
/* index.css */
@layer reset, base, components, utilities;

@layer reset {
  /* CSS Reset */
  * { margin: 0; padding: 0; box-sizing: border-box; }
}

@layer base {
  /* 设计 Token */
  :root {
    --color-bg: #f8f9fb;
    --color-bg-elevated: #ffffff;
    --color-primary: #2563eb;
    --color-primary-hover: #1d4ed8;
    --color-success: #0ea5e9;
    --color-warning: #f59e0b;
    --color-danger: #ef4444;
    --color-text: #1e293b;
    --color-text-secondary: #64748b;
    --radius-sm: 0.375rem;
    --radius-md: 0.75rem;
    --radius-lg: 1rem;
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
    --shadow-md: 0 10px 25px rgba(15, 23, 42, 0.08);
    --shadow-lg: 0 20px 40px rgba(15, 23, 42, 0.12);
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--color-bg);
    color: var(--color-text);
  }
}

@layer components {
  /* 按钮组件 */
  .btn {
    padding: 0.5rem 1rem;
    border-radius: var(--radius-md);
    transition: all 0.2s;
  }

  .btn-primary {
    background: var(--color-primary);
    color: white;
  }

  .btn-primary:hover {
    background: var(--color-primary-hover);
    box-shadow: var(--shadow-md);
  }
}

@layer utilities {
  /* 工具类 */
  .text-center { text-align: center; }
  .mt-4 { margin-top: 1rem; }
  .flex { display: flex; }
  .flex-col { flex-direction: column; }
}
```

### 6.2 侧边栏导航设计

```typescript
// components/layout/Sidebar.tsx

const menuItems = [
  {
    key: 'rules-section',
    label: '规则引擎',
    description: '管理广告调控规则',
    items: [
      { key: '/rules/definitions', label: '规则定义', icon: <BookIcon /> },
      { key: '/rules/bindings', label: '规则绑定', icon: <LinkIcon /> },
      { key: '/rules/executions', label: '执行日志', icon: <HistoryIcon /> },
      { key: '/rules/scheduler', label: '调度监控', icon: <ClockIcon /> }
    ]
  },
  {
    key: 'insights-section',
    label: '数据洞察',
    description: '查看和管理广告数据',
    items: [
      { key: '/insights/data', label: 'Insights 数据', icon: <ChartIcon /> },
      { key: '/insights/sync-runs', label: '数据同步', icon: <SyncIcon /> }
    ]
  }
]

// 激活状态样式
const isActive = location.pathname === item.key

<div className={clsx('menu-item', { active: isActive })}>
  {item.icon}
  <span>{item.label}</span>
</div>

/* CSS */
.menu-item {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.menu-item.active {
  background: rgba(37, 99, 235, 0.08);
  border-left: 3px solid var(--color-primary);
  box-shadow: inset 0 1px 3px rgba(37, 99, 235, 0.1);
}
```

### 6.3 表格组件设计

```typescript
// 自定义表格实现（非 Ant Design Table）

// Sticky 列
<table>
  <thead>
    <tr>
      <th className="sticky-column">ID</th>
      {metricColumns.map(col => (
        <th key={col.key} style={{ width: columnWidths[col.key] || 120 }}>
          {col.label}
          <ResizeHandle
            onResize={(newWidth) => handleColumnResize(col.key, newWidth)}
          />
        </th>
      ))}
    </tr>
  </thead>
  <tbody>
    {paginatedData.map(row => (
      <tr key={row.id}>
        <td className="sticky-column">{row.id}</td>
        {metricColumns.map(col => (
          <td key={col.key}>{formatValue(row[col.key], col.format)}</td>
        ))}
      </tr>
    ))}
  </tbody>
</table>

/* CSS */
.sticky-column {
  position: sticky;
  left: 0;
  background: white;
  z-index: 10;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.1);
}
```

### 6.4 智能广告账号选择器

```typescript
// components/AdAccountSelect.tsx

const AdAccountSelect = ({ value, onChange }) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)

  // 模糊搜索
  const filteredAccounts = accounts.filter(account =>
    account.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    account.account_id.includes(searchTerm)
  )

  // 键盘导航
  const handleKeyDown = (e: KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        setHighlightedIndex((prev) =>
          Math.min(prev + 1, filteredAccounts.length - 1)
        )
        break
      case 'ArrowUp':
        setHighlightedIndex((prev) => Math.max(prev - 1, 0))
        break
      case 'Enter':
        onChange(filteredAccounts[highlightedIndex])
        setIsOpen(false)
        break
      case 'Escape':
        setIsOpen(false)
        break
    }
  }

  return (
    <div className="ad-account-select">
      <input
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="搜索广告账号..."
      />
      {isOpen && (
        <ul className="dropdown">
          {filteredAccounts.map((account, index) => (
            <li
              key={account.account_id}
              className={clsx({ highlighted: index === highlightedIndex })}
              onClick={() => {
                onChange(account)
                setIsOpen(false)
              }}
            >
              <div className="account-name">{account.name}</div>
              <div className="account-id">{account.account_id}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

---

## 7. 路由架构

### 7.1 路由级代码分割

```typescript
// App.tsx
import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Spin } from 'antd'

// 懒加载页面组件
const RuleDefinitionsPage = lazy(() => import('./features/rule-definitions/RuleDefinitionsPage'))
const RuleBindingsPage = lazy(() => import('./features/rule-bindings/RuleBindingsPage'))
const ExecutionLogsPage = lazy(() => import('./features/execution-logs/ExecutionLogsPage'))
const SchedulerPage = lazy(() => import('./features/scheduler/SchedulerPage'))
const InsightsDataPage = lazy(() => import('./features/insights-data/InsightsDataPage'))
const InsightsSyncPage = lazy(() => import('./features/insights-sync/InsightsSyncPage'))
const FacebookAuthPage = lazy(() => import('./features/facebook-auth/FacebookAuthPage'))

function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Suspense fallback={<Spin size="large" tip="加载中..." />}>
          <Routes>
            <Route path="/" element={<Navigate to="/rules/definitions" replace />} />
            <Route path="/rules/definitions" element={<RuleDefinitionsPage />} />
            <Route path="/rules/bindings" element={<RuleBindingsPage />} />
            <Route path="/rules/executions" element={<ExecutionLogsPage />} />
            <Route path="/rules/scheduler" element={<SchedulerPage />} />
            <Route path="/insights/data" element={<InsightsDataPage />} />
            <Route path="/insights/sync-runs" element={<InsightsSyncPage />} />
            <Route path="/integrations/facebook" element={<FacebookAuthPage />} />
          </Routes>
        </Suspense>
      </AppLayout>
    </BrowserRouter>
  )
}
```

**优势**:
- 按需加载，减少初始 Bundle 体积
- 用户访问页面时才加载对应代码
- Suspense 提供优雅的加载状态

### 7.2 路由配置

```
/                               → Redirect to /rules/definitions
/rules/definitions              → 规则定义管理
/rules/bindings                 → 规则绑定管理
/rules/executions               → 执行日志查看
/rules/scheduler                → 调度器监控
/insights/data                  → Insights 数据浏览
/insights/sync-runs             → 数据同步管理
/integrations/facebook          → Facebook 授权管理
```

---

## 8. 构建优化策略

### 8.1 Vite 配置

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  build: {
    chunkSizeWarningLimit: 1024,
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心
          react: ['react', 'react-dom', 'react/jsx-runtime'],
          router: ['react-router-dom'],

          // Ant Design
          'antd-core': ['antd'],
          'antd-icons': ['@ant-design/icons'],  // 图标单独打包

          // 第三方库
          query: ['@tanstack/react-query'],
          charts: ['recharts'],
          axios: ['axios'],
          utils: ['clsx']
        }
      }
    },

    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,       // 移除 console
        drop_debugger: true,
        pure_funcs: ['console.log']
      }
    }
  },

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

### 8.2 打包策略

```
dist/
├── assets/
│   ├── index-[hash].js              # 主入口 (50KB)
│   ├── react-[hash].js              # React 核心 (150KB)
│   ├── antd-core-[hash].js          # Ant Design (300KB)
│   ├── antd-icons-[hash].js         # 图标库 (200KB)
│   ├── router-[hash].js             # React Router (50KB)
│   ├── query-[hash].js              # React Query (80KB)
│   ├── charts-[hash].js             # Recharts (200KB)
│   ├── axios-[hash].js              # Axios (20KB)
│   ├── utils-[hash].js              # clsx (5KB)
│   ├── InsightsDataPage-[hash].js   # 懒加载页面 (100KB)
│   └── ...其他懒加载页面
├── index.html
└── favicon.ico
```

### 8.3 生产构建优化效果

- **总体积**: 1.5M (未压缩)
- **gzip 后**: ~500KB
- **初始加载**: react + antd-core + index ≈ 500KB
- **后续导航**: 每个页面 ~50-100KB

---

## 9. 类型系统设计

### 9.1 类型定义组织

```typescript
// types/rule-engine.ts
export type RuleStatus = 'draft' | 'published' | 'disabled'
export type ExecutionStatus = 'success' | 'failed' | 'skipped'
export type ExecutionTrigger = 'manual' | 'scheduler' | 'auto_unbind' | 'test'

export interface RuleDefinition {
  id: string
  name: string
  description: string
  code: string
  parameters_schema: ParametersSchema
  status: RuleStatus
  version: number
  tags: string[]
  created_by: string
  created_at: string
  updated_at: string
}

export interface RuleBinding {
  id: string
  rule_definition_id: string
  rule_name: string
  entity_id: string
  entity_type: 'ad'
  parameters: Record<string, any>
  cron_expression?: string
  is_enabled: boolean
  account_id: string
  notes?: string
  created_by: string
  created_at: string
  updated_at: string
}

export interface RuleExecutionLog {
  id: string
  rule_binding_id: string
  rule_name: string
  entity_id: string
  execution_status: ExecutionStatus
  execution_trigger: ExecutionTrigger
  actions_taken: Array<{
    type: string
    entity_id: string
    params?: any
  }>
  error_message?: string
  context_snapshot: any
  executed_at: string
  duration_ms: number
}

// types/insights.ts
export interface InsightRecord {
  ad_id: string
  adset_id?: string
  campaign_id?: string
  date_start: string

  // 实体名称
  ad_name?: string
  adset_name?: string
  campaign_name?: string

  // 核心指标
  spend: number
  impressions: number
  reach: number
  clicks: number
  inline_link_clicks: number
  outbound_clicks: number

  // 转化指标（动态）
  [key: `conversion_${string}`]: number | undefined
}

export interface InsightsDataResponse {
  insights: InsightRecord[]
  total: number
  account_id: string
  since: string
  until: string
  level: 'account' | 'campaign' | 'adset' | 'ad'
}
```

### 9.2 类型安全策略

```typescript
// 1. 严格的枚举类型
export type RuleStatus = 'draft' | 'published' | 'disabled'  // ✅ 类型安全

// 2. Record 类型约束
export type ParametersSchema = Record<string, RuleParameter>

// 3. 泛型工具函数
export function extractPaginatedResponse<T>(
  response: any,
  mapFn?: (item: any) => T
): PaginatedResult<T> {
  // ...
}

// 4. 条件类型推断
type MetricKey = typeof METRIC_COLUMNS[number]['key']
```

### 9.3 TypeScript 配置

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true
  }
}
```

---

## 10. 部署架构

### 10.1 Nginx 配置

```nginx
# nginx.conf.template
upstream backend {
    server ${BACKEND_HOST}:8000;
    keepalive 64;
    keepalive_requests 10000;
    keepalive_timeout 60s;
}

server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # API 代理
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-User-Id $http_x_user_id;

        # 性能优化
        proxy_buffering on;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }

    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 10.2 Docker 部署

```dockerfile
# Dockerfile
FROM node:18 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

## 总结

这是一个**现代化、高性能、高可维护性**的 React 企业级前端应用，核心亮点包括：

1. **无 Redux 轻量化状态管理**: React Query + useState 覆盖所有场景
2. **智能 Insights 数据浏览**: 四级层级 + 多数据源 + 自动实体名称同步
3. **灵活规则引擎**: 动态参数表单 + 实时测试 + 完整审计日志
4. **生产级构建优化**: 细粒度 chunks + Terser 压缩 + 仅 1.5M 体积
5. **强类型安全**: 全面的 TypeScript 覆盖 + 严格模式

**技术债务**: 极低，代码质量高，架构清晰，易于维护和扩展。

**推荐指数**: ⭐⭐⭐⭐⭐ (5/5)

---

**文档版本**: 1.0
**最后更新**: 2025-12-05
**下一篇**: [03_potential_issues.md](./03_potential_issues.md)
