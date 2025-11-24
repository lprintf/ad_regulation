from functools import partial

from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.insightsresult import InsightsResult
from pandas import DataFrame

from utils.fb_api_flyweight_factory import get_ad_object

ATOMIC_FIELDS = [
    "spend",
    "impressions",
    "reach",
    "clicks",
    # "unique_clicks",
    "inline_link_clicks",
    # "unique_inline_link_clicks",
    "outbound_clicks",
    # "unique_outbound_clicks",
    "actions",  # 列表
    "action_values",  # 列表
    # "conversions",
]


def get_atomic_metric(data: InsightsResult) -> dict:
    """
    输入一个包含原子属性字段 (ATOMIC_FIELDS) 的 AdsInsights，返回包含原子属性的结果。
    data 要通过 ATOMIC_FIELDS中的字段。
    注意：
    返回结果可能是字符串，以生成器表达式结合df进行转换。
    """
    # 原子属性
    impressions = data.get("impressions", 0)
    reach = data.get("reach", 0)
    clicks = data.get("clicks", 0)
    inline_link_clicks = data.get("inline_link_clicks", 0)
    spend = data.get("spend", 0.0)

    outbound_clicks = 0
    for item in data.get("outbound_clicks", []):
        if item["action_type"] == "outbound_click":
            outbound_clicks += int(item.get("value", 0))

    onsite_web_add_to_cart = 0
    onsite_web_checkout = 0
    onsite_web_purchase = 0
    landing_page_view = 0
    for item in data.get("actions", []):
        if item.get("action_type") == "onsite_web_initiate_checkout":
            onsite_web_checkout = int(item.get("value", 0))
        elif item.get("action_type") == "onsite_web_add_to_cart":
            onsite_web_add_to_cart = int(item.get("value", 0))
        elif item.get("action_type") == "onsite_web_purchase":
            onsite_web_purchase = int(item.get("value", 0))
        elif item.get("action_type") == "landing_page_view":
            landing_page_view = int(item.get("value", 0))

    onsite_web_add_to_cart_value = 0
    onsite_web_checkout_value = 0
    onsite_web_purchase_value = 0
    for item in data.get("action_values", []):
        if item.get("action_type") == "onsite_web_initiate_checkout":
            onsite_web_checkout_value = float(item.get("value", 0))
        elif item.get("action_type") == "onsite_web_purchase":
            onsite_web_purchase_value = float(item.get("value", 0.0))
        elif item.get("action_type") == "onsite_web_add_to_cart":
            onsite_web_add_to_cart_value = float(item.get("value", 0.0))

    return {
        "spend": spend,
        "impressions": impressions,
        "reach": reach,
        "clicks": clicks,
        "inline_link_clicks": inline_link_clicks,
        "outbound_clicks": outbound_clicks,
        "landing_page_view": landing_page_view,
        "onsite_web_checkout": onsite_web_checkout,
        "onsite_web_add_to_cart": onsite_web_add_to_cart,
        "onsite_web_purchase": onsite_web_purchase,
        "onsite_web_checkout_value": onsite_web_checkout_value,
        "onsite_web_add_to_cart_value": onsite_web_add_to_cart_value,
        "onsite_web_purchase_value": onsite_web_purchase_value,
    }


# 字段类型定义：按返回字典的键一一对应
atomic_dtype_spec = {
    "spend": "float32",  # 金额类：float32精度足够
    "impressions": "int32",  # 计数类：非负整数，int32范围足够
    "reach": "int32",
    "clicks": "int32",
    "inline_link_clicks": "int32",
    "landing_page_view": "int32",
    "outbound_clicks": "int32",  # 循环累加的整数结果
    "onsite_web_purchase": "int32",  # 购买次数：整数
    "onsite_web_add_to_cart": "int32",  # 加购次数：整数
    "onsite_web_purchase_value": "float32",  # 购买金额：float32
    "onsite_web_add_to_cart_value": "float32",  # 加购金额：float32
    "onsite_web_checkout": "int32",  # 结账次数：整数
    "onsite_web_checkout_value": "float32",  # 结账金额：float32
}


def ensure_atomic_insight_df_type(df: DataFrame):
    """确保数据帧的列类型为 atomic_dtype_spec 中定义的（仅对存在的列进行转换）"""
    if df.empty:
        return df
    # Only cast columns that exist in both df and dtype_spec
    existing_columns = {col: dtype for col, dtype in atomic_dtype_spec.items() if col in df.columns}
    return df.astype(existing_columns) if existing_columns else df


def get_insight(
    adobject: AdAccount,
    fields,
    level,
    since,
    until,
    breakdowns="",
    sort="spend_descending",
    time_increment=None,
    limit=1000,
    is_async=False,
):

    params = {
        "level": level,
        "time_range": {"since": since, "until": until},
        "limit": limit,
    }
    if breakdowns:
        params["breakdowns"] = breakdowns.split(",")
    if sort:
        params["sort"] = sort.split(",")
    if time_increment:
        params["time_increment"] = time_increment
    return adobject.get_insights(
        fields=fields,
        params=params,
        is_async=is_async,
    )


# 获得小时级广告数据（广告主时间）
get_advertiser_hourly_insight = partial(
    get_insight, breakdowns="hourly_stats_aggregated_by_advertiser_time_zone"
)

# 获得小时级广告数据（受众时间）
get_audience_hourly_insight = partial(
    get_insight, breakdowns="hourly_stats_aggregated_by_audience_time_zone"
)

# 获得天级广告数据
get_daily_insight = partial(get_insight, time_increment=1)

# 获得国家定向广告数据
get_country_insight = partial(get_insight, breakdowns="country")

# 获得广告内容定向广告数据
get_body_set_insight = partial(get_insight, breakdowns="body_set")

if __name__ == "__main__":

    import asyncio

    from config import (
        MONGO_INITDB_ROOT_PASSWORD,
        MONGO_INITDB_ROOT_USERNAME,
        MONGODB_DB_NAME,
        MONGODB_PORT,
    )
    from utils.db import close_db, init_db

    async def main():
        mongo_url = f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{"localhost"}:{MONGODB_PORT}/{MONGODB_DB_NAME}?authSource=admin"
        print(mongo_url)
        await init_db(mongo_url)

        account_id = "act_1243925423619499"
        fbid = "act_1243925423619499"

        adobject = await get_ad_object(account_id, fbid)

        advertiser_hourly_insight = get_advertiser_hourly_insight(
            adobject=adobject,
            level="ad",
            fields=[
                "ad_id",
                "account_id",
                *ATOMIC_FIELDS,
            ],
            since="2025-07-01",
            until="2025-08-22",
        )
        df = DataFrame(
            [
                {
                    "ad_id": _["ad_id"],
                    "account_id": _["account_id"],
                    **get_atomic_metric(_),
                }
                for _ in advertiser_hourly_insight
            ]
        )
        print(df)
        await close_db()

    asyncio.run(main())
