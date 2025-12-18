# Ad Regulation HTTP 开发模式指南

## 开发模式架构

HTTP 模式使用**独立容器策略**，开发容器与生产容器完全隔离:

```
生产环境:
  mongodb → backend → frontend → Traefik (fb.${DOMAIN})

开发环境:
  mongodb → backend-dev → frontend-dev → Traefik (fb-dev.${DOMAIN})
         ↑ (暴露27017)
```

## 启动开发环境

```bash
cd /home/lprintf/workspace/ad_regulation/tunnel
./dev.sh
```

这将启动:
- `mongodb`: 共享的 MongoDB 实例
- `backend-dev`: 开发后端容器（热重载）
- `frontend-dev`: 开发前端容器

## 访问地址

- **开发环境（无认证）**: `http://fb-dev.${DOMAIN}`
  - 直接访问，无需 OIDC 认证
  - 适合快速测试和开发

- **生产环境（带认证）**: `http://fb.${DOMAIN}`
  - 需要 OIDC 认证
  - 测试完整的认证流程

## 代码修改和热重载

### 后端代码

后端代码目录挂载到 `backend-dev` 容器:

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
docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend-dev
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

访问 `http://fb-dev.${DOMAIN}` 测试更改

### 4. 查看日志

```bash
# 后端日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f backend-dev

# 前端日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f frontend-dev

# 所有日志
docker compose -f docker-compose.yml -f compose.dev.yml logs -f
```

### 5. 停止开发容器

```bash
# 仅停止开发容器，保留 mongodb
./dev-stop.sh

# 完全停止所有容器
./stop.sh
```

## 数据库访问

开发模式下，MongoDB 端口暴露到宿主机:

```bash
# 使用 mongosh 连接（用户名/密码从 .env 文件读取）
mongosh mongodb://${MONGO_INITDB_ROOT_USERNAME}:${MONGO_INITDB_ROOT_PASSWORD}@localhost:27017

# 或使用默认值
mongosh mongodb://admin:admin123@localhost:27017

# 或使用 MongoDB Compass
# URI: mongodb://admin:admin123@localhost:27017
```

## 调试技巧

### 1. 进入容器调试

```bash
# 进入后端容器
docker compose -f docker-compose.yml -f compose.dev.yml exec backend-dev bash

# 进入 MongoDB 容器
docker compose exec mongodb bash
```

### 2. 手动重启服务

```bash
# 重启后端
docker compose -f docker-compose.yml -f compose.dev.yml restart backend-dev

# 重启前端
docker compose -f docker-compose.yml -f compose.dev.yml restart frontend-dev
```

### 3. 查看容器状态

```bash
docker compose -f docker-compose.yml -f compose.dev.yml ps
```

### 4. 清理并重新构建

```bash
# 停止所有容器
./stop.sh

# 清理容器和镜像
docker compose down --rmi local

# 重新构建并启动
docker compose -f docker-compose.yml -f compose.dev.yml up -d --build
```

## 环境变量

开发模式使用相同的 `.env` 文件，但某些配置可以覆盖:

```env
# .env
COMPOSE_PROJECT_NAME=ad-regulation-http
DOMAIN=moondeity.dpdns.org
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin123
```

## 网络配置

开发容器使用相同的网络架构:

- `backend-dev`, `frontend-dev` 在内部网络通信
- `frontend-dev` 使用别名 `ad-regulation-http-frontend-dev` 暴露到 gateway
- 不与其他项目的开发环境冲突

## 性能优化

### 快速重启开发容器

使用 `dev-stop.sh` 而不是 `stop.sh`:

```bash
# 快速：仅停止开发容器，保留 mongodb
./dev-stop.sh

# 下次启动更快
./dev.sh
```

### 减少构建时间

使用 Docker 构建缓存:

```bash
# 仅重新构建更改的服务
docker compose -f docker-compose.yml -f compose.dev.yml up -d --build backend-dev
```

## 常见问题

### Q: 修改代码后没有生效？

A:
- 后端代码应该自动重载，检查 `docker compose logs -f backend-dev` 确认重启
- 前端代码需要手动构建: `cd ../frontend && npm run build`

### Q: 端口 27017 已被占用？

A: 检查是否有其他 MongoDB 实例运行:
```bash
lsof -i :27017
docker ps | grep mongo
```

### Q: 无法访问 fb-dev.${DOMAIN}？

A: 检查:
1. Traefik 是否运行: `docker ps | grep traefik`
2. frontend-dev 标签配置是否正确
3. DNS 是否正确解析域名

### Q: 数据库连接失败？

A: 确认:
1. mongodb 容器运行: `docker compose ps mongodb`
2. 环境变量配置正确: `cat .env`
3. backend-dev 可以访问 mongodb: `docker compose exec backend-dev ping mongodb`

## 切换到生产模式

```bash
# 停止开发环境
./dev-stop.sh

# 启动生产环境
./start.sh
```

## 相关文档

- 生产部署: [README.md](README.md)
- HTTPS 部署: [../https/README.md](../https/README.md)
