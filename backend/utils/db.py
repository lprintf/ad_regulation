from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Type

from beanie import Document, Link, init_beanie
from pydantic import Field
from pymongo import AsyncMongoClient, IndexModel
from pymongo.asynchronous.collection import AsyncCollection

from config import MONGODB_DB_NAME, MONGODB_URL
from utils.schemas.ad_account import ADAccount, FbAppAuth, FbAppTokenInfo

# Global MongoDB client and database instances
mongo_client: Optional[AsyncMongoClient] = None
mongo_database = None


class FbAppTokenInfoDocument(FbAppTokenInfo, Document):
    """
    fb token 原始token信息，同graph_api返回的token信息，不包含授权信息
    """

    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        indexes = [
            IndexModel(["app_id", "user_id"], unique=True),
        ]


class FbAppAuthDocument(FbAppAuth, Document):
    """
    FB App 授权信息
    包括：app_id, app_secret, access_token, user_id, token_type
    """

    last_synced_at: datetime = Field(default_factory=datetime.utcnow)
    last_synced_by: Optional[str] = None
    user_name: Optional[str] = None

    class Settings:
        indexes = [
            IndexModel(["app_id", "user_id"], unique=True),
        ]


class ADAccountDocument(ADAccount, Document):
    fb_app_auth: Optional[Link[FbAppAuthDocument]] = None


class BIUserAdAccountLink(Document):
    user_id: str
    account_id: str
    role: Literal["owner", "viewer", "editor"] = "viewer"
    joined_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        indexes = [
            IndexModel([("user_id", 1), ("account_id", 1)], unique=True),
            IndexModel("user_id"),
            IndexModel("account_id"),
        ]


class RuleDefinitionDocument(Document):
    name: str
    description: str | None = None
    version: str = Field(default="1.0.0")
    code: str = Field(..., description="Executable rule script")
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    status: Literal["draft", "published", "disabled"] = "draft"
    is_active: bool = False
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: datetime | None = None

    class Settings:
        name = "rule_definitions"
        indexes = [
            IndexModel("name", unique=True),
            IndexModel([("name", 1), ("status", 1)]),
            IndexModel("tags"),
        ]


class RuleConfigDocument(Document):
    """
    统一规则模型 - 存储基础规则元数据和用户自定义配置
    
    基础规则（来自代码注册表）：
    - template_id = None, source = "system"
    - 由系统在启动时同步到数据库
    
    自定义配置（用户复制）：
    - template_id = 被复制对象的 ID
    - source = "user:{user_id}"
    - version 在模板版本基础上修复号+1
    """
    name: str  # 规则名称，如 "ml_auto_stop" 或 "ml_auto_stop_conservative"
    base_rule: str  # 基础规则名（代码注册表中的规则名）
    description: str | None = None
    version: str = Field(default="1.0.0")  # 语义版本号
    
    # 来源追踪
    template_id: str | None = None  # 模板ID，None表示基础规则
    source: str = "system"  # 来源：system 或 user:{user_id}
    
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)  # 参数覆盖
    tags: list[str] = Field(default_factory=list)
    
    # 状态管理
    is_active: bool = True
    is_archived: bool = False  # 归档状态（替代删除）
    
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rule_configs"
        indexes = [
            IndexModel("name", unique=True),
            IndexModel("base_rule"),
            IndexModel("template_id"),
            IndexModel("source"),
            IndexModel("tags"),
            IndexModel("is_archived"),
        ]


class RuleBindingDocument(Document):
    # rule link is optional for backward compatibility (rules are now code-based)
    rule: Optional[Link[RuleDefinitionDocument]] = None
    rule_id: str  # Now stores rule name for registry lookup
    rule_name: str
    rule_config_id: str | None = None  # Optional: link to RuleConfigDocument for parameter overrides

    # Entity binding info
    entity_type: Literal["ad", "adset", "campaign", "account"]
    entity_id: str

    # Ad hierarchy fields for indexing and querying
    ad_account_id: str
    campaign_id: str | None = None
    adset_id: str | None = None
    ad_id: str | None = None

    source: Literal["manual", "auto", "naming_parser"] = "manual"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_executed_at: datetime | None = None

    class Settings:
        name = "rule_bindings"
        indexes = [
            IndexModel([("rule_name", 1), ("entity_id", 1)], unique=True),
            IndexModel("rule_id"),
            IndexModel("entity_id"),
            IndexModel("rule_name"),
            IndexModel("rule_config_id"),
            IndexModel("ad_account_id"),
            IndexModel([("ad_account_id", 1), ("campaign_id", 1)]),
            IndexModel([("ad_account_id", 1), ("adset_id", 1)]),
            IndexModel([("ad_account_id", 1), ("ad_id", 1)]),
        ]


class RuleExecutionLogDocument(Document):
    rule_name: str
    rule_id: str | None = None
    rule_version: str | None = None
    binding: Link[RuleBindingDocument] | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    trigger: Literal["manual", "scheduler", "auto_unbind", "test"] = "manual"
    scheduled_run_time: datetime | None = None
    actual_start_time: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: Literal["success", "failed", "skipped"] = "success"
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    execution_duration_ms: int | None = None
    execution_logs: list[str] = Field(default_factory=list)

    class Settings:
        name = "rule_execution_logs"
        indexes = [
            IndexModel("rule_name"),
            IndexModel("actual_start_time"),
            IndexModel([("rule_name", 1), ("actual_start_time", -1)]),
        ]


class InsightsDailyDocument(Document):
    account_id: str
    campaign_id: str | None = None
    adset_id: str | None = None
    ad_id: str
    date_start: datetime

    spend: float = 0.0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    inline_link_clicks: int = 0
    outbound_clicks: int = 0
    landing_page_view: int = 0
    onsite_web_checkout: int = 0
    onsite_web_add_to_cart: int = 0
    onsite_web_purchase: int = 0
    onsite_web_checkout_value: float = 0.0
    onsite_web_add_to_cart_value: float = 0.0
    onsite_web_purchase_value: float = 0.0

    fetched_range_start: datetime | None = None
    fetched_range_end: datetime | None = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "insights_daily"
        indexes = [
            IndexModel([("ad_id", 1), ("date_start", 1)], unique=True),
            IndexModel([("account_id", 1), ("date_start", 1)]),
            IndexModel([("campaign_id", 1), ("date_start", 1)]),
            IndexModel([("adset_id", 1), ("date_start", 1)]),
            IndexModel([("account_id", 1), ("campaign_id", 1), ("date_start", 1)]),
            IndexModel([("account_id", 1), ("adset_id", 1), ("date_start", 1)]),
            IndexModel([("account_id", 1), ("ad_id", 1), ("date_start", 1)]),
        ]


class InsightsSyncLogDocument(Document):
    date: datetime
    status: Literal["pending", "running", "success", "failed"] = "pending"
    mode: Literal["auto", "manual"] = "auto"
    triggered_by: str | None = None
    attempts: int = 0
    last_error: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    synced_at: datetime | None = None

    class Settings:
        name = "insights_sync_log"
        indexes = [
            IndexModel("date", unique=True),
            IndexModel([("status", 1), ("date", -1)]),
        ]


class InsightsSyncStateDocument(Document):
    account_id: str
    last_synced_at: datetime | None = None
    last_synced_date: datetime | None = None
    initial_requested_since: datetime | None = None

    # MongoDB 数据覆盖范围（历史数据）
    obs_since: datetime | None = None
    obs_until: datetime | None = None

    # Redis 缓存覆盖范围（实时数据）
    redis_cache_since: datetime | None = None
    redis_cache_until: datetime | None = None
    redis_cache_updated_at: datetime | None = None

    last_status: Literal["idle", "running", "success", "failed"] = "idle"
    last_error: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "insights_sync_state"
        indexes = [
            IndexModel("account_id", unique=True),
        ]


class AdEntityNamesDocument(Document):
    """
    存储 Facebook 广告实体（Campaign, AdSet, Ad）的名称
    用于在洞察数据界面显示实体名称而非ID
    """
    account_id: str
    entity_type: Literal["campaign", "adset", "ad"]
    entity_id: str
    entity_name: str

    # 可选的状态信息
    configured_status: str | None = None
    effective_status: str | None = None

    # 元数据
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "ad_entity_names"
        indexes = [
            # 唯一索引必须包含 account_id，防止跨账号数据覆盖
            IndexModel(
                [("account_id", 1), ("entity_type", 1), ("entity_id", 1)],
                unique=True
            ),
            IndexModel("account_id"),
            IndexModel([("account_id", 1), ("entity_type", 1)]),
        ]


class SyncHistoryDocument(Document):
    """
    洞察同步历史记录
    每次同步任务（无论成功或失败）都会创建一条记录
    """
    # 基本信息
    account_id: str
    account_name: str | None = None

    # 触发信息
    trigger_type: Literal["manual", "auto", "retry"] = "manual"
    triggered_by: str | None = None

    # 同步范围
    since: datetime  # 同步开始日期
    until: datetime  # 同步结束日期

    # 执行模式
    mode: Literal["sync", "async"] = "sync"

    # 数据存储目标
    data_target: Literal["mongodb", "redis", "hybrid"] = "mongodb"

    # 状态信息
    status: Literal["pending", "running", "success", "failed"] = "pending"

    # 时间戳
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # 结果统计
    records_count: int = 0
    error_message: str | None = None
    duration_seconds: float | None = None

    # 进度信息（用于异步任务）
    percent_complete: int = 0
    current_date: str | None = None
    total_days: int = 0
    processed_days: int = 0

    # 额外元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Settings:
        name = "sync_history"
        indexes = [
            IndexModel("account_id"),
            IndexModel([("account_id", 1), ("started_at", -1)]),
            IndexModel([("status", 1), ("started_at", -1)]),
            IndexModel("started_at"),
            IndexModel([("trigger_type", 1), ("started_at", -1)]),
        ]


async def init_db(mongodb_url=MONGODB_URL):
    """Initialize MongoDB connection and Beanie ODM"""
    global mongo_client, mongo_database
    # Create MongoDB client using individual configuration parameters
    # 构建MongoDB连接字符串，包含认证源 (authSource=admin)
    mongo_client = AsyncMongoClient(mongodb_url)
    mongo_database = mongo_client[MONGODB_DB_NAME]

    # Initialize Beanie with document models
    await init_beanie(
        database=mongo_database,
        document_models=[
            ADAccountDocument,
            FbAppTokenInfoDocument,
            FbAppAuthDocument,
            BIUserAdAccountLink,
            RuleDefinitionDocument,
            RuleConfigDocument,
            RuleBindingDocument,
            RuleExecutionLogDocument,
            InsightsDailyDocument,
            InsightsSyncLogDocument,
            InsightsSyncStateDocument,
            AdEntityNamesDocument,
            SyncHistoryDocument,
        ],
    )


async def close_db():
    """Close MongoDB connection"""
    global mongo_client
    if mongo_client:
        await mongo_client.close()


async def get_all_ad_account_documents(fetch_links=True) -> List[ADAccountDocument]:
    ad_account_documents = ADAccountDocument.find(fetch_links=fetch_links)
    ad_account_documents_list = await ad_account_documents.to_list()
    return ad_account_documents_list


def _resolve_collection_name(document_cls: Type[Document]) -> str:
    settings = getattr(document_cls, "Settings", None)
    if settings and getattr(settings, "name", None):
        return settings.name  # type: ignore[attr-defined]
    return document_cls.__name__


def get_async_collection(name: str) -> AsyncCollection:
    if mongo_database is None:
        raise RuntimeError("MongoDB is not initialized; call init_db() first.")
    return mongo_database[name]


def get_document_collection(document_cls: Type[Document]) -> AsyncCollection:
    return get_async_collection(_resolve_collection_name(document_cls))


async def drop_insights_indexes() -> list[str]:
    """Drop all non-default indexes on the insights collection."""
    collection = get_document_collection(InsightsDailyDocument)
    info = await collection.index_information()
    dropped: list[str] = []
    for name in info:
        if name == "_id_":
            continue
        await collection.drop_index(name)
        dropped.append(name)
    return dropped


async def ensure_insights_indexes() -> int:
    """Ensure insights collection indexes exist."""
    collection = get_document_collection(InsightsDailyDocument)
    indexes = getattr(InsightsDailyDocument.Settings, "indexes", []) or []
    if not indexes:
        return 0
    await collection.create_indexes(indexes)
    return len(indexes)
