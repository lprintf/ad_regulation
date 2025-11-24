# Ad Regulation HTTPS 开发模式指南

## 开发模式架构

HTTPS 模式使用**覆盖（overlay）策略**，通过 compose.dev.yml 覆盖生产配置:

```
生产环境:
  mongodb → backend → frontend → Traefik (fb.${DOMAIN}, HTTPS + OIDC)

开发环境:
  mongodb → backend (热重载) → frontend → Traefik
         ↑ (暴露27017)      ↑ (直连路由: fb-dev.${DOMAIN})
```

## 启动开发环境

```bash
cd /home/lprintf/workspace/ad_regulation/https
./dev.sh
```

这将:
1. 停止现有容器
2. 使用 `docker-compose.yml` + `compose.dev.yml` 启动
3. 覆盖生产配置，启用开发特性

## 访问地址

- **生产环境（带认证）**: `https://fb.${DOMAIN}`
  - 通过 frontend (nginx) 访问
  - 需要 OIDC 认证
  - 测试完整的认证流程

- **开发环境（直连后端）**: `https://fb-dev.${DOMAIN}`
  - 直接访问 backend (uvicorn)
  - 无需认证
  - 适合 API 开发和测试

## 覆盖策略详解

### 生产配置 (docker-compose.yml)

```yaml
backend:
  build: ...
  environment:
    MONGODB_HOST: mongodb
  # 默认命令，无热重载
```

### 开发覆盖 (compose.dev.yml)

```yaml
backend:
  command: uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload --loop uvloop
  volumes:
    - ../backend/api:/app/api:ro
    - ../backend/utils:/app/utils:ro
  labels:
    # 添加直连后端路由
    - traefik.http.routers.fb-backend-dev.rule=Host(`fb-dev.${DOMAIN}`)
  networks:
    default:
    gateway-https:
      aliases:
        - ${COMPOSE_PROJECT_NAME}-backend-dev
```

最终效果 = 生产配置 + 开发覆盖

## 代码修改和热重载

### 后端代码

后端代码目录挂载到容器:

```yaml
volumes:
  - ../backend/api:/app/api:ro
  - ../backend/utils:/app/utils:ro
  - ../backend/baseline:/app/baseline:ro
  - ../backend/config.py:/app/config.py:ro
```

修改代码后，uvicorn 会自动重启:

```bash
# 查看后端日志，确认重启
docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend
```

### 前端代码

前端需要手动构建后才能看到更改:

```bash
# 进入前端目录
cd /home/lprintf/workspace/ad_regulation/frontend

# 构建
npm run build
# 或使用 watch 模式
npm run build -- --watch
```

挂载的目录:

```yaml
volumes:
  - ../frontend/dist:/usr/share/nginx/html:ro
  - ../frontend/nginx.dev.conf.template:/etc/nginx/templates/default.conf.template:ro
```

## 开发工作流

### 1. 启动开发环境

```bash
./dev.sh
```

### 2. 修改代码

```bash
# 后端代码 - 自动重载
vim ../backend/api/routes.py

# 前端代码 - 需要重新构建
vim ../frontend/src/App.vue
cd ../frontend && npm run build
```

### 3. 测试

- 测试 API: 访问 `https://fb-dev.${DOMAIN}`
- 测试完整流程: 访问 `https://fb.${DOMAIN}`

### 4. 查看日志

```bash
# 后端日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend

# 前端日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f frontend

# 所有日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f
```

### 5. 退出开发模式

```bash
# 自动停止开发模式并恢复生产模式
./dev-stop.sh

# 或完全停止所有容器
./stop.sh
```

## 数据库访问

开发模式下，MongoDB 端口暴露到宿主机:

```bash
# 使用 mongosh 连接
mongosh mongodb://admin:admin123@localhost:27017

# 或使用 MongoDB Compass
# URI: mongodb://admin:admin123@localhost:27017
```

## 调试技巧

### 1. 测试 API 端点

使用 curl 测试后端:

```bash
# 直连后端（开发域名）
curl https://fb-dev.${DOMAIN}/api/health

# 通过前端（生产域名，需要认证）
curl https://fb.${DOMAIN}/api/health
```

### 2. 进入容器调试

```bash
# 进入后端容器
docker compose exec backend bash

# 进入 MongoDB 容器
docker compose exec mongodb bash
```

### 3. 手动重启服务

```bash
# 重启后端
docker compose -f docker-compose.yml -f compose.dev.yml restart backend

# 重启前端
docker compose -f docker-compose.yml -f compose.dev.yml restart frontend
```

### 4. 查看容器状态

```bash
docker compose -f docker-compose.yml -f compose.dev.yml ps
```

### 5. 清理并重新构建

```bash
# 停止所有容器
./stop.sh

# 清理容器和镜像
docker compose down --rmi local

# 重新构建并启动开发模式
docker compose -f docker-compose.yml -f compose.dev.yml up -d --build
```

## 环境变量

开发模式使用相同的 `.env` 文件:

```env
# .env
COMPOSE_PROJECT_NAME=ad-regulation-https
DOMAIN=moondeity.dpdns.org
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123
```

## 网络配置

开发模式下的网络变化:

生产模式:
- backend: 仅内部网络
- frontend: 内部网络 + gateway-https

开发模式:
- backend: 内部网络 + gateway-https（用于直连）
- frontend: 保持不变

## 覆盖策略 vs 独立容器策略

### 覆盖策略（HTTPS 模式）

优点:
- 节省资源：使用相同容器
- 快速切换：同一组容器，不同配置
- 数据一致：共享相同的数据卷

缺点:
- 无法同时运行生产和开发
- 切换需要重启容器

### 独立容器策略（HTTP 模式）

优点:
- 完全隔离：生产和开发互不影响
- 同时运行：可以对比测试
- 灵活性高：独立的配置和数据

缺点:
- 占用资源更多
- 需要管理更多容器

## 常见问题

### Q: 修改代码后没有生效？

A:
- 后端代码应该自动重载，检查 `docker compose logs -f backend` 确认重启
- 前端代码需要手动构建: `cd ../frontend && npm run build`

### Q: 无法访问 fb-dev.${DOMAIN}？

A: 检查:
1. 开发模式是否启动: `./dev.sh`
2. backend 标签配置是否正确: `docker compose config`
3. Traefik 是否运行: `docker ps | grep traefik`
4. DNS 是否正确解析域名

### Q: TLS 证书错误？

A: Traefik 使用 Let's Encrypt 自动获取证书:
1. 确认域名 DNS 正确解析
2. 检查 Traefik 日志: `docker logs traefik`
3. 等待证书获取完成（首次可能需要几分钟）

### Q: OIDC 认证失败？

A:
- `fb-dev.${DOMAIN}` 不应该有 OIDC 认证
- `fb.${DOMAIN}` 需要 OIDC，检查 Traefik 中间件配置

### Q: 如何完全禁用 OIDC？

A: 修改 docker-compose.yml，移除 `oidc-auth@file` 中间件:
```yaml
labels:
  - traefik.http.routers.fb.middlewares=strip-user-headers@file
```

## 切换到生产模式

```bash
# 方法 1: 使用 dev-stop.sh（推荐）
./dev-stop.sh

# 方法 2: 手动切换
docker compose -f docker-compose.yml -f compose.dev.yml down
docker compose up -d
```

## 性能优化

### 减少构建时间

使用 Docker 构建缓存:

```bash
# 仅重新构建更改的服务
docker compose -f docker-compose.yml -f compose.dev.yml up -d --build backend
```

### 减少重启时间

使用 `restart` 而不是 `down` + `up`:

```bash
# 快速重启
docker compose -f docker-compose.yml -f compose.dev.yml restart backend
```

## 相关文档

- 生产部署: [README.md](README.md)
- HTTP 部署: [../http/README.md](../http/README.md)
- HTTP 开发模式: [../http/dev.md](../http/dev.md)
