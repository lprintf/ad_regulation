from typing import List, Literal, Optional

from pydantic import BaseModel


class FbAppTokenInfo(BaseModel):
    app_id: str
    type: Optional[Literal["SYSTEM_USER", "USER"]] = None
    application: Optional[str] = None
    data_access_expires_at: Optional[int] = None
    expires_at: Optional[int] = None
    is_valid: Optional[bool] = None
    issued_at: Optional[int] = None
    scopes: Optional[List] = None
    granular_scopes: Optional[List] = None
    user_id: Optional[str] = None


class FbAppSeedInfo(BaseModel):

    app_id: str
    app_secret: str
    access_token: str


class FbAppAuth(FbAppSeedInfo):
    user_id: str
    type: Optional[Literal["SYSTEM_USER", "USER"]] = "SYSTEM_USER"


class ADAccount(BaseModel):
    id: str  # 以act_开头的ID
    name: str
