# Facebook 广告自动化调控系统 - 架构分析概览

**分析日期**: 2025-12-05
**分析范围**: 前后端架构、功能点、潜在问题、技术债务
**代码规模**: 后端 ~7500 行 Python，前端 ~2095 行 TypeScript

---

## 执行摘要

本系统是一个**数据驱动的 Facebook 广告自动化管理平台**，通过结合机器学习预测和规则引擎实现智能广告调控。系统架构现代化，采用全异步设计，但存在一些需要立即解决的生产环境风险。

### 核心价值

1. **自动化决策**: 基于 ROAS 目标自动评估广告性能
2. **规则引擎**: 灵活的 Python 脚本规则系统，支持复杂业务逻辑
3. **ML 集成**: HistGradientBoostingClassifier 预测广告停止概率
4. **混合数据源**: MongoDB 历史 + Redis 实时 + Facebook API 增量查询
5. **分布式调度**: Redis 分布式锁实现 Leader 选举和任务调度

### 技术栈

#### 后端
- **框架**: FastAPI (ASGI 异步)
- **数据库**: MongoDB (Beanie ODM) + Redis (缓存/队列)
- **机器学习**: scikit-learn (HistGradientBoostingClassifier)
- **调度**: APScheduler + 分布式 Leader 选举
- **服务器**: Granian (Rust ASGI 服务器)

#### 前端
- **框架**: React 18 + TypeScript 5.6
- **构建**: Vite 6 (路由级代码分割)
- **状态**: TanStack React Query 5 (无 Redux)
- **UI**: Ant Design 5 + 自定义 CSS 组件系统
- **图表**: Recharts 3

#### 部署
- **容器化**: Docker Compose
- **反向代理**: Traefik (OIDC 认证)
- **前端服务器**: Nginx (SPA 路由支持)

---

## 架构评级

| 维度 | 评级 | 说明 |
|------|------|------|
| **技术选型** | ⭐⭐⭐⭐⭐ | 现代化技术栈，异步优先，性能优秀 |
| **代码质量** | ⭐⭐⭐⭐ | 结构清晰，但缺少类型注解和测试 |
| **可维护性** | ⭐⭐⭐⭐ | 分层设计良好，职责单一 |
| **安全性** | ⭐⭐⭐ | 存在注入风险、日志泄露、CORS 过宽 |
| **性能** | ⭐⭐⭐⭐ | 多级缓存优化，但有 N+1 查询问题 |
| **测试覆盖** | ⭐ | 几乎无单元测试和集成测试 |
| **文档** | ⭐⭐⭐ | CLAUDE.md 详细，但代码注释不足 |

**总体评分**: 3.7 / 5.0 ⭐⭐⭐⭐

---

## 关键发现

### ✅ 架构优势

1. **全栈异步设计**
   - FastAPI + Motor + aioredis 全异步
   - 高并发支持 (10k+ QPS 潜力)
   - 异步任务管理 (Facebook Insights API)

2. **智能数据分层**
   - MongoDB: 历史数据 (>3天)
   - Redis: 实时缓存 (最近3天)
   - Facebook API: 按需增量获取
   - 减少 API 调用，降低成本

3. **规则引擎创新**
   - RestrictedPython 沙箱执行
   - JSON Schema 参数化配置
   - 支持 ML 预测集成
   - 实时测试功能

4. **前端性能优化**
   - 路由级代码分割 (7 个独立 chunk)
   - 细粒度 vendor chunks (Ant Design 图标单独打包)
   - Terser 压缩 + Tree Shaking
   - 生产包仅 1.5M

5. **分布式调度**
   - Redis SETNX 原子锁实现 Leader 选举
   - 多实例部署自动选主
   - 任务队列 BRPOP 原子出队

### ⚠️ 严重问题（需立即修复）

1. **缺少全局异常处理和日志系统** (Critical)
   - 使用 `print()` 而非 structured logging
   - 异常信息直接暴露给用户
   - 生产环境难以追踪问题

2. **数据库连接池未配置** (Critical)
   - 无最大连接数限制
   - 高并发下可能连接耗尽
   - 建议: 配置 `maxPoolSize=50`

3. **NoSQL 注入风险** (Critical)
   - 聚合查询的 `field_name` 未验证
   - 可能导致数据泄露或 DoS

4. **内存泄漏风险** (High)
   - `_from_last_cache` 无限增长
   - 无 LRU 淘汰机制
   - 建议: 使用 `TTLCache(maxsize=1000)`

5. **并发安全问题** (High)
   - Flyweight 工厂存在 Race Condition
   - 多协程可能创建重复 API 实例

6. **N+1 查询问题** (High)
   - `_attach_entity_names` 可能多次查询
   - 建议批量预加载

### 🔄 技术债务

1. **权限系统未实现**
   - `BIUserAdAccountLink` 模型存在但未使用
   - 所有用户可见所有账户
   - TODO 标记: `ad_accounts.py:33, :70`

2. **缺少 API 限流**
   - 无请求速率限制
   - 易受 DDoS 攻击

3. **测试覆盖不足**
   - 无单元测试
   - 无集成测试
   - 无 E2E 测试

4. **硬编码配置**
   - `REALTIME_LOOKBACK_DAYS = 3`
   - `MAX_ENTITY_NAME_BATCH_SIZE = 50`

---

## 功能模块清单

### 后端 API 端点 (58 个)

| 模块 | 端点数 | 核心功能 |
|------|--------|----------|
| **Health** | 1 | 健康检查 |
| **User** | 1 | 用户信息 |
| **Ad Accounts** | 2 | 账号管理 |
| **Insights** | 18 | 数据查询/同步/异步任务 |
| **Predictions** | 2 | ML 广告评估 |
| **Ad Control** | 6 | 广告启停/预算管理/活动日志 |
| **Rules** | 11 | 规则定义/绑定/执行/测试 |
| **Scheduler** | 5 | 调度器监控 |
| **FB Auth** | 4 | Facebook 凭证管理 |

### 前端功能页面 (7 个)

1. **Insights 数据浏览** (`InsightsDataPage.tsx`, 2507 行)
   - 四层级聚合 (Account/Campaign/AdSet/Ad)
   - 智能实体名称同步
   - 4 种数据源切换
   - 高级表格 (列自定义、分页)
   - 趋势图表 (Recharts)

2. **规则定义管理** (`RuleDefinitionsPage.tsx`)
   - 规则 CRUD
   - 版本控制和克隆
   - 参数 JSON Schema 配置
   - 状态管理 (Draft/Published/Disabled)

3. **规则绑定管理** (`RuleBindingsPage.tsx`)
   - 规则与广告实体绑定
   - 动态参数表单
   - 实时测试面板

4. **执行日志** (`ExecutionLogsPage.tsx`)
   - 规则执行审计
   - 错误追踪
   - 上下文快照

5. **调度监控** (`SchedulerPage.tsx`)
   - APScheduler 任务状态
   - 执行延迟监控
   - 错误信息展示

6. **数据同步** (`InsightsSyncPage.tsx`)
   - MongoDB/Redis 同步管理
   - 同步历史记录
   - 数据覆盖范围展示

7. **Facebook 授权** (`FacebookAuthPage.tsx`)
   - FB 凭证管理
   - Token 刷新
   - 账号同步

---

## 数据流架构

```
┌─────────────────────────────────────────────────────────┐
│                     用户请求                            │
│              (React + React Query)                      │
└───────────────────┬─────────────────────────────────────┘
                    │
          ┌─────────▼─────────┐
          │  Traefik (OIDC)   │
          │  X-User-Id 注入   │
          └─────────┬─────────┘
                    │
          ┌─────────▼─────────┐
          │  FastAPI Router   │
          │  (9 个模块)       │
          └─────────┬─────────┘
                    │
          ┌─────────▼─────────┐
          │   Service Layer   │
          │   (17 个服务)     │
          └───┬───────┬───┬───┘
              │       │   │
      ┌───────▼───┐   │   │
      │  MongoDB  │   │   │
      │  (Beanie) │   │   │
      └───────────┘   │   │
              ┌───────▼───┐  │
              │   Redis   │  │
              │  (缓存)   │  │
              └───────────┘  │
                      ┌──────▼──────┐
                      │ Facebook    │
                      │ Ads API     │
                      └─────────────┘
                    ┌──────▼──────┐
                    │  ML Model   │
                    │ (sklearn)   │
                    └─────────────┘
```

---

## 目录结构

```
ad_regulation/
├── backend/                    # Python 后端
│   ├── api/                    # FastAPI 应用
│   │   ├── app.py              # 应用入口 (215行)
│   │   ├── routers/            # 路由层 (10 模块)
│   │   ├── services/           # 服务层 (17 服务)
│   │   ├── models/             # Pydantic 模型 (8 文件)
│   │   └── dependencies/       # DI (认证/数据库)
│   ├── utils/                  # 工具函数
│   │   ├── db.py               # Beanie 模型 (386行)
│   │   ├── fb_api_flyweight_factory.py
│   │   ├── redis_client.py     # Redis 管理
│   │   └── insight_tool.py     # Insights 工具
│   ├── baseline/               # ML 基线
│   │   ├── data_build.py       # 特征工程
│   │   ├── train_tools.py      # 模型训练
│   │   └── get_data.py         # 数据获取
│   └── rules/scripts/          # 规则脚本示例
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── api/                # API 客户端 (6 模块)
│   │   ├── components/         # 可复用组件 (6 个)
│   │   ├── features/           # 功能模块 (7 页面)
│   │   ├── lib/                # 工具函数
│   │   ├── types/              # TS 类型定义
│   │   ├── App.tsx             # 路由配置
│   │   └── main.tsx            # 应用入口
│   ├── vite.config.ts          # Vite 配置
│   └── nginx.conf.template     # Nginx 配置
├── http/                       # Docker 部署
│   ├── compose.dev.yml         # 开发环境
│   ├── compose.yml             # 生产环境
│   └── traefik/                # Traefik 配置
└── docs/
    └── refectoring_preparation/ # 架构分析文档
```

---

## 关键指标

### 后端
- **服务层代码**: 7500 行 Python
- **API 端点**: 58 个
- **数据库模型**: 12 个 Document
- **服务类**: 17 个
- **调度器**: 3 个 (Insights 同步、Redis 缓存、规则执行)

### 前端
- **代码规模**: 2095 行 TypeScript
- **功能页面**: 7 个
- **可复用组件**: 6 个
- **生产构建**: 1.5M (gzip 后更小)
- **路由级代码分割**: 7 个独立 chunk

### 数据库
- **MongoDB Collections**: 12 个
- **Redis 缓存**: 最近 3 天 Insights 数据
- **索引**: 9 个复合/唯一索引

---

## 下一步行动

### 立即修复 (1-2 周)
1. 实现全局异常处理和结构化日志
2. 配置数据库连接池
3. 修复 NoSQL 注入风险
4. 修复内存泄漏 (TTLCache)
5. 解决 Flyweight 并发安全问题

### 短期改进 (1 个月)
6. 添加 API 速率限制和重试机制
7. 优化 N+1 查询问题
8. 敏感信息脱敏
9. 添加输入验证和日期范围限制
10. 实现事务处理

### 中期目标 (2-3 个月)
11. 实现权限系统 (BIUserAdAccountLink)
12. 添加单元测试 (目标 80% 覆盖率)
13. 配置化硬编码常量
14. 完善健康检查端点
15. 优化 CORS 配置

### 长期演进 (持续)
16. 提取可复用组件库
17. 添加 E2E 测试 (Playwright)
18. 集成监控系统 (Sentry + Prometheus)
19. 性能优化 (虚拟滚动、Web Worker)
20. 微前端架构探索

---

## 相关文档

- `01_backend_architecture.md` - 后端架构详细分析
- `02_frontend_architecture.md` - 前端架构详细分析
- `03_potential_issues.md` - 潜在问题和 Bug 清单
- `04_data_flow.md` - 数据流和集成分析
- `05_refactoring_recommendations.md` - 重构建议和最佳实践

---

**文档版本**: 1.0
**最后更新**: 2025-12-05
**分析工具**: Claude Code (Explore Agent)
