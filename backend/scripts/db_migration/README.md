# MongoDB Migration Helpers

本目录收纳了所有 MongoDB 迁移相关脚本，均基于 `config.py` 中的连接配置（`MONGODB_URL`/`MONGODB_DB_NAME`）。常用脚本：

- `mongo_copy_collections.py`：在线跨库复制，适合源/目标 Mongo 可互通的情况；可选 `--drop-target` 在写入前清空目标集合。
- `mongo_export_dump.py`：离线导出，把所有业务集合写入 `output/mongo_dump/*.jsonl`（含索引信息 `indexes.json`）；把该目录拷贝到新服务器即可。
- `mongo_import_dump.py`：配合导出结果在目标服务器导入，并按 `indexes.json` 重建索引。
- `mongo_collections.py`：定义迁移中会涉及到的集合清单（默认迁移所有业务数据 + `scheduler_state` + 全量 `insights_sync_log`，不迁移 `rule_execution_log`）。
- `__init__.py`：标记本目录为脚本包，便于引用。

### 在线迁移示例
```bash
uv run python scripts/db_migration/mongo_copy_collections.py \
  --source-uri "$OLD_MONGODB_URL" --source-db "$MONGODB_DB_NAME" \
  --target-uri "mongodb://user:pwd@new-host:27017/fb_monitor?authSource=admin" \
  --target-db "$MONGODB_DB_NAME" --drop-target
```

## 离线迁移流程

### 方式一：宿主机直接运行（推荐开发环境）

1. **导出数据**（在旧服务器）：
```bash
cd /path/to/ad_regulation/backend
PYTHONPATH=. uv run --env-file=../.env python scripts/db_migration/mongo_export_dump.py
```
导出文件位置：`backend/output/mongo_dump/`

2. **拷贝数据**：
```bash
# 将 backend/output/mongo_dump/ 整个目录拷贝到新服务器相同路径
scp -r backend/output/mongo_dump/ user@new-server:/path/to/ad_regulation/backend/output/
```

3. **导入数据**（在新服务器）：
```bash
cd /path/to/ad_regulation/backend
PYTHONPATH=. uv run --env-file=../.env python scripts/db_migration/mongo_import_dump.py
```

### 方式二：容器内运行（推荐生产环境）

**前提条件**：MongoDB容器没有映射端口到宿主机时使用此方式。

1. **准备数据文件**（确保 `backend/output/mongo_dump/` 目录存在导出的数据）

2. **复制数据和脚本到容器**：
```bash
# 进入 docker-compose.yml 所在目录
cd /path/to/ad_regulation/http  # 或 https 目录

# 复制数据文件到容器
docker cp ../backend/output/mongo_dump/. <backend-container-name>:/app/output/mongo_dump/

# 复制scripts目录到容器（如果容器中没有）
docker cp ../backend/scripts <backend-container-name>:/app/
```

3. **在容器内执行导入**：
```bash
# 方式A: 使用backend-dev容器（开发环境）
docker exec <backend-container-name> sh -c "cd /app && PYTHONPATH=. python scripts/db_migration/mongo_import_dump.py"

# 方式B: 使用backend容器（生产环境）
docker exec <backend-container-name> sh -c "cd /app && PYTHONPATH=. python scripts/db_migration/mongo_import_dump.py"
```

**容器名称示例**：
- HTTP开发环境：`fb-http-backend-dev-1`
- HTTP生产环境：`fb-http-backend-1`
- HTTPS开发环境：`fb-https-backend-dev-1`
- HTTPS生产环境：`fb-https-backend-1`

**导入成功标志**：
```
Importing collection 'ADAccountDocument'...
  -> Restored 28 documents.
Importing collection 'insights_daily'...
  -> Restored 65088 documents.
...
Mongo import completed.
```

## 注意事项

- 导入操作会自动 drop 目标集合后再导入，请确保数据已备份
- 如需调整参与迁移的集合或日志策略，可修改 `mongo_collections.py` 中的集合列表
- 容器方式需要手动复制 `scripts` 目录，因为默认compose配置未挂载此目录
