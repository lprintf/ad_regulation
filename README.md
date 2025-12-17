# Ad Regulation System

广告监管数据分析系统，使用 ML 驱动的广告效果评估。

## 功能特性

- **ML 驱动评估**: 使用 HistGradientBoostingClassifier 进行广告效果预测
- **数据管道**: 自动化 Facebook Ads 数据获取和特征工程
- **身份认证**: 基于 MongoDB 的凭证管理和 OIDC 认证
- **FastAPI 服务**: RESTful API 提供广告操作和评估
- **ROAS 优化**: 基于目标的广告控制建议

## 项目结构

```
ad_regulation/
├── backend/              # 后端代码（FastAPI + MongoDB）
│   ├── api/             # FastAPI 应用
│   ├── baseline/        # ML 数据管道
│   ├── utils/           # 核心工具
│   └── config.py        # 配置文件
├── frontend/             # 前端代码（Vue.js）
├── http/                 # HTTP 部署配置
│   ├── docker-compose.yml
│   ├── compose.dev.yml
│   ├── .env
│   ├── start.sh, stop.sh, dev.sh, dev-stop.sh
│   ├── README.md
│   └── dev.md
├── https/                # HTTPS 部署配置
│   ├── docker-compose.yml
│   ├── compose.dev.yml
│   ├── .env
│   ├── start.sh, stop.sh, dev.sh, dev-stop.sh
│   ├── README.md
│   └── dev.md
└── README.md             # 本文件
```

## 快速开始

### Docker 部署（推荐）

#### HTTP 模式（本地开发）

```bash
cd http/
./start.sh              # 生产模式
# 或
./dev.sh                # 开发模式（无需认证）
```

访问地址:
- 生产: `http://fb.${DOMAIN}` (需要 OIDC 认证)
- 开发: `http://fb-dev.${DOMAIN}` (无需认证)

#### HTTPS 模式（生产环境）

```bash
cd https/
./start.sh              # 生产模式
# 或
./dev.sh                # 开发模式
```

访问地址:
- 生产: `https://fb.${DOMAIN}` (需要 OIDC 认证)
- 开发: `https://fb-dev.${DOMAIN}` (直连后端，无需认证)

### 本地开发（不使用 Docker）

#### 1. 安装依赖

```bash
cd backend
uv sync
```

#### 2. 配置环境变量

```bash
export MONGODB_HOST=localhost
export MONGODB_PORT=27017
export MONGODB_DB_NAME=fb_monitor
export MONGO_INITDB_ROOT_USERNAME=admin
export MONGO_INITDB_ROOT_PASSWORD=admin123
```

#### 3. 启动 MongoDB

```bash
docker run -d -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=admin123 \
  mongo:latest
```

#### 4. 运行 API 服务器

```bash
cd backend
python run_api.py
```

API 访问地址:
- **API**: http://localhost:8000
- **文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 部署模式对比

| 特性 | HTTP 模式 | HTTPS 模式 |
|------|-----------|------------|
| TLS 加密 | ❌ | ✅ |
| OIDC 认证 | ✅ | ✅ |
| 开发策略 | 独立容器 | 覆盖模式 |
| 资源占用 | 较高 | 较低 |
| 适用场景 | 本地开发 | 生产环境 |

### HTTP 模式特点

- **独立容器策略**: 开发容器与生产容器完全隔离
- **灵活性高**: 可同时运行生产和开发环境
- **快速迭代**: 停止开发容器不影响基础设施
- **适合场景**: 本地开发、频繁测试

### HTTPS 模式特点

- **覆盖策略**: 使用 compose.dev.yml 覆盖生产配置
- **资源节约**: 同一组容器，不同配置
- **快速切换**: 生产/开发模式一键切换
- **适合场景**: 生产部署、临时调试

## 架构说明

### 网络架构

采用双网络隔离架构，确保安全性:

```
外部网络 (gateway)
  ↓ Traefik 路由和认证
frontend (nginx)
  ↓ 内部网络
backend (FastAPI)
  ↓ 内部网络
mongodb
```

### 关键设计

1. **网络隔离**
   - 内部网络: 项目专属（`${COMPOSE_PROJECT_NAME}_internal`）
   - 外部网络: 共享 gateway，frontend 使用唯一别名

2. **服务命名**
   - 内部通信: 简单服务名（mongodb, backend, frontend）
   - 外部访问: 网络别名（`${COMPOSE_PROJECT_NAME}-frontend`）

3. **多实例支持**
   - 移除 `container_name`，支持多实例运行
   - 每个实例独立的网络和数据卷

## API 使用

### 身份认证

生产环境通过 OIDC 认证，开发环境需要 `X-User-Id` 请求头:

```bash
curl -H "X-User-Id: user123" http://fb-dev.${DOMAIN}/api/ad-accounts
```

### 示例端点

**列出广告账户**
```bash
GET /api/ad-accounts
Headers: X-User-Id: user123
```

**获取广告账户详情**
```bash
GET /api/ad-accounts/act_1243925423619499
Headers: X-User-Id: user123
```

**健康检查**
```bash
GET /health
```

## 开发工作流

### 后端开发

```bash
cd http/    # 或 cd https/
./dev.sh

# 修改代码（自动重载）
vim ../backend/api/routers/ad_accounts.py

# 查看日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend
```

### 前端开发

```bash
# 启动开发环境
cd http/
./dev.sh

# 修改前端代码
cd ../frontend
vim src/App.vue

# 重新构建
npm run build
```

### 数据管道

```bash
# 获取 Facebook Ads 数据
python backend/baseline/get_data.py

# 构建特征和标签
python backend/baseline/data_build.py

# 训练模型
python backend/baseline/train_tools.py
```

## 环境配置

### HTTP 模式

编辑 `http/.env`:

```env
COMPOSE_PROJECT_NAME=ad-regulation-http
DOMAIN=moondeity.dpdns.org
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123
```

### HTTPS 模式

编辑 `https/.env`:

```env
COMPOSE_PROJECT_NAME=ad-regulation-https
DOMAIN=moondeity.dpdns.org
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123
```

## 从旧版本迁移

如果你之前使用根目录的 `compose.yml`:

1. **停止旧版本**
   ```bash
   docker compose down
   ```

2. **备份数据**（可选）
   ```bash
   # 数据卷会保留，可以手动备份
   docker volume ls | grep mongo
   ```

3. **启动新版本**
   ```bash
   # 选择 HTTP 或 HTTPS 模式
   cd http/    # 或 cd https/
   ./start.sh
   ```

## 详细文档

- [HTTP 部署文档](http/README.md)
- [HTTP 开发指南](http/dev.md)
- [HTTPS 部署文档](https/README.md)
- [HTTPS 开发指南](https/dev.md)
- [架构文档](CLAUDE.md)

## 技术栈

- **后端**: FastAPI + MongoDB + uvicorn
- **前端**: Vue.js + nginx
- **机器学习**: scikit-learn (HistGradientBoostingClassifier)
- **部署**: Docker Compose + Traefik
- **认证**: OIDC (Zitadel)

## License

MIT
