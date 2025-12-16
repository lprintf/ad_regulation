# Ad Regulation HTTP 部署

HTTP 模式部署配置，适用于本地开发或无需 HTTPS 的环境。

## 架构

```
用户
 ↓
Traefik (gateway-http)
 ↓
frontend (nginx)
 ↓ (内部网络)
backend (uvicorn)
 ↓ (内部网络)
mongodb
```

## 网络架构

- **内部网络**: `ad-regulation-http_internal`
  - mongodb: 仅内部网络
  - backend: 仅内部网络
  - frontend: 桥接内外网络

- **外部网络**: `gateway-http`
  - frontend: 使用别名 `ad-regulation-http-frontend`

## 快速开始

### 生产模式

```bash
./start.sh
```

访问地址: `http://fb.${DOMAIN}`

### 开发模式

```bash
./dev.sh
```

访问地址:
- 生产环境（带认证）: `http://fb.${DOMAIN}`
- 开发环境（无认证）: `http://fb-dev.${DOMAIN}`

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
DOMAIN=moondeity.dpdns.org               # 域名
MONGO_INITDB_ROOT_USERNAME=admin         # MongoDB 用户名
MONGO_INITDB_ROOT_PASSWORD=admin123      # MongoDB 密码
```

### 服务端口

生产模式:
- frontend: 80 (内部)
- backend: 8000 (内部)
- mongodb: 27017 (内部)

开发模式（额外）:
- mongodb: 27017 (暴露到宿主机)

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

2. **外部网络** (`gateway-http`)
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
