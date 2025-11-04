# 2025-10-30 规则引擎首版集成工作日志

- 梳理 `docs/rule_engine_development_plan.md` 中的 MVP 范围，设计 `rule_definitions`/`rule_bindings`/`rule_execution_logs` 三类文档结构。
- 在 `utils/db.py` 中新增规则相关 Document，并接入 Beanie 初始化；实现 `utils/rule_sandbox.py` 作为脚本受限执行环境。
- 编写 `api/models/rules.py`、`api/services/rule_engine_service.py`，覆盖规则 CRUD、绑定管理、手动执行、自动解绑占位等核心逻辑。
- 集成 `APScheduler`（新增 `api/services/rule_scheduler.py`），在 FastAPI lifespan 中启动/关闭调度，预置每日执行、每小时扫描与自动解绑任务。
- 新建 `/rules` 路由模块，提供规则定义、绑定、执行日志等 REST API；更新 `pyproject.toml` 增加 `apscheduler` 依赖。
- 将以上改动整理为首版规则引擎后端骨架，便于后续补充命名解析、上下文数据接入与安全校验。
- 新增 `RuleContextService` 拉取真实广告元数据与近14天洞察指标，执行时仅生成建议，不直接下发调控；从 `rules/scripts/demo_spend_guard.py` 读取“素材测试规则”脚本并在启动阶段自动补种。
- 编写 `tests/run_demo_rule.py` 脚本，可通过环境变量指定广告素材，调用规则上下文与执行流程输出评估结果；支持打印完整上下文并通过 JSON mock 数据复现规则执行。
- 新增 `tests/generate_mock_data.py`，基于真实 API 数据拉取上下文并可自动匿名、附带 ML 特征模板，帮助批量生成符合真实结构的 mock 数据。
- 新建 `frontend/` React 控制台：基于 Vite + React Query 实现规则定义、规则绑定、执行日志与调度监控四大页面；封装 `api/ruleEngine.ts` 对接现有 REST 接口，提供手动执行与调度管控能力。编译通过 `npm run build`，产物用于 Phase 4 管理后台可视化。
