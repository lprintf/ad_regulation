from typing import Dict

from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.api import FacebookAdsApi

from utils.db import ADAccountDocument, FbAppAuthDocument


class FacebookAdsApiFlyweightFactory:
    """
    FacebookAdsApi的工厂类，用于读取数据库已插入数据，创建FacebookAdsApi实例，并缓存实例，
    避免重复创建实例，提高性能。
    """

    def __init__(self):
        self._cache: Dict[str, FacebookAdsApi] = {}

    async def get(self, ad_account_id: str) -> FacebookAdsApi:
        if ad_account_id not in self._cache:
            self._cache[ad_account_id] = await self.create(ad_account_id)
        return self._cache[ad_account_id]

    async def create(self, ad_account_id: str) -> FacebookAdsApi:
        ad_account = await ADAccountDocument.find_one(
            ADAccountDocument.id == ad_account_id, fetch_links=True
        )
        fb_app_auth: FbAppAuthDocument = ad_account.fb_app_auth
        return FacebookAdsApi.init(
            fb_app_auth.app_id, fb_app_auth.app_secret, fb_app_auth.access_token
        )

    def pop(self, ad_account_id: str) -> FacebookAdsApi | None:
        self._cache.pop(ad_account_id, None)


fb_ads_api_flyweight_factory = FacebookAdsApiFlyweightFactory()


async def get_ad_object(ad_account_id: str, fbid) -> AdAccount:

    api = await fb_ads_api_flyweight_factory.get(ad_account_id)
    adobject = AdAccount(
        fbid, api=api
    )  # 创建广告账户对象,AdAccount类会被处理为fbid的真实类别
    return adobject
