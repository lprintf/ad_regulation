# MongoDB Migration Helpers

本目录收纳了所有 MongoDB 迁移相关脚本，均基于 `config.py` 中的连接配置（`MONGODB_URL`/`MONGODB_DB_NAME`）。常用脚本：

- `mongo_copy_collections.py`：在线跨库复制，适合源/目标 Mongo 可互通的情况；可选 `--drop-target` 在写入前清空目标集合。
- `mongo_export_dump.py`：离线导出，把所有业务集合写入 `output/mongo_dump/*.jsonl`（含索引信息 `indexes.json`）；把该目录拷贝到新服务器即可。
- `mongo_import_dump.py`：配合导出结果在目标服务器导入，并按 `indexes.json` 重建索引。
- `mongo_collections.py`：定义迁移中会涉及到的集合清单（默认迁移所有业务数据 + `scheduler_state` + 全量 `insights_sync_log`，不迁移 `rule_execution_log`）。
- `__init__.py`：标记本目录为脚本包，便于引用。

### 在线迁移示例
```
uv run python scripts/db_migration/mongo_copy_collections.py \
  --source-uri "$OLD_MONGODB_URL" --source-db "$MONGODB_DB_NAME" \
  --target-uri "mongodb://user:pwd@new-host:27017/fb_monitor?authSource=admin" \
  --target-db "$MONGODB_DB_NAME" --drop-target
```

### 离线迁移流程
1. 在旧服务器运行 `uv run python scripts/db_migration/mongo_export_dump.py`，会把数据导出到 `output/mongo_dump`。
2. 将该目录整体拷贝到新服务器相同路径。
3. 在新服务器的项目目录中运行 `uv run python scripts/db_migration/mongo_import_dump.py`，即可恢复所有集合（导入时会自动 drop 目标集合）。

如需调整参与迁移的集合或日志策略，可修改 `mongo_collections.py` 中的集合列表。
