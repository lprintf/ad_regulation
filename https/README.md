# Ad Regulation HTTPS 部署

HTTPS 模式部署配置，使用 TLS 加密和 OIDC 认证，适用于生产环境。

## 架构

```
用户
 ↓ (HTTPS)
Traefik (gateway)
 ↓ (TLS termination)
frontend (nginx)
 ↓ (内部网络)
backend (uvicorn)
 ↓ (内部网络)
mongodb
```

## 网络架构

- **内部网络**: `ad-regulation-https_internal`
  - mongodb: 仅内部网络
  - backend: 仅内部网络
  - frontend: 桥接内外网络

- **外部网络**: `gateway`
  - frontend: 使用别名 `ad-regulation-https-frontend`

## 快速开始

### 生产模式

```bash
./start.sh
```

访问地址: `https://fb.${DOMAIN}`

### 开发模式

```bash
./dev.sh
```

访问地址:
- 生产环境（带认证）: `https://fb.${DOMAIN}`
- 开发环境（直连后端）: `https://fb-dev.${DOMAIN}`

### 停止服务

```bash
# 停止所有容器
./stop.sh

# 退出开发模式，恢复生产模式
./dev-stop.sh
```

## 配置说明

### 环境变量 (.env)

```env
COMPOSE_PROJECT_NAME=ad-regulation-https  # 项目名称
DOMAIN=moondeity.dpdns.org                # 域名
MONGO_INITDB_ROOT_USERNAME=admin          # MongoDB 用户名
MONGO_INITDB_ROOT_PASSWORD=admin123       # MongoDB 密码
```

### TLS 配置

TLS 证书由 Traefik 自动管理，无需额外配置。

### OIDC 认证

前端路由配置了 OIDC 认证中间件:

```yaml
labels:
  - traefik.http.routers.fb.middlewares=strip-user-headers@file,oidc-auth@file
```

认证配置在 Traefik 的动态配置文件中管理。

## 开发模式特性

HTTPS 模式使用覆盖（overlay）策略:

1. **覆盖现有容器配置**
   - 使用 `compose.dev.yml` 覆盖生产配置
   - 同一个容器，不同的启动参数
   - 节省资源，快速切换

2. **代码热重载**
   - 挂载本地代码目录
   - 后端启用 `--reload` 模式

3. **直连后端**
   - 开发域名 `fb-dev.${DOMAIN}` 直连后端
   - 绕过 nginx，直接访问 uvicorn
   - 方便测试 API

4. **快速切换**
   - `dev-stop.sh` 自动停止开发模式并恢复生产模式
   - 无需手动管理多个容器

## 服务端口

生产模式:
- frontend: 80 (内部)
- backend: 8000 (内部)
- mongodb: 27017 (内部)

开发模式（额外）:
- backend: 8000 (通过 Traefik 暴露)
- mongodb: 27017 (暴露到宿主机)

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

1. **内部网络** (`ad-regulation-https_internal`)
   - 项目专属网络
   - 所有服务间通信使用简单服务名（mongodb, backend, frontend）
   - 不与其他项目冲突

2. **外部网络** (`gateway`)
   - 仅 frontend 连接（生产模式）
   - backend 也连接（开发模式，用于直连）
   - 使用网络别名确保唯一性

## 多实例支持

本配置支持同时运行多个实例:

```bash
# 实例 1（默认）
COMPOSE_PROJECT_NAME=ad-regulation-https docker compose up -d

# 实例 2（测试环境）
COMPOSE_PROJECT_NAME=ad-regulation-https-test docker compose up -d
```

每个实例拥有:
- 独立的容器名称
- 独立的内部网络
- 独立的数据卷
- 独立的网络别名

## 安全注意事项

1. **环境变量保密**
   - `.env` 文件包含敏感信息
   - 不要提交到 git 仓库
   - 使用强密码

2. **OIDC 认证**
   - 生产环境强制启用
   - 开发域名仅用于开发，不要暴露到公网

3. **网络隔离**
   - 数据库仅在内部网络可访问
   - 生产模式下后端不暴露到外网

## 故障排除

### TLS 证书问题

检查 Traefik 日志:
```bash
docker logs traefik
```

### OIDC 认证失败

检查:
1. OIDC 配置是否正确
2. 回调 URL 是否配置正确
3. Traefik 中间件是否正确加载

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

## 更多信息

- 开发模式详细说明: [dev.md](dev.md)
- HTTP 部署方式: [../http/README.md](../http/README.md)
- 项目根目录: `/home/lprintf/workspace/ad_regulation/`
