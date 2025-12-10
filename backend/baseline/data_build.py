import numpy as np
import pandas as pd


def load_df_data(file_path: str) -> pd.DataFrame:
    """加载feather文件
    Load data from a feather file into a Pandas DataFrame."""
    df = pd.read_feather(file_path)
    df.rename(columns={"date_start": "date"}, inplace=True)
    return df


def save_df_data(df: pd.DataFrame, file_path: str):
    """
    保存DataFrame为feather文件"""
    return df.to_feather(file_path)


def _clean_data_by_min_total_spend(df: pd.DataFrame, min_total_spend: float = 15):
    """
    删除低于指定总消费的广告数据"""
    ad_total_spend = df.groupby("ad_id")["spend"].sum()
    valid_ad_ids = ad_total_spend[ad_total_spend >= min_total_spend].index.tolist()
    return df[df["ad_id"].isin(valid_ad_ids)].copy()


def _clean_data_by_rules(df: pd.DataFrame):
    """
    删除无效数据"""
    df = df[~((df["spend"] == 0) & ((df["impressions"] > 0) | (df["clicks"] > 0)))]
    return df.sort_values(["ad_id", "date"]).reset_index(drop=True)


def clean_data(df: pd.DataFrame, min_total_spend=15):
    """
    清理数据
    """
    df.rename(columns={"date_start": "date"}, inplace=True)
    df = _clean_data_by_rules(df)
    df = _clean_data_by_min_total_spend(df, min_total_spend=min_total_spend)
    return df


def _safe_div(a, b):
    return np.where(b > 0, a / b, 0.0)


def build_features(
    df: pd.DataFrame,
    lookback_days=3,  # 回溯时间
    decay_weights=(0.2, 0.3, 0.5),  # 衰减权重，用于计算各个指标的加权和
    append_day=4,  # 追加的日期数，多考虑lookback_days前append_day的数据，这部分数据不参与动量等的计算
    iloc_index=2,
) -> pd.DataFrame:
    """
    构建特征
    """
    df = df.copy()
    w = np.array(decay_weights, dtype="float32")
    w /= w.sum()

    def per_ad(ad_df):
        ad_df = ad_df.sort_values("date")
        rolled = {}
        cols = [
            "spend",
            "impressions",
            "clicks",
            "landing_page_view",
            "onsite_web_add_to_cart",
            "onsite_web_purchase",
            "onsite_web_add_to_cart_value",
            "onsite_web_purchase_value",
        ]
        for col in cols:
            for k in range(1, lookback_days + 1 + append_day):
                rolled[f"{col}_lag{k}"] = ad_df[col].shift(k).fillna(0)
        feat = pd.concat([ad_df, pd.DataFrame(rolled, index=ad_df.index)], axis=1)

        # 比例特征（按lag）
        for k in range(1, lookback_days + 1 + append_day):
            feat[f"ctr_lag{k}"] = _safe_div(
                feat[f"clicks_lag{k}"], feat[f"impressions_lag{k}"]
            )
            feat[f"cpc_lag{k}"] = _safe_div(
                feat[f"spend_lag{k}"], feat[f"clicks_lag{k}"]
            )
            feat[f"lpv_rate_lag{k}"] = _safe_div(
                feat[f"landing_page_view_lag{k}"], feat[f"clicks_lag{k}"]
            )
            feat[f"atc_rate_lag{k}"] = _safe_div(
                feat[f"onsite_web_add_to_cart_lag{k}"],
                feat[f"landing_page_view_lag{k}"],
            )
            feat[f"purchase_rate_lag{k}"] = _safe_div(
                feat[f"onsite_web_purchase_lag{k}"],
                feat[f"onsite_web_add_to_cart_lag{k}"],
            )
            feat[f"roas_lag{k}"] = _safe_div(
                feat[f"onsite_web_purchase_value_lag{k}"], feat[f"spend_lag{k}"]
            )

        # 趋势/动能
        feat["spend_trend"] = feat["spend_lag1"] - feat["spend_lag3"]
        feat["ctr_trend"] = feat["ctr_lag1"] - feat["ctr_lag3"]
        feat["roas_momentum"] = _safe_div(feat["roas_lag1"], (feat["roas_lag3"] + 1e-9))

        # 波动率
        def vol(prefix):
            cols = [
                f"{prefix}_lag{k}" for k in range(1, lookback_days + 1 + append_day)
            ]
            return feat[cols].std(axis=1) / (feat[cols].mean(axis=1) + 1e-9)

        feat["cpc_vol"] = vol("cpc")
        feat["ctr_vol"] = vol("ctr")
        feat["roas_vol"] = vol("roas")

        # 衰减均值
        def decay_mean(prefix):
            arr = np.stack(
                [feat[f"{prefix}_lag{k}"].values for k in range(1, lookback_days + 1)],
                axis=1,
            )
            return (arr * w).sum(axis=1)

        for p in [
            "spend",
            "ctr",
            "cpc",
            "lpv_rate",
            "atc_rate",
            "purchase_rate",
            "roas",
        ]:
            feat[f"{p}_decay3"] = decay_mean(p)

        # 丢弃没有完整lookback的行
        # feat = feat.iloc[lookback_days :].reset_index(drop=True)
        feat = feat.iloc[iloc_index:].reset_index(drop=True)
        return feat

    return df.groupby("ad_id", group_keys=False).apply(per_ad, include_groups=True)


def build_labels(
    df: pd.DataFrame,
    target_roas=0.5,
    pos_margin=0.9,
    neg_margin=1.1,
    future_horizon_days: int = 7,  # 考虑未来几天的数据
) -> pd.DataFrame:
    """
    构建标签

    target_roas: 目标ROAS
    pos_margin: 预测为正的样本的margin
    neg_margin: 预测为负的样本的margin
    """

    df = df.copy().sort_values(["ad_id", "date"])
    df["rev"] = df["onsite_web_purchase_value"].astype("float64")
    df["sp"] = df["spend"].astype("float64")

    def per_ad(ad_df):
        # 确保数据按日期排序
        ad_df = ad_df.sort_values("date").reset_index(drop=True)

        # 计算过去3天收入和花费（共3天）
        past_plus_current_rev = sum(
            [
                ad_df["rev"].shift(k).fillna(0) for k in range(1, 4)
            ]  # 0:今天, 1:昨天, 2:前天, 3:大前天
        )
        past_plus_current_sp = sum(
            [ad_df["sp"].shift(k).fillna(0) for k in range(1, 4)]
        )

        # # 计算未来4天的收入和花费
        # future_rev_4 = sum(
        #     [
        #         ad_df["rev"].shift(-k).fillna(0) for k in range(0, 4)
        #     ]  # 0:今天, 1:明天, 2:后天, 3:大后天
        # )
        # future_sp_4 = sum([ad_df["sp"].shift(-k).fillna(0) for k in range(0, 4)])

        # 计算未来7天的收入和花费
        future_rev = sum(
            [ad_df["rev"].shift(-k).fillna(0) for k in range(0, future_horizon_days)]
        )
        future_sp = sum(
            [ad_df["sp"].shift(-k).fillna(0) for k in range(0, future_horizon_days)]
        )
        roas_fut = np.where(future_sp > 0, future_rev / future_sp, 0.0)

        # # 合并所有时间段的总收入和总花费（过去3天+今天+未来3天，共7天）
        # total_rev = past_plus_current_rev + future_rev_4
        # total_sp = past_plus_current_sp + future_sp_4

        total_rev = past_plus_current_rev + future_rev
        total_sp = past_plus_current_sp + future_sp

        # 计算合并时间段的ROAS
        roas_total = np.where(total_sp > 0, total_rev / total_sp, 0.0)

        # 构建输出DataFrame
        out = ad_df[["ad_id", "date"]].copy()
        # 新增各时间段的明细列
        out["rev_past3d_current"] = past_plus_current_rev
        out["spend_past3d_current"] = past_plus_current_sp
        out["rev_future3d"] = future_rev
        out["spend_future3d"] = future_sp
        # 合并时间段的总计列
        out["rev_total_7d"] = total_rev
        out["spend_total_7d"] = total_sp
        out["roas_total_7d"] = roas_total
        # 记录未来7天收入和花费
        out["rev_future_7d"] = future_rev
        out["spend_future_7d"] = future_sp
        out["roas_future_7d"] = roas_fut

        # 计算目标变量y（基于合并时间段的ROAS）
        y = np.full(len(out), np.nan)
        y[roas_total < target_roas * pos_margin] = 1
        y[roas_total > target_roas * neg_margin] = 0
        out["y"] = y

        return out

    return df.groupby("ad_id", group_keys=False).apply(per_ad, include_groups=True)


if __name__ == "__main__":
    import pandas as pd

    # Example usage: load data from a feather file and build features/labels
    # df = pd.read_feather("path/to/your/data.feather")
    # ad_total_spend = df.groupby("ad_id")["spend"].sum()
    # print(ad_total_spend.describe())
    #
    # df_clean = clean_data(df)
    # feat = build_features(df_clean)
    # labels = build_labels(df_clean)
    # feat.to_feather("models/feat.feather")
    # labels.to_feather("models/labels.feather")
    # print(feat.describe())
    # print(labels.describe())
    pass
