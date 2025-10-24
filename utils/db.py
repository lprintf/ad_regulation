from datetime import datetime
from typing import List, Literal, Optional

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

    class Settings:
        indexes = [
            IndexModel(["app_id", "user_id"], unique=True),
        ]


class FbAppAuthDocument(FbAppAuth, Document):
    """
    FB App 授权信息
    包括：app_id, app_secret, access_token, user_id, token_type
    """

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
