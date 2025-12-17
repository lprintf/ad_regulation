"""
广告组加购率守卫规则 - ML增强版

结合 HHI 分析和 ML 模型判断广告好坏：
1. 使用 pandas 高效处理数据
2. 使用 ML 模型预测广告停止概率
3. 结合 HHI 分析确定哪些广告"吃到预算"
4. 综合 ATC 率、效率分数、ML 预测来决策
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@dataclass
class AdPerformanceML:
    """单个广告的表现数据（ML增强版）"""

    ad_id: str
    ad_name: str | None
    # 7天累计数据
    spend_7d: float
    clicks_7d: int
    lpv_7d: int
    atc_7d: int
    impressions_7d: int
    purchase_7d: int
    purchase_value_7d: float
    # 计算指标
    spend_share: float = 0.0
    atc_share: float = 0.0
    atc_rate: float = 0.0
    efficiency_score: float = 0.0
    ctr: float = 0.0
    cpm: float = 0.0
    roas: float = 0.0
    # ML 预测
    ml_stop_probability: float = 0.0
    ml_recommendation: str = ""
    # 分类标签
    is_eating_budget: bool = False
    is_inefficient: bool = False
    # 活跃窗口
    active_windows: dict = field(default_factory=dict)


@dataclass
class HHIAnalysis:
    """HHI 分析结果"""

    spend_hhi: float
    atc_hhi: float
    effective_ad_count: float
    concentration_level: str


@register_rule
class AdSetATCGuardMLRule(RuleBase):
    """广告组加购率守卫规则 - ML增强版"""

    name: ClassVar[str] = "luopan@adset_atc_guard_ml"
    description: ClassVar[str] = (
        "结合 HHI 分析和 ML 模型的广告组优化规则，使用 pandas 高效处理数据"
    )
    version: ClassVar[str] = "1.0.0"
    tags: ClassVar[list[str]] = ["adset", "atc", "hhi", "ml", "pandas"]

    parameters_schema: ClassVar[dict[str, Any]] = {
        "evaluation_date": {
            "type": "string",
            "label": "评估日期",
            "description": "规则评估的时间点，格式：YYYY-MM-DD（留空使用昨天）",
            "default": "",
            "required": False,
        },
        "atc_rate_threshold": {
            "type": "number",
            "default": 0.05,
            "label": "加购率阈值",
            "description": "广告组加购率低于此阈值时触发优化",
            "min": 0.01,
            "max": 0.20,
            "step": 0.01,
            "unit": "%",
        },
        "ml_stop_threshold": {
            "type": "number",
            "default": 0.6,
            "label": "ML停止阈值",
            "description": "ML模型预测的停止概率超过此阈值时建议暂停",
            "min": 0.4,
            "max": 0.9,
            "step": 0.05,
        },
        "efficiency_threshold": {
            "type": "number",
            "default": 0.5,
            "label": "效率阈值",
            "description": "效率分数（ATC占比/花费占比）低于此值视为低效",
            "min": 0.1,
            "max": 1.0,
            "step": 0.1,
        },
        "min_spend_for_ml": {
            "type": "number",
            "default": 10.0,
            "label": "ML评估最小花费",
            "description": "广告至少花费多少美元才进行ML评估",
            "min": 1.0,
            "max": 100.0,
            "unit": "USD",
        },
        "max_ads_to_pause": {
            "type": "integer",
            "default": 2,
            "label": "单次最多关闭数",
            "description": "单次执行最多关闭几个低效广告",
            "min": 1,
            "max": 5,
        },
        "min_remaining_ads": {
            "type": "integer",
            "default": 2,
            "label": "最少保留广告数",
            "description": "至少保留几个活跃广告",
            "min": 1,
            "max": 5,
        },
        "model_path": {
            "type": "string",
            "default": "experiments/src/output/model_all_data.joblib",
            "label": "模型路径",
            "description": "ML模型文件路径",
        },
        "dry_run": {
            "type": "boolean",
            "default": True,
            "label": "试运行模式",
            "description": "启用后仅输出建议，不自动执行操作",
        },
    }

    async def evaluate(self) -> RuleResult:
        """执行广告组加购率守卫评估（ML增强版）"""
        from api.services.insights_service import InsightsService
        from baseline.train_tools import load_model

        # 验证 binding
        if not self.binding:
            return RuleResult(decision="error", reasons=["No binding provided"])

        ad_account_id = self.binding.ad_account_id
        if not ad_account_id:
            return RuleResult(
                decision="error", reasons=["Missing ad_account_id in binding"]
            )

        # 获取 adset_id
        entity_type = self.binding.entity_type
        entity_id = self.binding.entity_id

        if entity_type == "adset":
            adset_id = entity_id
        elif entity_type == "ad":
            adset_id = await self._get_adset_id_from_ad(ad_account_id, entity_id)
            if not adset_id:
                return RuleResult(
                    decision="error",
                    reasons=[f"Cannot get adset_id for ad {entity_id}"],
                )
        else:
            return RuleResult(
                decision="error",
                reasons=[f"Unsupported entity_type: {entity_type}"],
            )

        # 获取参数
        atc_threshold = self.get_param("atc_rate_threshold", 0.05)
        ml_stop_threshold = self.get_param("ml_stop_threshold", 0.6)
        efficiency_threshold = self.get_param("efficiency_threshold", 0.5)
        min_spend_for_ml = self.get_param("min_spend_for_ml", 10.0)
        max_pause = self.get_param("max_ads_to_pause", 2)
        min_remaining = self.get_param("min_remaining_ads", 2)
        model_path = self.get_param(
            "model_path", "experiments/src/output/model_all_data.joblib"
        )
        dry_run = self.get_param("dry_run", True)

        # 确定评估日期
        eval_date_str = self.get_param("evaluation_date")
        if eval_date_str:
            try:
                eval_date = datetime.strptime(eval_date_str, "%Y-%m-%d")
            except ValueError:
                eval_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        else:
            eval_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)

        date_str = eval_date.strftime("%Y-%m-%d")
        seven_days_ago = eval_date - timedelta(days=6)
        since_str = seven_days_ago.strftime("%Y-%m-%d")

        self.log(f"AdSet ID: {adset_id}")
        self.log(f"Evaluation Date: {date_str}")
        self.log(f"Data Range: {since_str} ~ {date_str}")
        self.log(f"ATC Rate Threshold: {atc_threshold:.1%}")
        self.log(f"ML Stop Threshold: {ml_stop_threshold:.1%}")

        # 加载 ML 模型
        model = None
        feature_names = []
        if os.path.exists(model_path):
            try:
                model_package = load_model(model_path)
                if isinstance(model_package, dict) and "model" in model_package:
                    model = model_package["model"]
                    feature_names = model_package.get("feature_names", [])
                else:
                    model = model_package
                self.log(f"Loaded ML model with {len(feature_names)} features")
            except Exception as exc:
                self.log(f"Failed to load ML model: {exc}", "WARNING")
        else:
            self.log(f"ML model not found: {model_path}", "WARNING")

        # 获取 insights 数据
        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since_str,
                until=date_str,
                level="ad",
                time_increment=1,
            )
        except Exception as exc:
            self.log(f"Failed to fetch insights: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Data fetch failed: {exc}"])

        insights_records = insights_data.get("insights", [])
        if not insights_records:
            return RuleResult(
                decision="skip",
                reasons=["No insights data for the evaluation period"],
            )

        # 使用 pandas 高效处理数据
        df = self._build_dataframe(insights_records)
        if df.empty:
            return RuleResult(decision="skip", reasons=["No valid data"])

        # 过滤该广告组的数据
        df_adset = df[df["adset_id"] == adset_id].copy()
        if df_adset.empty:
            return RuleResult(
                decision="skip",
                reasons=[f"No ads found in adset {adset_id}"],
            )

        self.log(f"Found {df_adset['ad_id'].nunique()} ads in adset")

        # 聚合 7 天数据
        ad_stats = self._aggregate_ad_stats(df_adset, date_str)

        # 计算广告组整体指标
        total_spend = ad_stats["spend_7d"].sum()
        total_lpv = ad_stats["lpv_7d"].sum()
        total_clicks = ad_stats["clicks_7d"].sum()
        total_atc = ad_stats["atc_7d"].sum()

        denominator = total_lpv if total_lpv > 0 else total_clicks
        adset_atc_rate = total_atc / denominator if denominator > 0 else 0

        self.log(f"AdSet 7D: Spend=${total_spend:.2f}, LPV={total_lpv}, ATC={total_atc}")
        self.log(f"AdSet ATC Rate: {adset_atc_rate:.2%}")

        # 计算 HHI 和有效广告数
        ad_stats = self._calculate_shares(ad_stats, total_spend, total_atc)
        hhi_analysis = self._calculate_hhi(ad_stats)

        self.log(
            f"HHI: {hhi_analysis.spend_hhi:.0f}, "
            f"Effective Ads: {hhi_analysis.effective_ad_count:.1f}, "
            f"Concentration: {hhi_analysis.concentration_level}"
        )

        # 确定"吃到预算"阈值
        spend_share_threshold = (
            1.0 / hhi_analysis.effective_ad_count
            if hhi_analysis.effective_ad_count > 0
            else 0
        )

        # 标记广告分类
        ad_stats["is_eating_budget"] = ad_stats["spend_share"] > spend_share_threshold
        ad_stats["is_inefficient"] = ad_stats["efficiency_score"] < efficiency_threshold

        # ML 预测（仅对花费足够的广告）
        if model is not None:
            ad_stats = await self._run_ml_predictions(
                ad_stats,
                df_adset,
                model,
                feature_names,
                min_spend_for_ml,
            )
        else:
            ad_stats["ml_stop_probability"] = 0.0
            ad_stats["ml_recommendation"] = "无模型"

        # 构建 AdPerformanceML 列表
        performances = self._build_performances(ad_stats, date_str, df_adset)

        # 构建结果
        return self._build_result(
            performances=performances,
            adset_id=adset_id,
            adset_atc_rate=adset_atc_rate,
            atc_threshold=atc_threshold,
            ml_stop_threshold=ml_stop_threshold,
            efficiency_threshold=efficiency_threshold,
            hhi_analysis=hhi_analysis,
            max_pause=max_pause,
            min_remaining=min_remaining,
            dry_run=dry_run,
            date_str=date_str,
            total_spend=total_spend,
            total_atc=total_atc,
        )

    def _build_dataframe(self, records: list[dict]) -> pd.DataFrame:
        """将 insights 记录转换为 DataFrame"""
        rows = []
        for record in records:
            m = record.get("metrics", {})
            rows.append({
                "ad_id": record.get("ad_id"),
                "adset_id": record.get("adset_id"),
                "campaign_id": record.get("campaign_id"),
                "ad_name": record.get("ad_name"),
                "date": record.get("date"),
                "spend": float(m.get("spend") or 0),
                "impressions": int(m.get("impressions") or 0),
                "clicks": int(m.get("clicks") or 0),
                "landing_page_view": int(m.get("landing_page_view") or 0),
                "onsite_web_add_to_cart": int(m.get("onsite_web_add_to_cart") or 0),
                "onsite_web_purchase": int(m.get("onsite_web_purchase") or 0),
                "onsite_web_purchase_value": float(m.get("onsite_web_purchase_value") or 0),
                "reach": int(m.get("reach") or 0),
                "inline_link_clicks": int(m.get("inline_link_clicks") or 0),
                "outbound_clicks": int(m.get("outbound_clicks") or 0),
                "onsite_web_add_to_cart_value": float(m.get("onsite_web_add_to_cart_value") or 0),
                "onsite_web_checkout": int(m.get("onsite_web_checkout") or 0),
                "onsite_web_checkout_value": float(m.get("onsite_web_checkout_value") or 0),
            })

        df = pd.DataFrame(rows)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values(["ad_id", "date"]).reset_index(drop=True)
        return df

    def _aggregate_ad_stats(self, df: pd.DataFrame, eval_date_str: str) -> pd.DataFrame:
        """聚合每个广告的 7 天统计数据"""
        eval_date = pd.to_datetime(eval_date_str)

        # 7天聚合
        agg_7d = df.groupby("ad_id").agg({
            "ad_name": "last",
            "spend": "sum",
            "clicks": "sum",
            "impressions": "sum",
            "landing_page_view": "sum",
            "onsite_web_add_to_cart": "sum",
            "onsite_web_purchase": "sum",
            "onsite_web_purchase_value": "sum",
        }).reset_index()

        agg_7d.columns = [
            "ad_id", "ad_name", "spend_7d", "clicks_7d", "impressions_7d",
            "lpv_7d", "atc_7d", "purchase_7d", "purchase_value_7d"
        ]

        # 计算指标
        agg_7d["ctr"] = np.where(
            agg_7d["impressions_7d"] > 0,
            agg_7d["clicks_7d"] / agg_7d["impressions_7d"],
            0
        )
        agg_7d["cpm"] = np.where(
            agg_7d["impressions_7d"] > 0,
            agg_7d["spend_7d"] / agg_7d["impressions_7d"] * 1000,
            0
        )
        denom = np.where(agg_7d["lpv_7d"] > 0, agg_7d["lpv_7d"], agg_7d["clicks_7d"])
        agg_7d["atc_rate"] = np.where(denom > 0, agg_7d["atc_7d"] / denom, 0)
        agg_7d["roas"] = np.where(
            agg_7d["spend_7d"] > 0,
            agg_7d["purchase_value_7d"] / agg_7d["spend_7d"],
            0
        )

        # 计算活跃窗口
        def calc_active_windows(ad_id):
            ad_df = df[df["ad_id"] == ad_id]
            windows = {}
            for window_name, days in [("1d", 1), ("3d", 3), ("5d", 5), ("7d", 7)]:
                start = eval_date - timedelta(days=days - 1)
                mask = (ad_df["date"] >= start) & (ad_df["date"] <= eval_date)
                windows[window_name] = ad_df.loc[mask, "spend"].sum() > 0
            return windows

        agg_7d["active_windows"] = agg_7d["ad_id"].apply(calc_active_windows)

        return agg_7d

    def _calculate_shares(
        self, df: pd.DataFrame, total_spend: float, total_atc: int
    ) -> pd.DataFrame:
        """计算花费占比、ATC占比和效率分数"""
        df = df.copy()
        df["spend_share"] = np.where(
            total_spend > 0, df["spend_7d"] / total_spend, 0
        )
        df["atc_share"] = np.where(
            total_atc > 0, df["atc_7d"] / total_atc, 0
        )
        df["efficiency_score"] = np.where(
            df["spend_share"] > 0,
            df["atc_share"] / df["spend_share"],
            0
        )
        return df

    def _calculate_hhi(self, df: pd.DataFrame) -> HHIAnalysis:
        """计算 HHI（赫芬达尔-赫希曼指数）"""
        spend_hhi = ((df["spend_share"] * 100) ** 2).sum()
        atc_hhi = ((df["atc_share"] * 100) ** 2).sum()
        effective_count = 10000 / spend_hhi if spend_hhi > 0 else len(df)

        if spend_hhi >= 5000:
            level = "高度集中"
        elif spend_hhi >= 2500:
            level = "中度集中"
        elif spend_hhi >= 1500:
            level = "低度集中"
        else:
            level = "分散"

        return HHIAnalysis(
            spend_hhi=spend_hhi,
            atc_hhi=atc_hhi,
            effective_ad_count=effective_count,
            concentration_level=level,
        )

    async def _run_ml_predictions(
        self,
        ad_stats: pd.DataFrame,
        df_raw: pd.DataFrame,
        model,
        feature_names: list[str],
        min_spend: float,
    ) -> pd.DataFrame:
        """对每个广告运行 ML 预测"""
        from baseline.data_build import build_features, clean_data

        ad_stats = ad_stats.copy()
        probas = []
        recommendations = []

        for _, row in ad_stats.iterrows():
            ad_id = row["ad_id"]
            spend = row["spend_7d"]

            if spend < min_spend:
                probas.append(0.0)
                recommendations.append("花费不足，跳过ML评估")
                continue

            # 获取该广告的数据
            ad_df = df_raw[df_raw["ad_id"] == ad_id].copy()
            ad_df = ad_df.rename(columns={
                "landing_page_view": "landing_page_view",
                "onsite_web_add_to_cart": "onsite_web_add_to_cart",
                "onsite_web_purchase": "onsite_web_purchase",
                "onsite_web_purchase_value": "onsite_web_purchase_value",
            })

            try:
                # 清洗数据
                df_clean = clean_data(ad_df, min_total_spend=min_spend * 0.5)
                if df_clean.empty or len(df_clean) < 3:
                    probas.append(0.0)
                    recommendations.append("数据不足")
                    continue

                # 构建特征
                features = build_features(df_clean, iloc_index=-1)
                if features.empty:
                    probas.append(0.0)
                    recommendations.append("特征构建失败")
                    continue

                # 预测
                proba = self._predict(features, model, feature_names)
                probas.append(proba if proba is not None else 0.0)

                if proba is not None:
                    if proba >= 0.7:
                        recommendations.append("ML建议停止")
                    elif proba >= 0.5:
                        recommendations.append("ML建议观察")
                    else:
                        recommendations.append("ML评估良好")
                else:
                    recommendations.append("预测失败")

            except Exception as exc:
                self.log(f"ML prediction failed for {ad_id}: {exc}", "WARNING")
                probas.append(0.0)
                recommendations.append("预测异常")

        ad_stats["ml_stop_probability"] = probas
        ad_stats["ml_recommendation"] = recommendations
        return ad_stats

    def _predict(
        self, features: pd.DataFrame, model, feature_names: list[str]
    ) -> float | None:
        """使用模型进行预测"""
        try:
            if feature_names:
                available = set(features.columns)
                missing = [f for f in feature_names if f not in available]
                if missing:
                    return None
                X = features[feature_names].fillna(0)
            else:
                feature_cols = [c for c in features.columns if c not in ["ad_id", "date"]]
                X = features[feature_cols].fillna(0)

            if len(X) > 0:
                proba = model.predict_proba(X.iloc[[-1]])[0, 1]
                return float(proba)
        except Exception:
            pass
        return None

    def _build_performances(
        self, ad_stats: pd.DataFrame, eval_date_str: str, df_raw: pd.DataFrame
    ) -> list[AdPerformanceML]:
        """构建 AdPerformanceML 列表"""
        performances = []
        for _, row in ad_stats.iterrows():
            performances.append(AdPerformanceML(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                spend_7d=row["spend_7d"],
                clicks_7d=row["clicks_7d"],
                lpv_7d=row["lpv_7d"],
                atc_7d=row["atc_7d"],
                impressions_7d=row["impressions_7d"],
                purchase_7d=row["purchase_7d"],
                purchase_value_7d=row["purchase_value_7d"],
                spend_share=row["spend_share"],
                atc_share=row["atc_share"],
                atc_rate=row["atc_rate"],
                efficiency_score=row["efficiency_score"],
                ctr=row["ctr"],
                cpm=row["cpm"],
                roas=row["roas"],
                ml_stop_probability=row["ml_stop_probability"],
                ml_recommendation=row["ml_recommendation"],
                is_eating_budget=row["is_eating_budget"],
                is_inefficient=row["is_inefficient"],
                active_windows=row["active_windows"],
            ))
        return performances

    def _build_result(
        self,
        performances: list[AdPerformanceML],
        adset_id: str,
        adset_atc_rate: float,
        atc_threshold: float,
        ml_stop_threshold: float,
        efficiency_threshold: float,
        hhi_analysis: HHIAnalysis,
        max_pause: int,
        min_remaining: int,
        dry_run: bool,
        date_str: str,
        total_spend: float,
        total_atc: int,
    ) -> RuleResult:
        """构建最终结果"""
        actions = []
        notes = []

        # 基础信息
        reasons = [
            f"📅 广告组 {adset_id} 评估日期: {date_str}",
            f"📊 7D花费 ${total_spend:.2f}，加购 {total_atc} 次",
            f"📈 ATC率 {adset_atc_rate:.2%}（阈值 {atc_threshold:.1%}）",
            f"🎯 花费集中度: {hhi_analysis.concentration_level}（有效广告 {hhi_analysis.effective_ad_count:.1f} 个）",
        ]

        # 分类广告
        eating_budget = [p for p in performances if p.is_eating_budget]
        not_eating_budget = [p for p in performances if not p.is_eating_budget]

        # 识别需要停止的广告（综合判断）
        # 条件：吃到预算 + (低效率 OR ML建议停止)
        ads_to_stop = []
        for p in eating_budget:
            should_stop = False
            stop_reasons = []

            if p.is_inefficient:
                stop_reasons.append(f"效率低({p.efficiency_score:.2f})")
                should_stop = True

            if p.ml_stop_probability >= ml_stop_threshold:
                stop_reasons.append(f"ML建议停止({p.ml_stop_probability:.1%})")
                should_stop = True

            if should_stop:
                ads_to_stop.append((p, stop_reasons))

        # 按综合评分排序（ML概率 + 低效程度）
        ads_to_stop.sort(
            key=lambda x: x[0].ml_stop_probability + (1 - x[0].efficiency_score),
            reverse=True
        )

        # 限制关闭数量
        good_ads_count = len([p for p in performances if not p.is_inefficient])
        if good_ads_count >= min_remaining:
            num_to_pause = min(len(ads_to_stop), max_pause)
        else:
            must_keep = max(1, min_remaining - good_ads_count)
            max_can_pause = max(0, len(ads_to_stop) - must_keep)
            num_to_pause = min(max_can_pause, max_pause)

        final_to_pause = ads_to_stop[:num_to_pause]

        # 显示吃到预算的广告
        if eating_budget:
            reasons.append(f"💰 {len(eating_budget)} 个广告吃到预算:")
            for p in sorted(eating_budget, key=lambda x: x.spend_share, reverse=True)[:5]:
                ml_info = f"ML={p.ml_stop_probability:.0%}" if p.ml_stop_probability > 0 else p.ml_recommendation
                reasons.append(
                    f"  - {p.ad_name or p.ad_id}: "
                    f"7D花费 ${p.spend_7d:.2f}，CTR={p.ctr:.2%}，CPM=${p.cpm:.2f}，"
                    f"效率={p.efficiency_score:.2f}，{ml_info}"
                )

        # 显示未吃到预算的广告
        if not_eating_budget:
            reasons.append(f"💤 {len(not_eating_budget)} 个广告未吃到预算:")
            for p in not_eating_budget[:3]:
                ml_info = f"ML={p.ml_stop_probability:.0%}" if p.ml_stop_probability > 0 else p.ml_recommendation
                reasons.append(
                    f"  - {p.ad_name or p.ad_id}: "
                    f"7D花费 ${p.spend_7d:.2f}，CTR={p.ctr:.2%}，CPM=${p.cpm:.2f}，{ml_info}"
                )

        # 显示建议关闭的广告
        if final_to_pause:
            reasons.append(f"❌ 建议关闭 {len(final_to_pause)} 个广告:")
            for p, stop_reasons in final_to_pause:
                reason_str = "，".join(stop_reasons)
                reasons.append(
                    f"  - {p.ad_name or p.ad_id}: {reason_str}，"
                    f"ROAS={p.roas:.2f}"
                )
                if not dry_run:
                    actions.append({
                        "action": "pause_ad",
                        "entity_type": "ad",
                        "entity_id": p.ad_id,
                        "reason": reason_str,
                    })

            if dry_run:
                notes.append(f"[试运行模式] 建议关闭 {len(final_to_pause)} 个广告")
        elif ads_to_stop:
            reasons.append(
                f"⚠️ 识别到 {len(ads_to_stop)} 个问题广告，"
                f"但需保留至少 {min_remaining} 个，暂不关闭"
            )

        # 显示表现良好的广告
        good_performers = [
            p for p in performances
            if not p.is_inefficient and p.ml_stop_probability < ml_stop_threshold
        ]
        if good_performers:
            reasons.append(f"✅ {len(good_performers)} 个广告表现良好:")
            for p in sorted(good_performers, key=lambda x: x.efficiency_score, reverse=True)[:3]:
                reasons.append(
                    f"  - {p.ad_name or p.ad_id}: "
                    f"效率={p.efficiency_score:.2f}，ROAS={p.roas:.2f}，"
                    f"ML={p.ml_stop_probability:.0%}"
                )

        # 构建指标
        metrics = {
            "adset_id": adset_id,
            "evaluation_date": date_str,
            "adset_atc_rate": adset_atc_rate,
            "total_spend_7d": total_spend,
            "total_atc_7d": total_atc,
            "spend_hhi": hhi_analysis.spend_hhi,
            "effective_ad_count": hhi_analysis.effective_ad_count,
            "total_ads": len(performances),
            "eating_budget_count": len(eating_budget),
            "ads_to_pause": [p.ad_id for p, _ in final_to_pause],
            "ad_details": [
                {
                    "ad_id": p.ad_id,
                    "ad_name": p.ad_name,
                    "spend_7d": p.spend_7d,
                    "spend_share": p.spend_share,
                    "atc_7d": p.atc_7d,
                    "efficiency_score": p.efficiency_score,
                    "ml_stop_probability": p.ml_stop_probability,
                    "roas": p.roas,
                    "ctr": p.ctr,
                    "cpm": p.cpm,
                    "is_eating_budget": p.is_eating_budget,
                    "is_inefficient": p.is_inefficient,
                }
                for p in performances
            ],
        }

        # 确定决策
        if final_to_pause:
            decision = "stop_recommended" if dry_run else "stop_executed"
        elif adset_atc_rate < atc_threshold:
            decision = "continue"
            notes.append("ATC率未达标但无明确需关闭的广告")
        else:
            decision = "continue"

        return RuleResult(
            decision=decision,
            actions=actions,
            reasons=reasons,
            metrics=metrics,
            notes=notes,
        )

    async def _get_adset_id_from_ad(self, ad_account_id: str, ad_id: str) -> str | None:
        """从广告获取其所属广告组ID"""
        try:
            from utils.fb_api_flyweight_factory import get_ad_object

            ad_obj = await get_ad_object(ad_account_id, ad_id)
            ad_info = ad_obj.api_get(fields=["adset_id"])
            return ad_info.get("adset_id")
        except Exception as exc:
            self.log(f"Failed to get adset_id: {exc}", "WARNING")
            return None
