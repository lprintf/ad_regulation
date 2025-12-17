# 部署环境依赖

**文档版本**: 1.0
**更新日期**: 2025-12-05

---

## 部署架构概览

```
用户 (HTTPS)
    ↓
Cloudflare Tunnel (监听 8080 端口)
    ↓
Traefik 反向代理 (gateway 网络)
    ↓ (Docker 服务发现)
frontend (nginx) / backend-dev (开发直连)
    ↓
backend (granian/uvicorn)
    ↓
mongodb + redis
```

---

## 核心组件

### 1. Cloudflare Tunnel

提供公网 HTTPS 访问入口：

| 配置项 | 说明 |
|--------|------|
| 监听端口 | 本地 8080 |
| 协议 | HTTPS (Cloudflare 边缘终止 TLS) |
| 生产域名 | `fb.${DOMAIN}` |
| 开发域名 | `fb-dev.${DOMAIN}` |

**访问方式**:
- 公网通过 Cloudflare Tunnel 自动获得 HTTPS
- 本地开发可通过 `--resolve` 直连：
  ```bash
  curl --resolve fb-dev.moondeity.dpdns.org:8080:127.0.0.1 \
       http://fb-dev.moondeity.dpdns.org:8080/docs
  ```

---

### 2. Traefik 反向代理

通过 Docker 服务发现自动路由请求：

| 配置项 | 说明 |
|--------|------|
| 外部网络 | `gateway` |
| 入口点 | `web` (HTTP) |
| 服务发现 | Docker Labels |

**路由规则**:

| 路由 | 域名 | 中间件 | 用途 |
|------|------|--------|------|
| `fb` | `fb.${DOMAIN}` | `oidc-auth@file` | 生产环境 (需 OIDC 认证) |
| `fb-dev` | `fb-dev.${DOMAIN}` | `strip-user-headers@file` | 开发环境 (无认证) |

**Traefik Labels 示例** (摘自 `docker-compose.yml`):
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.fb.rule=Host(`fb.${DOMAIN}`)
  - traefik.http.routers.fb.entrypoints=web
  - traefik.http.routers.fb.middlewares=strip-user-headers@file,oidc-auth@file
  - traefik.http.services.fb.loadbalancer.server.port=80
```

---

### 3. Docker Compose 部署

部署文件位于 `http/` 目录：

| 文件 | 用途 |
|------|------|
| `docker-compose.yml` | 基础服务定义 (生产) |
| `compose.dev.yml` | 开发模式覆盖配置 |
| `.env` | 环境变量配置 |

**网络架构**:

| 网络 | 类型 | 连接服务 | 用途 |
|------|------|----------|------|
| `${PROJECT}_internal` | 内部 | mongodb, redis, backend, frontend | 服务间通信 |
| `gateway` | 外部 | frontend | Traefik 路由入口 |

**服务拓扑**:

```
┌─────────────────────────────────────────────────────────────┐
│                    gateway (外部网络)                   │
│                           ↓                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              internal (内部网络)                     │   │
│  │                                                      │   │
│  │   ┌──────────┐    ┌──────────┐    ┌──────────┐     │   │
│  │   │ frontend │ → │ backend  │ → │ mongodb  │     │   │
│  │   │  :80     │    │  :8000   │    │  :27017  │     │   │
│  │   └──────────┘    └──────────┘    └──────────┘     │   │
│  │                        ↓                            │   │
│  │                   ┌──────────┐                      │   │
│  │                   │  redis   │                      │   │
│  │                   │  :6379   │                      │   │
│  │                   └──────────┘                      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 环境配置

### 环境变量 (.env)

```env
COMPOSE_PROJECT_NAME=ad-regulation-http
DOMAIN=moondeity.dpdns.org
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=******
MONGODB_DB_NAME=fb
```

### 代理配置

后端服务支持 HTTP 代理访问 Facebook API：

```env
HTTP_PROXY=http://host.docker.internal:7890
HTTPS_PROXY=http://host.docker.internal:7890
NO_PROXY=mongodb,redis,localhost
```

---

## 运维命令

### 启动服务

```bash
cd http/

# 生产模式
./start.sh

# 开发模式 (含热重载)
./dev.sh
```

### 停止服务

```bash
# 停止所有
./stop.sh

# 仅停止开发容器
./dev-stop.sh
```

### 日志查看

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

---

## 开发模式特性

| 特性 | 说明 |
|------|------|
| 热重载 | 代码挂载到容器，修改自动生效 |
| 无认证 | `fb-dev.${DOMAIN}` 绕过 OIDC |
| 独立容器 | `backend-dev` / `frontend-dev` 与生产隔离 |
| API 文档 | 直接访问 `/docs` (Swagger UI) |

---

## 注意事项

1. **Rust 层错误隔离**: 若代码修改触发语法错误，Granian 不会直接崩溃，而是保留旧进程提供服务
2. **Leader Election**: 多实例部署时，调度器通过 Redis 自动选举 Leader，避免重复调度
3. **网络别名**: 多实例部署需确保 `COMPOSE_PROJECT_NAME` 唯一，避免网络别名冲突

---

## 相关文档

- [http/README.md](../../http/README.md) - 部署目录详细说明
- [http/dev.md](../../http/dev.md) - 开发模式详细说明
