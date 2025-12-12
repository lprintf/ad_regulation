#!/usr/bin/env python3
"""
迁移脚本：修复 AdEntityNamesDocument 的唯一索引

问题：原索引 (entity_type, entity_id) 不包含 account_id，
     导致不同账号的相同 entity_id 会互相覆盖

修复：将唯一索引改为 (account_id, entity_type, entity_id)

使用方法：
    python backend/scripts/migrate_entity_names_index.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from backend.config import MONGODB_URI, MONGODB_DB_NAME


async def migrate_index():
    """重建 ad_entity_names 集合的唯一索引"""

    print("🔧 开始迁移 ad_entity_names 索引...")

    # 连接数据库
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]
    collection = db["ad_entity_names"]

    print(f"📊 当前集合文档数: {await collection.count_documents({})}")

    # Step 1: 列出当前所有索引
    print("\n📋 当前索引列表:")
    indexes = await collection.list_indexes().to_list(None)
    for idx in indexes:
        print(f"  - {idx['name']}: {idx.get('key', {})}")

    # Step 2: 删除旧的唯一索引
    old_index_name = "entity_type_1_entity_id_1"
    try:
        print(f"\n🗑️  删除旧索引: {old_index_name}")
        await collection.drop_index(old_index_name)
        print("  ✅ 删除成功")
    except OperationFailure as e:
        if "index not found" in str(e):
            print("  ℹ️  旧索引不存在，跳过删除")
        else:
            raise

    # Step 3: 创建新的唯一索引（包含 account_id）
    new_index_keys = [
        ("account_id", 1),
        ("entity_type", 1),
        ("entity_id", 1)
    ]

    print(f"\n🔨 创建新索引: {new_index_keys}")
    try:
        new_index_name = await collection.create_index(
            new_index_keys,
            unique=True,
            background=True  # 后台创建，不阻塞其他操作
        )
        print(f"  ✅ 新索引创建成功: {new_index_name}")
    except OperationFailure as e:
        if "duplicate key" in str(e):
            print("  ⚠️  检测到重复数据！")
            print("  💡 建议：先清理重复记录，然后重新运行此脚本")

            # 查找重复记录
            print("\n🔍 查找重复记录...")
            pipeline = [
                {
                    "$group": {
                        "_id": {
                            "account_id": "$account_id",
                            "entity_type": "$entity_type",
                            "entity_id": "$entity_id"
                        },
                        "count": {"$sum": 1},
                        "docs": {"$push": "$$ROOT"}
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
                {"$limit": 10}
            ]

            duplicates = await collection.aggregate(pipeline).to_list(None)
            if duplicates:
                print(f"  发现 {len(duplicates)} 组重复记录（显示前10组）:")
                for dup in duplicates:
                    print(f"    - {dup['_id']}: {dup['count']} 条记录")

                print("\n🛠️  自动清理重复记录（保留最新的）...")
                cleaned_count = 0
                for dup in duplicates:
                    # 按 updated_at 排序，保留最新的
                    docs = sorted(dup['docs'], key=lambda d: d.get('updated_at', d.get('fetched_at')), reverse=True)
                    to_delete = docs[1:]  # 删除旧的记录

                    for doc in to_delete:
                        await collection.delete_one({"_id": doc["_id"]})
                        cleaned_count += 1

                print(f"  ✅ 已清理 {cleaned_count} 条重复记录")

                # 重新尝试创建索引
                print(f"\n🔨 重新创建新索引...")
                new_index_name = await collection.create_index(
                    new_index_keys,
                    unique=True,
                    background=True
                )
                print(f"  ✅ 新索引创建成功: {new_index_name}")
            else:
                print("  未找到重复记录")
        else:
            raise

    # Step 4: 验证最终索引
    print("\n✅ 迁移完成！最终索引列表:")
    indexes = await collection.list_indexes().to_list(None)
    for idx in indexes:
        key_info = idx.get('key', {})
        unique = " (UNIQUE)" if idx.get('unique') else ""
        print(f"  - {idx['name']}: {key_info}{unique}")

    client.close()
    print("\n🎉 索引迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate_index())
