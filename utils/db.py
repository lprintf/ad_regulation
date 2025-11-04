from datetime import datetime
from typing import Any, List, Literal, Optional

from beanie import Document, Link, init_beanie
from pydantic import Field
from pymongo import AsyncMongoClient, IndexModel

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
