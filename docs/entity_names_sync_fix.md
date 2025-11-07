# 实体名称同步系统修复总结

**日期**: 2025-11-06
**问题**: 用户反馈"同步成功过很多次，但每次刷新还是会遇到 null"

## 问题根本原因

经过深入分析，发现了**3个关键问题**导致实体名称无法正确显示：

### 1. 后端：Upsert 查询条件缺少 account_id 过滤

**位置**: `api/services/entity_names_sync_service.py` 第 209-216 行

**问题**:
```python
# 修复前 - 错误的查询条件
UpdateOne(
    {
        "entity_type": entity_type,
        "entity_id": entity_id,
    },
    ...
)
```

**影响**:
- 不同账号的相同 entity_id 会互相覆盖
- 账号 A 的 campaign_id 可能被账号 B 的数据覆盖
- 导致显示错误的名称或 null

**修复**:
```python
# 修复后 - 正确的查询条件
UpdateOne(
    {
        "account_id": account_id_without_prefix,  # 添加 account_id
        "entity_type": entity_type,
        "entity_id": entity_id,
    },
    ...
)
```

### 2. 后端：查询实体名称时缺少 account_id 过滤

**位置**: `api/services/insights_service.py` 第 513-541 行

**问题**:
```python
# 修复前 - 缺少 account_id 过滤
campaign_name_docs = await AdEntityNamesDocument.find(
    AdEntityNamesDocument.entity_type == "campaign",
    In(AdEntityNamesDocument.entity_id, list(campaign_ids)),
).to_list()
```

**影响**:
- 可能查询到其他账号的同名 entity_id
- 多账号环境下数据混乱

**修复**:
```python
# 修复后 - 添加 account_id 过滤
campaign_name_docs = await AdEntityNamesDocument.find(
    AdEntityNamesDocument.account_id == account_id,  # 添加账号过滤
    AdEntityNamesDocument.entity_type == "campaign",
    In(AdEntityNamesDocument.entity_id, list(campaign_ids)),
).to_list()
```

同时修改了方法签名，添加 `account_id` 参数：
```python
async def _attach_entity_names(
    insights_list: list[dict[str, Any]],
    level: str,
    account_id: str  # 新增参数
) -> list[dict[str, Any]]:
```

### 3. 前端：React Query 缓存未失效

**位置**: `frontend/src/features/insights-data/InsightsDataPage.tsx` 第 289-291 行和 475-477 行

**问题**:
```typescript
// 修复前 - 仅 refetch，不清除缓存
queryResult.refetch()
```

**影响**:
- 同步成功后，refetch() 仍然返回缓存的旧数据（包含 null）
- 用户看到的数据没有更新
- 即使数据库中已有名称，前端仍显示 null

**修复**:
```typescript
// 修复后 - 先使缓存失效，再 refetch
await queryClient.invalidateQueries({ queryKey: ['insights-data', activeQuery] })
queryResult.refetch()
```

同时添加了 `useQueryClient` hook:
```typescript
const queryClient = useQueryClient()
```

## 修复的文件清单

### 后端
1. `api/services/entity_names_sync_service.py`
   - 第 209-231 行：添加 account_id 到 upsert 查询条件

2. `api/services/insights_service.py`
   - 第 478-492 行：修改 `_attach_entity_names()` 方法签名，添加 account_id 参数
   - 第 513-541 行：添加 account_id 过滤到所有实体名称查询
   - 第 741-743 行：调用 `_attach_entity_names()` 时传递 account_id
   - 第 708-735 行：初始化聚合查询结果的名称字段

### 前端
1. `frontend/src/features/insights-data/InsightsDataPage.tsx`
   - 第 2 行：添加 `useQueryClient` 导入
   - 第 75 行：初始化 `queryClient`
   - 第 290-291 行：同步成功后使缓存失效
   - 第 476-477 行：手动刷新按钮使缓存失效
   - 第 461-482 行：添加"刷新实体名称"按钮

### 文档
1. `CLAUDE.md`
   - 第 250-304 行：添加"Entity Names Synchronization System"章节
   - 记录架构、常见问题和最佳实践

## 测试验证

所有级别的查询都已验证通过：

```bash
# Campaign 级别
curl "http://localhost:8000/insights/query?ad_account_id=1244295750378353&since=2025-07-22&until=2025-08-31&level=campaign&time_increment=1"
# ✅ 结果: 2 个 campaigns，名称全部正确显示

# AdSet 级别
curl "http://localhost:8000/insights/query?ad_account_id=1244295750378353&since=2025-07-22&until=2025-08-31&level=adset&time_increment=1"
# ✅ 结果: 7 条记录，名称全部正确显示

# Ad 级别
curl "http://localhost:8000/insights/query?ad_account_id=1244295750378353&since=2025-07-22&until=2025-08-31&level=ad&time_increment=1"
# ✅ 结果: 所有 ads，名称全部正确显示
```

数据库验证：
```python
# 检查缺失的名称
python check_missing_names.py
# ✅ 结果: Ads: 0 缺失, AdSets: 0 缺失, Campaigns: 0 缺失
```

## 预防措施和最佳实践

为了避免类似问题再次发生，请遵循以下最佳实践：

### 1. 数据库查询规范
- **始终在查询和 upsert 时包含 account_id 过滤**
- 实体的唯一标识是 `(account_id, entity_type, entity_id)` 三元组
- 示例：
  ```python
  await AdEntityNamesDocument.find(
      AdEntityNamesDocument.account_id == account_id,
      AdEntityNamesDocument.entity_type == entity_type,
      In(AdEntityNamesDocument.entity_id, list(entity_ids)),
  ).to_list()
  ```

### 2. 前端缓存管理
- **数据变更后必须使缓存失效**
- 使用 `queryClient.invalidateQueries()` 而不是仅 `refetch()`
- 示例：
  ```typescript
  await queryClient.invalidateQueries({ queryKey: ['insights-data', activeQuery] })
  queryResult.refetch()
  ```

### 3. 聚合查询规范
- **始终初始化名称字段为 None**
- 在构建聚合结果时，显式设置 `ad_name`, `adset_name`, `campaign_name` 为 `None`
- 让 `_attach_entity_names()` 方法统一处理名称附加

### 4. 错误处理
- 妥善处理 Facebook API 速率限制（错误码 80004）
- 使用指数退避策略重试
- 向用户显示友好的错误消息

## 用户使用指南

当在数据洞察页面看到实体名称为空时：

1. **自动同步**：页面会自动检测并同步未命名的实体
2. **手动刷新**：点击"刷新实体名称"按钮强制重新同步
3. **完全刷新**：点击"刷新数据"按钮重新查询数据

如果仍然显示 null：
1. 检查网络连接
2. 查看是否有速率限制提示
3. 等待几秒后再次点击"刷新实体名称"

## 技术债务清理建议

1. **清理重复的实体名称记录**
   - 数据库中存在大量重复的实体名称（同一 entity_id 被保存为多种 entity_type）
   - 建议添加数据清理脚本，删除不必要的重复记录

2. **添加索引优化**
   - 为 `AdEntityNamesDocument` 添加复合索引 `(account_id, entity_type, entity_id)`
   - 提高查询性能

3. **考虑缓存策略**
   - 实体名称相对稳定，可以考虑在服务端添加短期缓存
   - 减少对 MongoDB 的重复查询

## 相关文档

- 项目文档: `CLAUDE.md` - "Entity Names Synchronization System" 章节
- API 文档: `/insights/sync-entity-names` 端点说明
- 数据模型: `utils/db.py` - `AdEntityNamesDocument`
