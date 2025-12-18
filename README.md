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
│   ├── api/              # FastAPI 应用
│   ├── baseline/         # ML 数据管道
│   ├── utils/            # 核心工具
│   └── config.py         # 配置文件
├── frontend/             # 前端代码（React + TypeScript）
├── tunnel/               # 部署配置（Cloudflare Tunnel + Traefik）
│   ├── docker-compose.yml            # 基础配置
│   ├── compose.single-domain.yml     # 单域名路由
│   ├── compose.dual-domain.yml       # 双域名路由
│   ├── compose.dev.yml               # 开发容器
│   ├── compose.dev-single.yml        # 开发单域名路由
│   ├── compose.dev-dual.yml          # 开发双域名路由
│   ├── .env
│   ├── start.sh, dev.sh, stop.sh, dev-stop.sh
│   ├── README.md
│   └── dev.md
└── README.md             # 本文件
```

## 快速开始

### Docker 部署（推荐）

```bash
cd tunnel/

# 单域名生产模式
./start.sh

# 双域名生产模式
./start.sh --dual-domain

# 开发模式（支持热重载）
./dev.sh                # 单域名
./dev.sh --dual-domain  # 双域名
```

**访问地址**（通过 Cloudflare Tunnel 暴露 HTTPS）:
- 生产: `https://${COMPOSE_PROJECT_NAME}.${DOMAIN}` (OIDC 认证)
- 开发: `https://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}` (无认证)
- 本地测试: `curl --resolve ${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}:8080:127.0.0.1 http://...`

详见 [tunnel/README.md](tunnel/README.md)

### 本地开发（不使用 Docker）

#### 1. 安装依赖

```bash
cd backend
uv sync
```

#### 2. 配置环境变量

```bash
# 本地开发环境（直接运行 Python）
export MONGODB_HOST=localhost
export MONGODB_PORT=27017
export MONGODB_DB_NAME=fb  # 或使用任意数据库名
export MONGO_INITDB_ROOT_USERNAME=admin
export MONGO_INITDB_ROOT_PASSWORD=admin123
```

**注意**: 容器部署时，这些变量会通过 `.env` 文件和 `docker-compose.yml` 自动配置。

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
cd tunnel/
./dev.sh

# 修改代码（自动热重载）
vim ../backend/api/routers/ad_accounts.py

# 查看日志
docker compose logs -f backend-dev
```

### 前端开发

```bash
# 启动开发环境
cd tunnel/
./dev.sh

# 修改前端代码
cd ../frontend
vim src/App.tsx

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

编辑 `tunnel/.env`:

```env
COMPOSE_PROJECT_NAME=fb
DOMAIN=moondeity.dpdns.org
DOMAIN2=example.com  # 双域名部署时使用
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123
```

## 从旧版本迁移

如果你之前使用旧的部署方式:

1. **停止旧容器**
   ```bash
   docker compose down
   ```

2. **启动新版本**
   ```bash
   cd tunnel/
   ./start.sh  # 或 ./start.sh --dual-domain
   ```

数据卷会自动保留（根据 `COMPOSE_PROJECT_NAME` 识别）。

## 详细文档

- [部署文档](tunnel/README.md)
- [开发指南](tunnel/dev.md)
- [架构文档](CLAUDE.md)

**历史文档** (不推荐使用):
- [HTTPS 部署](https/README.md) - 旧版 HTTPS 配置（已被 tunnel/ 替代）


## 技术栈

- **后端**: FastAPI + MongoDB + uvicorn
- **前端**: Vue.js + nginx
- **机器学习**: scikit-learn (HistGradientBoostingClassifier)
- **部署**: Docker Compose + Traefik
- **认证**: OIDC (Zitadel)

## License

MIT
