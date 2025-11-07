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


class RuleBindingDocument(Document):
    rule: Link[RuleDefinitionDocument]
    rule_id: str
    rule_name: str
    entity_type: Literal["ad", "adset", "campaign", "account"]
    entity_id: str
    source: Literal["manual", "auto", "naming_parser"] = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)
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
    obs_since: datetime | None = None
    obs_until: datetime | None = None
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
            IndexModel([("entity_type", 1), ("entity_id", 1)], unique=True),
            IndexModel("account_id"),
            IndexModel([("account_id", 1), ("entity_type", 1)]),
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
            RuleBindingDocument,
            RuleExecutionLogDocument,
            InsightsDailyDocument,
            InsightsSyncLogDocument,
            InsightsSyncStateDocument,
            AdEntityNamesDocument,
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
