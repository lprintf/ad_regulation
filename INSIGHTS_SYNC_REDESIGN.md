# 洞察同步页面重构 - 更新说明

## 📋 概述

本次更新完全重构了洞察同步管理功能，提供了更清晰的UI、更强大的历史追踪和更好的用户体验。

## 🎯 主要改进

### 1. **全新的 Tab 布局**
- **概览页**: 卡片式布局展示所有账号的同步状态
- **同步历史页**: 完整的历史记录列表，支持分页和详情查看

### 2. **完整的历史记录系统**
- 每次同步任务都会创建历史记录
- 记录包含：触发方式、执行进度、耗时、错误信息等
- 支持按账号、状态、触发类型筛选

### 3. **改进的数据模型**
- 新增 `SyncHistoryDocument` 存储每次同步的完整记录
- 保留 `InsightsSyncStateDocument` 记录账号最新状态
- 清晰的状态流转：pending → running → success/failed

## 📦 变更清单

### 后端变更

#### 1. 数据库模型 (`backend/utils/db.py`)

**新增:**
```python
class SyncHistoryDocument(Document):
    """洞察同步历史记录"""
    account_id: str
    account_name: str | None
    trigger_type: Literal["manual", "auto", "retry"]
    triggered_by: str | None
    since: datetime
    until: datetime
    mode: Literal["sync", "async"]
    status: Literal["pending", "running", "success", "failed"]
    started_at: datetime
    completed_at: datetime | None
    records_count: int
    error_message: str | None
    duration_seconds: float | None
    percent_complete: int
    total_days: int
    processed_days: int
    # ... 更多字段
```

#### 2. API 模型 (`backend/api/models/insights.py`)

**新增类型:**
- `TriggerType`: 触发类型枚举 (manual/auto/retry)
- `SyncMode`: 同步模式枚举 (sync/async)
- `SyncHistoryRecord`: 历史记录响应模型
- `SyncHistoryListResponse`: 历史记录列表响应
- `SyncOverviewItem`: 账号概览项
- `SyncOverviewResponse`: 概览页响应

#### 3. 同步历史服务 (`backend/api/services/sync_history_service.py`)

**新增服务类 `SyncHistoryService`:**
- `create_history_record()`: 创建历史记录
- `update_history_status()`: 更新历史记录状态
- `update_history_progress()`: 更新进度信息
- `get_history_list()`: 获取分页历史列表
- `get_sync_overview()`: 获取所有账号概览
- `get_history_by_id()`: 获取单条历史记录详情

#### 4. API 端点 (`backend/api/routers/insights.py`)

**新增端点:**
```python
GET  /insights/sync/overview           # 获取所有账号同步概览
GET  /insights/sync/history            # 获取分页历史记录列表
GET  /insights/sync/history/{id}       # 获取单条历史记录详情
POST /insights/sync/trigger            # 手动触发同步（替代旧端点）
```

**标记为弃用:**
```python
GET  /insights/sync/runs               # 已弃用，使用 /sync/overview 替代
POST /insights/sync/runs               # 已弃用，使用 /sync/trigger 替代
```

### 前端变更

#### 1. 类型定义 (`frontend/src/types/insights.ts`)

**新增类型:**
```typescript
type TriggerType = 'manual' | 'auto' | 'retry'
type SyncMode = 'sync' | 'async'

interface SyncHistoryRecord { ... }
interface SyncHistoryListResponse { ... }
interface SyncOverviewItem { ... }
interface SyncOverviewResponse { ... }
```

#### 2. API 调用 (`frontend/src/api/insights.ts`)

**新增函数:**
```typescript
fetchSyncOverview(): Promise<SyncOverviewResponse>
fetchSyncHistory(params): Promise<SyncHistoryListResponse>
fetchSyncHistoryDetail(id): Promise<SyncHistoryRecord>
triggerSync(payload): Promise<InsightSyncTriggerResult>
```

#### 3. 新页面组件 (`frontend/src/features/insights-sync/InsightsSyncPageNew.tsx`)

**主要功能:**
- Tab 切换（概览 / 历史）
- 卡片式账号状态展示
- 手动触发同步表单
- 历史记录表格 + 分页
- 历史记录详情弹窗

## 🚀 使用指南

### 启动新页面

**临时测试（不影响现有功能）:**

在 `frontend/src/App.tsx` 中添加新路由：

```typescript
import InsightsSyncPageNew from './features/insights-sync/InsightsSyncPageNew'

// 在路由配置中添加
<Route path="/insights-sync-new" element={<InsightsSyncPageNew />} />
```

访问 `http://localhost:3000/insights-sync-new` 查看新页面。

**正式替换（推荐）:**

直接替换旧的同步页面：

```typescript
// frontend/src/App.tsx
import InsightsSyncPage from './features/insights-sync/InsightsSyncPageNew'  // 使用新页面

// 或者重命名文件
mv InsightsSyncPageNew.tsx InsightsSyncPage.tsx
```

### API 端点示例

#### 1. 获取同步概览

```bash
curl -X GET "http://localhost:8000/insights/sync/overview" \
  -H "X-User-Id: user123"
```

#### 2. 触发手动同步

```bash
curl -X POST "http://localhost:8000/insights/sync/trigger" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "account_ids": ["act_123", "act_456"],
    "since": "2025-01-01",
    "until": "2025-01-31"
  }'
```

#### 3. 查询历史记录

```bash
# 获取第1页，每页20条
curl -X GET "http://localhost:8000/insights/sync/history?page=1&page_size=20" \
  -H "X-User-Id: user123"

# 筛选特定账号的历史
curl -X GET "http://localhost:8000/insights/sync/history?account_id=act_123" \
  -H "X-User-Id: user123"

# 只看失败的记录
curl -X GET "http://localhost:8000/insights/sync/history?status=failed" \
  -H "X-User-Id: user123"
```

#### 4. 获取历史记录详情

```bash
curl -X GET "http://localhost:8000/insights/sync/history/67890abcdef" \
  -H "X-User-Id: user123"
```

## 📊 数据结构示例

### 概览响应
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "accountId": "act_123",
        "accountName": "示例账号",
        "status": "success",
        "lastSyncedAt": "2025-11-25T10:30:00Z",
        "lastSyncedDate": "2025-11-24",
        "dataCoverageSince": "2024-08-01",
        "dataCoverageUntil": "2025-11-24",
        "lastError": null,
        "isRunning": false,
        "lastHistoryId": "67890abcdef"
      }
    ],
    "totalAccounts": 1
  }
}
```

### 历史记录响应
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "67890abcdef",
        "accountId": "act_123",
        "accountName": "示例账号",
        "triggerType": "manual",
        "triggeredBy": "user123",
        "since": "2025-01-01",
        "until": "2025-01-31",
        "mode": "sync",
        "status": "success",
        "startedAt": "2025-11-25T10:00:00Z",
        "completedAt": "2025-11-25T10:15:00Z",
        "recordsCount": 3100,
        "errorMessage": null,
        "durationSeconds": 900.5,
        "percentComplete": 100,
        "totalDays": 31,
        "processedDays": 31
      }
    ],
    "total": 150,
    "page": 1,
    "pageSize": 20
  }
}
```

## 🔧 数据库迁移

新增了 `sync_history` collection，MongoDB 会自动创建。无需手动迁移。

**自动创建索引:**
```javascript
// 在应用启动时自动创建
{
  "account_id": 1,
  "started_at": -1
}
{
  "status": 1,
  "started_at": -1
}
```

## ⚠️ 注意事项

### 向后兼容性

1. **旧端点保留但标记为弃用**
   - `GET /insights/sync/runs` → 仍可用，但建议迁移到 `/sync/overview`
   - `POST /insights/sync/runs` → 仍可用，但建议迁移到 `/sync/trigger`

2. **旧前端页面**
   - `InsightsSyncPage.tsx` 保留为备份
   - 新页面为 `InsightsSyncPageNew.tsx`

### 性能考虑

1. **历史记录分页**
   - 默认每页 20 条
   - 最大每页 100 条
   - 建议使用分页而非一次性加载

2. **自动刷新间隔**
   - 概览页：30 秒
   - 历史页：60 秒
   - 避免过于频繁的轮询

## 🐛 已知问题

1. **历史记录创建** ⚠️
   - 当前 `insights_sync_service.py` 中的同步方法尚未集成历史记录创建
   - 需要在 `_process_sync_accounts` 和 `_process_async_accounts` 中添加调用
   - 临时方案：历史记录需手动创建或等待下一版本集成

2. **进度更新**
   - 异步任务的实时进度更新尚未完全实现
   - 目前只在任务开始和结束时更新状态

## 📝 后续计划

- [ ] 在现有同步逻辑中集成历史记录创建
- [ ] 添加重试失败任务的功能
- [ ] 支持同步任务取消
- [ ] 实时进度WebSocket推送（可选）
- [ ] 导出历史记录为CSV

## 🔗 相关文件

### 后端
- `backend/utils/db.py` - 数据库模型
- `backend/api/models/insights.py` - API模型
- `backend/api/services/sync_history_service.py` - 历史服务
- `backend/api/routers/insights.py` - API路由

### 前端
- `frontend/src/types/insights.ts` - 类型定义
- `frontend/src/api/insights.ts` - API调用
- `frontend/src/features/insights-sync/InsightsSyncPageNew.tsx` - 新页面

## 👥 测试建议

1. **启动后端服务**
   ```bash
   cd backend
   python run_api.py
   ```

2. **访问新页面**
   - 添加路由后访问 `/insights-sync-new`
   - 或直接替换旧页面

3. **测试场景**
   - 查看账号概览
   - 触发手动同步
   - 浏览历史记录
   - 查看历史详情
   - 测试分页功能

---

**更新日期**: 2025-11-25
**版本**: 2.0.0
**作者**: Claude Code Assistant
