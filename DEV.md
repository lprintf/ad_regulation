# 开发指南

## 目录结构

```
ad_regulation/
├── backend/
│   └── Dockerfile           # 后端容器配置
├── frontend/
│   ├── Dockerfile          # 前端容器配置
│   ├── nginx.conf.template # 生产环境 nginx 配置
│   └── nginx.dev.conf.template # 开发环境 nginx 配置（包含 /docs 代理）
├── api/                    # FastAPI 后端代码
├── utils/                  # 工具模块
├── compose.yml            # 生产环境 Docker Compose 配置
└── compose.dev.yml        # 开发环境 Docker Compose 配置
```

## 开发模式

开发模式支持代码热重载，无需重新构建容器即可看到代码更改。

### 启动开发环境

```bash
# 启动所有服务（开发模式）
docker compose -f compose.yml -f compose.dev.yml up

# 后台启动
docker compose -f compose.yml -f compose.dev.yml up -d

# 查看日志
docker compose -f compose.yml -f compose.dev.yml logs -f
```

### 开发模式特性

**后端 (FastAPI)**:
- ✅ 代码热重载（uvicorn --reload）
- ✅ 挂载本地代码目录（api/, utils/, config.py）
- ✅ 独立的开发路由：`fb-dev.${DOMAIN}` (无 OIDC 认证，便于测试)
- ✅ MongoDB 端口暴露：`27017` (便于本地调试)

**前端 (React + Vite)**:
- ✅ 挂载本地构建的 dist 目录
- ✅ 代理 FastAPI 文档接口 (/docs, /redoc, /openapi.json)
- ✅ 需要手动构建前端后刷新浏览器查看更改

### 前端开发流程

由于前端使用静态容器 + nginx 提供服务，开发时需要：

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖（首次）
pnpm install

# 3. 启动本地开发服务器（热重载）
pnpm run dev
# 访问 http://localhost:5173

# 或者：构建后通过容器访问
pnpm run build
# 访问 https://fb.${DOMAIN}
```

**推荐工作流**：
- 前端开发：使用 `pnpm run dev` 获得最快的热重载体验
- 后端开发：Docker Compose 自动热重载
- 集成测试：构建前端后通过容器访问完整应用

### 后端开发流程

```bash
# 修改 api/ 或 utils/ 下的代码
# uvicorn 会自动检测并重载

# 查看后端日志
docker compose -f compose.yml -f compose.dev.yml logs -f backend

# 访问 API 文档
# 通过前端：https://fb.${DOMAIN}/docs
# 直连后端：https://fb-dev.${DOMAIN}/docs (无需 OIDC 认证)
```

## 生产模式

生产模式使用优化的容器配置，无热重载。

### 启动生产环境

```bash
# 启动所有服务
docker compose up

# 后台启动
docker compose up -d

# 重新构建并启动
docker compose up --build
```

### 生产模式特性

**后端**:
- ✅ 使用 uvloop 提升性能
- ✅ 无热重载，稳定运行
- ✅ OIDC 认证保护

**前端**:
- ✅ 构建优化的静态资产
- ✅ Nginx 高性能服务
- ✅ OIDC 认证保护

## 访问地址

| 服务 | 生产模式 | 开发模式 |
|------|---------|----------|
| 前端 | `https://fb.${DOMAIN}` | `https://fb.${DOMAIN}` |
| 后端 API (通过前端代理) | `https://fb.${DOMAIN}/api` | `https://fb.${DOMAIN}/api` |
| 后端 API (直连，无认证) | ❌ | `https://fb-dev.${DOMAIN}` |
| FastAPI 文档 | `https://fb.${DOMAIN}/docs` | `https://fb.${DOMAIN}/docs` 或 `https://fb-dev.${DOMAIN}/docs` |
| MongoDB | ❌ | `localhost:27017` |

## 环境变量

需要在 `.env` 文件中配置：

```bash
# MongoDB 配置
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=your_password

# Traefik 域名
DOMAIN=127.0.0.1.sslip.io
```

## 常用命令

```bash
# 停止所有服务
docker compose -f compose.yml -f compose.dev.yml down

# 停止并删除数据卷
docker compose -f compose.yml -f compose.dev.yml down -v

# 重新构建特定服务
docker compose -f compose.yml -f compose.dev.yml up --build backend
docker compose -f compose.yml -f compose.dev.yml up --build frontend

# 查看服务状态
docker compose -f compose.yml -f compose.dev.yml ps

# 进入容器
docker compose -f compose.yml -f compose.dev.yml exec backend bash
docker compose -f compose.yml -f compose.dev.yml exec frontend sh
```

## 故障排查

### 后端无法连接 MongoDB

检查 MongoDB 是否正常启动：
```bash
docker compose -f compose.yml -f compose.dev.yml logs mongodb
```

### 前端无法访问后端 API

1. 检查 nginx 配置中的后端服务名是否正确（`fb-backend-1`）
2. 查看前端容器日志：
   ```bash
   docker compose -f compose.yml -f compose.dev.yml logs frontend
   ```

### 代码修改后未生效

**后端**：
- 检查文件是否正确挂载
- 查看 uvicorn 重载日志

**前端**：
- 需要重新构建：`cd frontend && pnpm run build`
- 或使用本地开发服务器：`pnpm run dev`
