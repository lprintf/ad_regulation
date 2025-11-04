## Frontend Rule Engine Console

### 目标

根据 `docs/rule_engine_development_plan.md` 的 Phase 4 规划，实现一套规则引擎可视化管理界面，覆盖规则元数据维护、绑定关系管理、执行日志溯源以及 APScheduler 调度监控，为运营和研发提供统一的可视化入口。

### 技术栈

- Vite 6 + React 18 + TypeScript
- React Router 6 负责前端路由
- TanStack Query 管理数据获取与缓存
- Axios 适配现有 FastAPI `rules/*` REST 接口
- CSS 原子样式（原生变量 + 自定义组件样式），无第三方 UI 依赖，方便按需定制

### 目录结构

```
frontend/
├── src/
│   ├── api/                # REST API 封装（规则定义、绑定、执行、调度）
│   ├── components/
│   │   └── layout/         # AppLayout、Sidebar、Topbar
│   ├── features/
│   │   ├── rule-definitions/  # 规则 CRUD 页面与表单
│   │   ├── rule-bindings/     # 绑定列表与表单
│   │   ├── execution-logs/    # 执行日志列表与详情
│   │   └── scheduler/         # APScheduler 任务监控
│   ├── lib/                # axios client、时间格式化工具
│   ├── types/              # 规则领域类型定义
│   ├── App.tsx             # 路由入口
│   ├── main.tsx            # React 挂载入口
│   └── index.css           # 全局样式
├── index.html
├── package.json
└── tsconfig.json
```

### 安装与启动

```bash
cd frontend
npm install
npm run dev # 默认 http://localhost:5173
```

打包 & 预览：

```bash
npm run build
npm run preview
```

### 环境变量

- `VITE_API_BASE_URL`（可选，默认 `http://localhost:8000`）
- `VITE_DEFAULT_USER_ID`（可选，为 Axios 请求设置 `X-User-Id` Header，便于调试）

### 页面概览

1. **规则定义**
   - 列表展示规则名称、版本、状态、标签、更新时间等信息。
   - 支持关键字搜索、状态筛选。
   - 表单支持 Python 规则脚本、参数配置、标签填写。
   - 样式对齐 `docs/rule_engine_development_plan.md` 中的参数化、沙箱发布要求。

2. **规则绑定**
   - 按实体类型、规则、启用状态过滤。
   - 支持 JSON 元数据填写、备注记录，配合自动解绑策略。
   - 支持启用/停用、删除操作，调用 `/rules/bindings` 系列 API。

3. **执行日志**
   - 实时轮询（30s）展示最新执行结果。
   - 支持按规则、状态、触发类型过滤，并一键重试。
   - 详情面板展示动作、原因代码、指标和上下文快照，便于审计。

4. **调度监控**
   - 对接 `/rules/scheduler/tasks` 系列接口，展示 Cron 配置、延迟、报错信息。
   - 支持任务暂停 / 恢复、立即执行。

### 与后端的接口约束

- 所有请求默认携带 `X-User-Id`，可在 `.env` 中配置。
- API 响应约定遵循 `data.items` 或 `data` 包装格式，兼容当前 FastAPI 响应体。
- 若后端暂未落地 `/rules/scheduler/*` 接口，可先使用 mock 数据或临时返回空数组。

### 后续迭代建议

1. 增加代码语法高亮与静态检查提示（例如 Monaco Editor + AST 预检查）。
2. 引入角色与权限控制，实现规则审批、灰度发布流程可视化。
3. 扩展通知配置模块，对接 Webhook、Slack、邮件等渠道。
4. 与 ML 预测结果联动，提供混合决策的可视化和对比分析。
