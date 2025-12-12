# 前端自动分批同步功能

## 问题

用户选择大量实体（>50个）进行批量刷新时，后端返回错误：
```json
{"detail":"最多一次同步 50 个实体，请分批请求"}
```

## 解决方案

### ✅ 前端自动分批处理

**修改文件**: `frontend/src/features/insights-data/InsightsDataPageSimplified.tsx:341-380`

**核心逻辑**:
```typescript
const handleBatchSync = useCallback(() => {
  const MAX_BATCH_SIZE = 50  // 后端限制

  // 1. 按账号分组
  const entityIdsByAccount = new Map<string, string[]>()
  aggregatedEntities.forEach(entity => {
    if (selectedIds.has(entity.entityId)) {
      const list = entityIdsByAccount.get(entity.accountId) ?? []
      list.push(entity.entityId)
      entityIdsByAccount.set(entity.accountId, list)
    }
  })

  // 2. 标记所有为"同步中"
  setSyncingEntityIds(prev => new Set([...prev, ...selectedIds]))

  // 3. 自动分批：每批最多50个
  let totalBatches = 0
  entityIdsByAccount.forEach((entityIds, accountId) => {
    for (let i = 0; i < entityIds.length; i += MAX_BATCH_SIZE) {
      const batch = entityIds.slice(i, i + MAX_BATCH_SIZE)
      totalBatches++

      // 每批延迟100ms，避免并发过多
      setTimeout(() => {
        syncMutation.mutate({ entityIds: batch, accountId })
      }, totalBatches * 100)
    }
  })

  // 4. 用户提示
  if (totalBatches > 1) {
    toast.info(`已分成 ${totalBatches} 批次同步，请稍候...`)
  }
}, [selectedIds, aggregatedEntities, syncMutation])
```

## 功能特性

### 1. 智能分批
- **自动检测**: 自动判断是否需要分批（>50个）
- **批次大小**: 每批最多50个实体
- **账号隔离**: 不同账号的实体分别处理

### 2. 并发控制
- **延迟发送**: 每批之间延迟100ms
- **避免过载**: 防止同时发送过多请求

### 3. 用户体验
- **批次提示**: 超过1批时显示总批次数
- **状态同步**: 所有选中的实体立即标记为"同步中"
- **进度可见**: UI中显示Spinner加载状态

## 使用示例

### 场景 1: 小批量（≤50个）
```
用户选择: 30个广告
  ↓
点击"批量刷新实体名称"
  ↓
发送1个请求: 30个实体
  ↓
Toast: 无提示（正常同步）
```

### 场景 2: 中批量（51-100个）
```
用户选择: 75个广告
  ↓
点击"批量刷新实体名称"
  ↓
自动分成2批:
  - 批次1: 50个实体 (延迟0ms)
  - 批次2: 25个实体 (延迟100ms)
  ↓
Toast: "已分成 2 批次同步，请稍候..."
```

### 场景 3: 大批量（>100个）
```
用户选择: 150个广告
  ↓
点击"批量刷新实体名称"
  ↓
自动分成3批:
  - 批次1: 50个 (延迟0ms)
  - 批次2: 50个 (延迟100ms)
  - 批次3: 50个 (延迟200ms)
  ↓
Toast: "已分成 3 批次同步，请稍候..."
```

### 场景 4: 多账号混合
```
用户选择:
  - 账号A: 80个广告
  - 账号B: 40个广告
  ↓
点击"批量刷新实体名称"
  ↓
自动分批处理:
  账号A:
    - 批次1: 50个 (延迟0ms)
    - 批次2: 30个 (延迟100ms)
  账号B:
    - 批次3: 40个 (延迟200ms)
  ↓
Toast: "已分成 3 批次同步，请稍候..."
```

## 技术细节

### 分批算法
```typescript
// 将数组切片，每片最多 MAX_BATCH_SIZE 个
for (let i = 0; i < entityIds.length; i += MAX_BATCH_SIZE) {
  const batch = entityIds.slice(i, i + MAX_BATCH_SIZE)
  // 处理这一批...
}
```

### 延迟策略
```typescript
// 每批延迟 100ms * 批次编号
setTimeout(() => {
  syncMutation.mutate({ entityIds: batch, accountId })
}, totalBatches * 100)
```

**原因**:
- 避免瞬间发送大量并发请求
- 给后端防抖机制留出反应时间
- 降低 Facebook API 速率限制风险

### 状态管理
```typescript
// 立即标记所有为"同步中"
setSyncingEntityIds(prev => new Set([...prev, ...selectedIds]))

// 每批成功后，mutation.onSuccess 会自动移除
onSuccess: (result, variables) => {
  setSyncingEntityIds(prev => {
    const next = new Set(prev)
    variables.entityIds.forEach(id => next.delete(id))
    return next
  })
}
```

## 性能优化

### 时间复杂度
- **分组**: O(n) - 遍历所有选中的实体
- **分批**: O(n/50) - 每50个为一批
- **总体**: O(n) - 线性时间复杂度

### 空间复杂度
- **Map 存储**: O(n) - 存储所有账号ID和实体ID的映射
- **Set 状态**: O(n) - 存储所有"同步中"的实体ID

### 网络优化
- **批次大小**: 50个/批（后端限制）
- **并发控制**: 100ms间隔（避免过载）
- **估算时间**:
  - 100个实体 ≈ 2批 ≈ 0.1秒延迟
  - 500个实体 ≈ 10批 ≈ 1秒延迟

## 测试验证

### 测试用例 1: 边界条件
```typescript
// 恰好50个
selectedIds = new Set([...Array(50)].map((_, i) => `id_${i}`))
handleBatchSync()
// 预期：1批，无toast提示

// 51个
selectedIds = new Set([...Array(51)].map((_, i) => `id_${i}`))
handleBatchSync()
// 预期：2批，toast显示"已分成 2 批次同步"
```

### 测试用例 2: 多账号
```typescript
// 账号A: 60个, 账号B: 40个
handleBatchSync()
// 预期：
//   - 账号A分成2批（50 + 10）
//   - 账号B分成1批（40）
//   - 总计3批
//   - Toast: "已分成 3 批次同步"
```

## 与后端协作

### 后端约束
- **最大批次**: 50个实体/请求
- **返回错误**: `{"detail":"最多一次同步 50 个实体，请分批请求"}`

### 前端适配
- ✅ 自动分批，用户无感知
- ✅ 符合后端限制
- ✅ 优化并发性能

## 后续优化建议

### 1. 进度条显示
```typescript
const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 })

// 每批完成后更新进度
onSuccess: () => {
  setSyncProgress(prev => ({ ...prev, current: prev.current + 1 }))
}

// UI显示
{syncProgress.total > 0 && (
  <div className="progress-bar">
    {syncProgress.current} / {syncProgress.total} 批次已完成
  </div>
)}
```

### 2. 失败重试
```typescript
// 记录失败的批次
const [failedBatches, setFailedBatches] = useState<Set<number>>(new Set())

onError: (error, variables, batchIndex) => {
  setFailedBatches(prev => new Set(prev).add(batchIndex))
}

// 提供重试按钮
<button onClick={() => retryFailedBatches()}>
  重试失败的批次
</button>
```

### 3. 智能调度
```typescript
// 根据网络状况动态调整延迟
const adaptiveDelay = networkSpeed === 'fast' ? 50 : 150

setTimeout(() => {
  syncMutation.mutate(...)
}, totalBatches * adaptiveDelay)
```

## 总结

✅ **已实现**: 前端自动分批处理，最多50个/批
✅ **用户体验**: 无需手动分批，自动提示批次数量
✅ **性能优化**: 100ms延迟间隔，避免并发过多
✅ **类型安全**: TypeScript 检查通过

用户现在可以放心选择任意数量的实体进行批量刷新，前端会自动处理分批逻辑！🎉
