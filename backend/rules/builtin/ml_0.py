"""
ML调控规则 - 高级版本

支持功能:
- 多时间窗口评估：当回溯天数 > 7 天时，选择多个时间点分别调用模型
- 最佳预算探索：在 ±20% 范围内调整花费评分，确定最佳预算
- 多广告评估：支持对同一系列/广告组下的多个广告进行批量评估
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@dataclass
class AdEvaluation:
    """单个广告的评估结果"""

    ad_id: str
    ad_name: str | None
    stop_probability: float
    optimal_budget_ratio: float  # 最佳预算相对于当前预算的比例 (0.8 - 1.2)
    time_window_scores: list[float]  # 各时间窗口的评分
    metrics: dict[str, Any]
    recommendation: str


@register_rule
class MLControlRule(RuleBase):
    """ML调控规则 - 高级版本"""

    name: ClassVar[str] = "ml_control"
    description: ClassVar[str] = (
        "基于ML模型的高级广告调控规则，支持多时间窗口评估、预算优化和批量广告评估"
    )
    version: ClassVar[str] = "1.0.0"
    tags: ClassVar[list[str]] = ["ml", "budget_optimization", "multi_window", "batch"]

    parameters_schema: ClassVar[dict[str, Any]] = {
        "evaluation_date": {
            "type": "string",
            "label": "评估日期",
            "description": "规则评估的时间点，格式：YYYY-MM-DD",
            "default": "",
            "required": False,
            "hint": "留空使用当前日期",
        },
        "lookback_days": {
            "type": "integer",
            "default": 14,
            "label": "数据回溯天数",
            "description": "从评估日期往前回溯的天数（可超过7天，会自动分多窗口评估）",
            "min": 7,
            "max": 60,
            "unit": "天",
            "hint": "建议14-30天，系统会自动选择多个7天窗口进行评估",
        },
        "stop_probability_threshold": {
            "type": "number",
            "default": 0.7,
            "label": "停止概率阈值",
            "description": "综合评分超过此阈值时建议暂停广告",
            "min": 0.5,
            "max": 0.95,
            "step": 0.05,
        },
        "budget_optimization_enabled": {
            "type": "boolean",
            "default": True,
            "label": "启用预算优化",
            "description": "是否在 ±20% 范围内探索最佳预算",
            "hint": "启用后会模拟不同预算水平下的模型评分",
        },
        "budget_search_steps": {
            "type": "integer",
            "default": 5,
            "label": "预算搜索步数",
            "description": "在 ±20% 范围内的搜索粒度",
            "min": 3,
            "max": 10,
        },
        "evaluate_siblings": {
            "type": "boolean",
            "default": False,
            "label": "评估同级广告",
            "description": "同时评估同一广告组/系列下的其他广告",
            "hint": "启用后会获取并评估相关广告",
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

    # 模型窗口大小（固定为7天）
    MODEL_WINDOW_DAYS: ClassVar[int] = 7

    async def evaluate(self) -> RuleResult:
        """执行ML调控评估"""
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

        # 获取参数
        lookback_days = self.get_param("lookback_days", 14)
        threshold = self.get_param("stop_probability_threshold", 0.7)
        budget_opt_enabled = self.get_param("budget_optimization_enabled", True)
        budget_steps = self.get_param("budget_search_steps", 5)
        evaluate_siblings = self.get_param("evaluate_siblings", False)
        model_path = self.get_param(
            "model_path", "experiments/src/output/model_all_data.joblib"
        )
        dry_run = self.get_param("dry_run", True)

        # 确定评估日期
        eval_date_str = self.get_param("evaluation_date")
        if eval_date_str:
            try:
                reference_date = datetime.strptime(eval_date_str, "%Y-%m-%d")
            except ValueError:
                reference_date = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            reference_date = datetime.now(timezone.utc).replace(tzinfo=None)

        self.log(f"Evaluation Date: {reference_date.strftime('%Y-%m-%d')}")
        self.log(f"Lookback Days: {lookback_days}")
        self.log(f"Threshold: {threshold:.2%}")
        self.log(f"Budget Optimization: {'ON' if budget_opt_enabled else 'OFF'}")
        self.log(f"Evaluate Siblings: {'ON' if evaluate_siblings else 'OFF'}")
        self.log(f"Dry Run: {'ON' if dry_run else 'OFF'}")

        # 检查模型
        if not os.path.exists(model_path):
            self.log(f"Model not found: {model_path}", "ERROR")
            return RuleResult(
                decision="error",
                reasons=[f"ML model not found: {model_path}"],
                notes=["请先运行 experiments/train_model_use_all_data/3.train_model.py 训练模型"],
            )

        # 加载模型
        try:
            model_package = load_model(model_path)
            if isinstance(model_package, dict) and "model" in model_package:
                model = model_package["model"]
                feature_names = model_package.get("feature_names", [])
            else:
                model = model_package
                feature_names = []
            self.log(f"Loaded model with {len(feature_names)} features")
        except Exception as exc:
            self.log(f"Failed to load model: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Model load failed: {exc}"])

        # 确定要评估的广告列表
        ad_ids = await self._get_ad_ids_to_evaluate(
            ad_account_id, evaluate_siblings
        )
        self.log(f"Ads to evaluate: {len(ad_ids)}")

        # 计算评估时间窗口
        time_windows = self._calculate_time_windows(reference_date, lookback_days)
        self.log(f"Time windows: {len(time_windows)}")

        # 获取广告名称
        ad_names = await self._get_ad_names(ad_account_id, ad_ids)

        # 获取数据（一次性获取所有时间范围的数据）
        since = reference_date - timedelta(days=lookback_days)
        since_str = since.strftime("%Y-%m-%d")
        until_str = reference_date.strftime("%Y-%m-%d")

        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since_str,
                until=until_str,
                level="ad",
                time_increment=1,
                object_ids=ad_ids if len(ad_ids) <= 50 else None,  # 限制查询数量
            )
        except Exception as exc:
            self.log(f"Failed to fetch insights: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Data fetch failed: {exc}"])

        insights_records = insights_data.get("insights", [])
        if not insights_records:
            self.log("No insights data available", "WARNING")
            return RuleResult(
                decision="skip",
                reasons=["No insights data available"],
            )

        # 按广告ID分组数据
        ad_data_map = self._group_insights_by_ad(insights_records, ad_ids)

        # 评估每个广告
        evaluations: list[AdEvaluation] = []
        for ad_id in ad_ids:
            if ad_id not in ad_data_map or not ad_data_map[ad_id]:
                self.log(f"Ad {ad_id}: No data, skipping")
                continue

            eval_result = await self._evaluate_single_ad(
                ad_id=ad_id,
                ad_name=ad_names.get(ad_id),
                records=ad_data_map[ad_id],
                time_windows=time_windows,
                model=model,
                feature_names=feature_names,
                budget_opt_enabled=budget_opt_enabled,
                budget_steps=budget_steps,
                threshold=threshold,
            )
            if eval_result:
                evaluations.append(eval_result)

        if not evaluations:
            return RuleResult(
                decision="skip",
                reasons=["No ads could be evaluated (insufficient data)"],
            )

        # 汇总结果
        return self._build_result(evaluations, threshold, dry_run)

    def _calculate_time_windows(
        self, reference_date: datetime, lookback_days: int
    ) -> list[tuple[datetime, datetime]]:
        """
        计算评估时间窗口

        当回溯天数 > 7 时，选择多个时间点调用模型
        返回: [(window_start, window_end), ...]
        """
        windows = []
        window_size = self.MODEL_WINDOW_DAYS

        if lookback_days <= window_size:
            # 单窗口
            start = reference_date - timedelta(days=lookback_days)
            windows.append((start, reference_date))
        else:
            # 多窗口：从最近往前，每隔 (window_size - 2) 天取一个窗口
            # 这样窗口之间有2天重叠，确保连续性
            step = window_size - 2
            num_windows = max(1, (lookback_days - window_size) // step + 2)

            for i in range(num_windows):
                offset = i * step
                end = reference_date - timedelta(days=offset)
                start = end - timedelta(days=window_size)

                if start < reference_date - timedelta(days=lookback_days):
                    start = reference_date - timedelta(days=lookback_days)

                windows.append((start, end))

        # 按时间排序（从早到晚）
        windows.sort(key=lambda x: x[0])
        return windows

    async def _get_ad_ids_to_evaluate(
        self, ad_account_id: str, evaluate_siblings: bool
    ) -> list[str]:
        """获取要评估的广告ID列表"""
        from utils.fb_api_flyweight_factory import get_ad_object

        primary_ad_id = self.binding.entity_id
        ad_ids = [primary_ad_id]

        if evaluate_siblings and self.binding.entity_type == "ad":
            try:
                # 获取主广告的 adset_id
                ad_obj = get_ad_object(ad_account_id, primary_ad_id, "ad")
                ad_info = ad_obj.api_get(fields=["adset_id"])
                adset_id = ad_info.get("adset_id")

                if adset_id:
                    # 获取同一 adset 下的所有广告
                    adset_obj = get_ad_object(ad_account_id, adset_id, "adset")
                    ads = adset_obj.get_ads(fields=["id", "name", "effective_status"])

                    for ad in ads:
                        if ad["id"] != primary_ad_id:
                            # 只评估活跃或暂停的广告
                            if ad.get("effective_status") in [
                                "ACTIVE",
                                "PAUSED",
                                "PENDING_REVIEW",
                            ]:
                                ad_ids.append(ad["id"])

                    self.log(f"Found {len(ad_ids) - 1} sibling ads in adset {adset_id}")
            except Exception as exc:
                self.log(f"Failed to get sibling ads: {exc}", "WARNING")

        return ad_ids

    async def _get_ad_names(
        self, ad_account_id: str, ad_ids: list[str]
    ) -> dict[str, str]:
        """获取广告名称"""
        from utils.db import AdEntityNamesDocument

        names = {}
        for ad_id in ad_ids:
            entity = await AdEntityNamesDocument.find_one(
                AdEntityNamesDocument.account_id == ad_account_id,
                AdEntityNamesDocument.entity_type == "ad",
                AdEntityNamesDocument.entity_id == ad_id,
            )
            if entity:
                names[ad_id] = entity.entity_name
        return names

    def _group_insights_by_ad(
        self, records: list[dict], ad_ids: list[str]
    ) -> dict[str, list[dict]]:
        """按广告ID分组 insights 数据"""
        ad_data_map: dict[str, list[dict]] = {ad_id: [] for ad_id in ad_ids}

        for record in records:
            ad_id = record.get("ad_id")
            if ad_id in ad_data_map:
                ad_data_map[ad_id].append(record)

        return ad_data_map

    async def _evaluate_single_ad(
        self,
        ad_id: str,
        ad_name: str | None,
        records: list[dict],
        time_windows: list[tuple[datetime, datetime]],
        model,
        feature_names: list[str],
        budget_opt_enabled: bool,
        budget_steps: int,
        threshold: float,
    ) -> AdEvaluation | None:
        """评估单个广告"""
        from baseline.data_build import build_features, clean_data

        # 构建 DataFrame
        df = self._build_dataframe(records, ad_id)
        if df.empty:
            return None

        # 清洗数据（使用较低的阈值，因为单广告数据量可能较小）
        try:
            df_clean = clean_data(df, min_total_spend=5)
            if df_clean.empty:
                self.log(f"Ad {ad_id}: No valid data after cleaning")
                return None
        except Exception as exc:
            self.log(f"Ad {ad_id}: Data cleaning failed: {exc}", "WARNING")
            return None

        # 计算每个时间窗口的评分
        window_scores = []
        for start, end in time_windows:
            # 过滤窗口内的数据
            mask = (df_clean["date"] >= start.strftime("%Y-%m-%d")) & (
                df_clean["date"] <= end.strftime("%Y-%m-%d")
            )
            window_df = df_clean[mask].copy()

            if len(window_df) < 3:  # 至少需要3天数据
                continue

            # 构建特征
            try:
                features = build_features(window_df, iloc_index=-1)
                if features.empty:
                    continue

                # 预测
                score = self._predict_with_features(features, model, feature_names)
                if score is not None:
                    window_scores.append(score)
            except Exception:
                continue

        if not window_scores:
            self.log(f"Ad {ad_id}: No valid window scores")
            return None

        # 计算综合评分（使用时间加权，最近的窗口权重更高）
        weights = np.array([1.0 + 0.5 * i for i in range(len(window_scores))])
        weights = weights / weights.sum()
        avg_score = float(np.average(window_scores, weights=weights))

        # 预算优化
        optimal_ratio = 1.0
        if budget_opt_enabled:
            optimal_ratio = self._find_optimal_budget_ratio(
                df_clean, model, feature_names, budget_steps
            )

        # 计算指标
        total_spend = df["spend"].sum()
        total_purchase_value = df["onsite_web_purchase_value"].sum()
        roas = total_purchase_value / total_spend if total_spend > 0 else 0

        metrics = {
            "spend": float(total_spend),
            "purchase_value": float(total_purchase_value),
            "roas": float(roas),
            "avg_stop_probability": avg_score,
            "window_scores": window_scores,
            "optimal_budget_ratio": optimal_ratio,
        }

        # 生成建议
        if avg_score >= threshold:
            if optimal_ratio < 0.9:
                recommendation = f"建议暂停或大幅降低预算至 {optimal_ratio:.0%}"
            else:
                recommendation = "建议暂停广告"
        elif avg_score >= 0.5:
            if optimal_ratio < 0.95:
                recommendation = f"表现一般，建议降低预算至 {optimal_ratio:.0%}"
            else:
                recommendation = "表现一般，建议观察"
        else:
            if optimal_ratio > 1.05:
                recommendation = f"表现良好，可考虑增加预算至 {optimal_ratio:.0%}"
            else:
                recommendation = "表现良好，建议保持"

        self.log(
            f"Ad {ad_id}: score={avg_score:.2%}, optimal_ratio={optimal_ratio:.2f}, "
            f"windows={len(window_scores)}"
        )

        return AdEvaluation(
            ad_id=ad_id,
            ad_name=ad_name,
            stop_probability=avg_score,
            optimal_budget_ratio=optimal_ratio,
            time_window_scores=window_scores,
            metrics=metrics,
            recommendation=recommendation,
        )

    def _predict_with_features(
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

            # 取最后一行（最近的数据）
            if len(X) > 0:
                proba = model.predict_proba(X.iloc[[-1]])[0, 1]
                return float(proba)
        except Exception:
            pass
        return None

    def _find_optimal_budget_ratio(
        self,
        df_clean: pd.DataFrame,
        model,
        feature_names: list[str],
        budget_steps: int,
    ) -> float:
        """
        在 ±20% 范围内探索最佳预算

        通过修改 spend 相关特征，模拟不同预算水平下的模型评分
        注意：这是一个保守估计，因为实际预算调整会影响其他指标
        """
        from baseline.data_build import build_features

        # 生成预算比例范围: 0.8 到 1.2
        ratios = np.linspace(0.8, 1.2, budget_steps)
        scores = []

        for ratio in ratios:
            # 复制数据并调整花费
            df_adjusted = df_clean.copy()
            df_adjusted["spend"] = df_adjusted["spend"] * ratio

            try:
                features = build_features(df_adjusted, iloc_index=-1)
                if features.empty:
                    scores.append(1.0)  # 无法评估时假设最差
                    continue

                score = self._predict_with_features(features, model, feature_names)
                scores.append(score if score is not None else 1.0)
            except Exception:
                scores.append(1.0)

        # 找到最低评分对应的预算比例
        if scores:
            min_idx = np.argmin(scores)
            return float(ratios[min_idx])
        return 1.0

    def _build_dataframe(self, records: list[dict], ad_id: str) -> pd.DataFrame:
        """将 insights 记录转换为 DataFrame"""
        rows = []
        for record in records:
            m = record.get("metrics", {})
            rows.append(
                {
                    "ad_id": ad_id,
                    "date": record.get("date"),
                    "spend": float(m.get("spend") or 0),
                    "impressions": int(m.get("impressions") or 0),
                    "reach": int(m.get("reach") or 0),
                    "clicks": int(m.get("clicks") or 0),
                    "inline_link_clicks": int(m.get("inline_link_clicks") or 0),
                    "outbound_clicks": int(m.get("outbound_clicks") or 0),
                    "landing_page_view": int(m.get("landing_page_view") or 0),
                    "onsite_web_add_to_cart": int(m.get("onsite_web_add_to_cart") or 0),
                    "onsite_web_checkout": int(m.get("onsite_web_checkout") or 0),
                    "onsite_web_purchase": int(m.get("onsite_web_purchase") or 0),
                    "onsite_web_add_to_cart_value": float(
                        m.get("onsite_web_add_to_cart_value") or 0
                    ),
                    "onsite_web_checkout_value": float(
                        m.get("onsite_web_checkout_value") or 0
                    ),
                    "onsite_web_purchase_value": float(
                        m.get("onsite_web_purchase_value") or 0
                    ),
                }
            )

        df = pd.DataFrame(rows)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
        return df

    def _build_result(
        self,
        evaluations: list[AdEvaluation],
        threshold: float,
        dry_run: bool,
    ) -> RuleResult:
        """构建最终结果"""
        actions = []
        reasons = []
        notes = []

        # 分类广告
        stop_ads = [e for e in evaluations if e.stop_probability >= threshold]
        watch_ads = [
            e for e in evaluations if 0.5 <= e.stop_probability < threshold
        ]
        good_ads = [e for e in evaluations if e.stop_probability < 0.5]

        # 汇总指标
        total_metrics = {
            "total_ads_evaluated": len(evaluations),
            "stop_recommended": len(stop_ads),
            "watch_recommended": len(watch_ads),
            "good_performance": len(good_ads),
            "evaluations": [
                {
                    "ad_id": e.ad_id,
                    "ad_name": e.ad_name,
                    "stop_probability": e.stop_probability,
                    "optimal_budget_ratio": e.optimal_budget_ratio,
                    "recommendation": e.recommendation,
                    "metrics": e.metrics,
                }
                for e in evaluations
            ],
        }

        # 生成建议
        if stop_ads:
            reasons.append(f"❌ 建议停止的广告: {len(stop_ads)} 个")
            for e in stop_ads:
                ad_label = f"{e.ad_name or e.ad_id}"
                reasons.append(
                    f"  - {ad_label}: 停止概率 {e.stop_probability:.1%}, {e.recommendation}"
                )
                if not dry_run:
                    actions.append(
                        {
                            "action": "pause_ad",
                            "entity_type": "ad",
                            "entity_id": e.ad_id,
                            "confidence": e.stop_probability,
                            "reason": e.recommendation,
                        }
                    )

        if watch_ads:
            reasons.append(f"⚠️ 需要观察的广告: {len(watch_ads)} 个")
            for e in watch_ads:
                ad_label = f"{e.ad_name or e.ad_id}"
                reasons.append(
                    f"  - {ad_label}: 停止概率 {e.stop_probability:.1%}, {e.recommendation}"
                )

        if good_ads:
            reasons.append(f"✅ 表现良好的广告: {len(good_ads)} 个")
            for e in good_ads:
                ad_label = f"{e.ad_name or e.ad_id}"
                reasons.append(
                    f"  - {ad_label}: 停止概率 {e.stop_probability:.1%}, {e.recommendation}"
                )

        # 确定决策
        if stop_ads:
            if dry_run:
                decision = "stop_recommended"
                notes.append(f"[试运行模式] 建议停止 {len(stop_ads)} 个广告")
            else:
                decision = "stop_executed"
        elif watch_ads:
            decision = "continue"
            notes.append(f"有 {len(watch_ads)} 个广告需要密切监控")
        else:
            decision = "continue"

        return RuleResult(
            decision=decision,
            actions=actions,
            reasons=reasons,
            metrics=total_metrics,
            notes=notes,
        )
