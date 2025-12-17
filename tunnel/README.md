# Ad Regulation HTTP 部署

HTTP 模式部署配置，通过 Cloudflare Tunnel 或自建 Tunnel 对外暴露 HTTPS 服务。

## 架构

```
用户 (HTTPS)
 ↓
Cloudflare Tunnel / 自建 Tunnel
 ↓ (HTTP)
Traefik (gateway, 监听 8080)
 ↓
frontend (nginx)
 ↓ (内部网络)
backend (uvicorn)
 ↓ (内部网络)
mongodb
```

**说明**:
- 内部服务使用 HTTP 通信（无需配置 HTTPS）
- Traefik 监听 8080 端口，接收来自 Tunnel 的 HTTP 流量
- Cloudflare Tunnel 或自建 Tunnel 负责 TLS 终止，对外暴露 HTTPS
- 用户访问 `https://fb.${DOMAIN}` 时，流量经过 Tunnel 加密传输

## 网络架构

- **内部网络**: `ad-regulation-http_internal`
  - mongodb: 仅内部网络
  - backend: 仅内部网络
  - frontend: 桥接内外网络

- **外部网络**: `gateway`
  - frontend: 使用别名 `ad-regulation-http-frontend`

## 快速开始

### 生产模式

**单域名部署**（默认）:
```bash
./start.sh
```

**双域名部署**:
```bash
./start.sh --dual-domain
# 或简写
./start.sh -d
```

访问地址:
- 单域名: `https://${COMPOSE_PROJECT_NAME}.${DOMAIN}` (通过 Tunnel 暴露)
- 双域名: `https://${COMPOSE_PROJECT_NAME}.${DOMAIN}` 和 `https://${COMPOSE_PROJECT_NAME}.${DOMAIN2}` (通过 Tunnel 暴露)

### 开发模式

**单域名开发**（默认）:
```bash
./dev.sh
```

**双域名开发**:
```bash
./dev.sh --dual-domain
# 或简写
./dev.sh -d
```

访问地址:
- 生产环境（带认证）: `https://${COMPOSE_PROJECT_NAME}.${DOMAIN}` (通过 Tunnel 暴露)
- 开发环境（无认证）: `https://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}` (通过 Tunnel 暴露)
- 双域名模式: 每个域名都支持对应的 `-dev` 子域名
- 本地测试（绕过 Tunnel）: `curl --resolve ${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}:8080:127.0.0.1 http://${COMPOSE_PROJECT_NAME}-dev.${DOMAIN}:8080`

### 停止服务

```bash
# 停止所有容器
./stop.sh

# 仅停止开发容器（保留基础设施）
./dev-stop.sh
```

## 配置说明

### 环境变量 (.env)

```env
COMPOSE_PROJECT_NAME=ad-regulation-http  # 项目名称
DOMAIN=moondeity.dpdns.org               # 主域名
DOMAIN2=example.com                      # 第二域名（仅双域名部署使用）
MONGO_INITDB_ROOT_USERNAME=admin         # MongoDB 用户名
MONGO_INITDB_ROOT_PASSWORD=admin123      # MongoDB 密码
```

### Compose 文件组织

项目采用模块化 compose 文件设计，通过组合不同文件实现灵活部署：

**基础文件**:
- `docker-compose.yml` - 基础配置（mongodb, redis, backend, frontend 基础配置，不含 Traefik labels）

**生产环境域名配置**:
- `compose.single-domain.yml` - 单域名 Traefik 路由（带 OIDC 认证）
- `compose.dual-domain.yml` - 双域名 Traefik 路由（带 OIDC 认证）

**开发环境配置**:
- `compose.dev.yml` - 开发容器定义（backend-dev, frontend-dev，不含路由）
- `compose.dev-single.yml` - 开发单域名路由（绕过认证）
- `compose.dev-dual.yml` - 开发双域名路由（绕过认证）

**组合方式**:
```bash
# 单域名生产
docker compose -f docker-compose.yml -f compose.single-domain.yml up -d

# 双域名生产
docker compose -f docker-compose.yml -f compose.dual-domain.yml up -d

# 单域名开发
docker compose -f docker-compose.yml -f compose.single-domain.yml -f compose.dev.yml -f compose.dev-single.yml up -d

# 双域名开发
docker compose -f docker-compose.yml -f compose.dual-domain.yml -f compose.dev.yml -f compose.dev-dual.yml up -d
```

**优势**:
- ✅ 消除重复代码，基础配置统一管理
- ✅ 灵活切换单/双域名，无需修改文件
- ✅ 清晰的配置分层，易于理解和维护
- ✅ 脚本封装细节，用户只需关注 `--dual-domain` 参数

### 服务端口

生产模式:
- Traefik: 8080 (宿主机，接收 Tunnel 流量)
- frontend: 80 (内部)
- backend: 8000 (内部)
- mongodb: 27017 (内部)

开发模式（额外）:
- mongodb: 27017 (暴露到宿主机)

### Tunnel 配置

本项目使用 Cloudflare Tunnel 或自建 Tunnel 将内部 HTTP 服务暴露为公网 HTTPS:

1. **Cloudflare Tunnel** (推荐)
   - 自动处理 TLS 证书
   - 配置文件: `tunnel/cloudflared/config.yml`
   - 指向: `http://localhost:8080`

2. **自建 Tunnel**
   - 使用 frp/ngrok 等工具
   - 需要自行配置 TLS 终止
   - 转发到: `http://localhost:8080`

**重要**: 内部服务无需配置 HTTPS，所有 TLS 加密由 Tunnel 层处理。

## 开发模式特性

HTTP 模式使用独立容器策略:

1. **独立的开发容器**
   - `backend-dev`: 独立的后端容器，启用热重载
   - `frontend-dev`: 独立的前端容器
   - 与生产容器完全隔离

2. **代码热重载**
   - 挂载本地代码目录
   - 修改代码后自动重启

3. **无需认证**
   - 开发域名 `fb-dev.${DOMAIN}` 绕过 OIDC 认证
   - 直接访问后端 API

4. **保留基础设施**
   - `dev-stop.sh` 仅停止 backend-dev 和 frontend-dev
   - mongodb 保持运行，加快下次启动

## 常用命令

```bash
# 查看容器状态
docker compose ps

# 查看日志
docker compose logs -f
docker compose logs -f backend

# 重启服务
docker compose restart backend

# 进入容器
docker compose exec backend bash
docker compose exec mongodb mongosh

# 清理所有数据（危险操作）
docker compose down -v
```

## 网络隔离说明

项目采用双网络架构，确保安全性和服务隔离:

1. **内部网络** (`ad-regulation-http_internal`)
   - 项目专属网络
   - 所有服务间通信使用简单服务名（mongodb, backend, frontend）
   - 不与其他项目冲突

2. **外部网络** (`gateway`)
   - 仅 frontend 连接
   - 使用网络别名 `ad-regulation-http-frontend` 确保唯一性
   - 通过 Traefik 提供外部访问

## 多实例支持

本配置支持同时运行多个实例:

```bash
# 实例 1（默认）
COMPOSE_PROJECT_NAME=ad-regulation-http docker compose up -d

# 实例 2（测试环境）
COMPOSE_PROJECT_NAME=ad-regulation-http-test docker compose up -d
```

每个实例拥有:
- 独立的容器名称
- 独立的内部网络
- 独立的数据卷
- 独立的网络别名

## 故障排除

### 404 错误

检查 backend 容器是否正常运行:
```bash
docker compose ps backend
docker compose logs backend
```

### 连接数据库失败

检查 mongodb 容器状态:
```bash
docker compose ps mongodb
docker compose logs mongodb
```

### 端口冲突

检查是否有其他服务占用端口:
```bash
docker compose ps
lsof -i :27017
```

## 更多信息

- 开发模式详细说明: [dev.md](dev.md)
- 项目根目录: `/home/lprintf/workspace/ad_regulation/`
