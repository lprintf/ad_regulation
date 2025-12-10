"""
ML自动停止规则：基于机器学习模型预测广告停止概率，自动评估广告表现
使用 HistGradientBoostingClassifier 模型，结合历史表现数据进行智能决策。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, ClassVar

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@register_rule
class MLAutoStopRule(RuleBase):
    """ML 自动停止规则"""

    name: ClassVar[str] = "ml_auto_stop"
    description: ClassVar[str] = "基于 ML 模型预测广告停止概率，自动评估广告表现"
    version: ClassVar[str] = "2.0.0"
    tags: ClassVar[list[str]] = ["ml", "auto_stop", "prediction"]

    parameters_schema: ClassVar[dict[str, Any]] = {
        "evaluation_date": {
            "type": "string",
            "label": "评估日期",
            "description": "规则评估的时间点，格式：YYYY-MM-DD",
            "default": "",
            "required": False,
            "hint": "留空使用当前日期；填入历史日期可验证规则在该时间点的表现",
        },
        "lookback_days": {
            "type": "integer",
            "default": 14,
            "label": "数据回溯天数",
            "description": "从评估日期往前回溯的天数用于特征构建",
            "min": 7,
            "max": 30,
            "unit": "天",
            "hint": "建议7-30天，用于计算lag特征和趋势",
        },
        "stop_probability_threshold": {
            "type": "number",
            "default": 0.7,
            "label": "停止概率阈值",
            "description": "模型预测的停止概率超过此阈值时建议暂停广告",
            "min": 0.5,
            "max": 0.95,
            "step": 0.05,
            "unit": "probability",
            "hint": "0.7表示70%的概率应该停止广告",
        },
        "dry_run": {
            "type": "boolean",
            "default": True,
            "label": "试运行模式",
            "description": "启用后仅输出建议，不自动执行操作",
            "hint": "建议先启用试运行模式测试规则效果",
        },
    }

    async def evaluate(self) -> RuleResult:
        """执行 ML 预测评估"""
        import numpy as np
        import pandas as pd

        from api.services.insights_service import InsightsService
        from baseline.data_build import build_features, clean_data
        from baseline.train_tools import load_model
        from utils.db import AdEntityNamesDocument

        # 验证 binding
        if not self.binding:
            return RuleResult(decision="error", reasons=["No binding provided"])

        ad_account_id = self.binding.ad_account_id
        if not ad_account_id:
            return RuleResult(decision="error", reasons=["Missing ad_account_id in binding"])

        ad_id = self.binding.entity_id

        # 获取参数
        lookback_days = self.get_param("lookback_days", 10)
        threshold = self.get_param("stop_probability_threshold", 0.7)
        dry_run = self.get_param("dry_run", True)

        # 确定评估日期
        eval_date_str = self.get_param("evaluation_date")
        if eval_date_str:
            try:
                reference_date = datetime.strptime(eval_date_str, "%Y-%m-%d")
            except ValueError:
                reference_date = datetime.utcnow()
        else:
            reference_date = datetime.utcnow()

        since = reference_date - timedelta(days=lookback_days)
        since_str = since.strftime("%Y-%m-%d")
        until_str = reference_date.strftime("%Y-%m-%d")

        # 获取广告名称
        ad_entity = await AdEntityNamesDocument.find_one(
            AdEntityNamesDocument.account_id == ad_account_id,
            AdEntityNamesDocument.entity_type == "ad",
            AdEntityNamesDocument.entity_id == ad_id,
        )
        ad_name = ad_entity.entity_name if ad_entity else None

        self.log(f"Ad ID: {ad_id}, Name: {ad_name}")
        self.log(f"Evaluation Window: {since_str} to {until_str} ({lookback_days} days)")
        self.log(f"Threshold: Stop Probability > {threshold:.2%}")
        self.log(f"Dry Run Mode: {'ON' if dry_run else 'OFF'}")

        # 直接调用 InsightsService 获取数据
        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=since_str,
                until=until_str,
                level="ad",
                time_increment=1,
                object_ids=[ad_id],
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
                notes=["Cannot evaluate - no historical data"],
            )

        # 聚合指标（用于展示）
        total_spend = sum(float(r.get("metrics", {}).get("spend") or 0) for r in insights_records)
        total_clicks = sum(int(r.get("metrics", {}).get("clicks") or 0) for r in insights_records)
        total_impressions = sum(int(r.get("metrics", {}).get("impressions") or 0) for r in insights_records)
        ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0

        metrics = {
            "spend": total_spend,
            "clicks": total_clicks,
            "impressions": total_impressions,
            "ctr": ctr,
        }

        self.log(f"Metrics - Spend: ${total_spend:.2f}, Clicks: {total_clicks}, CTR: {ctr:.2f}%")

        # 检查模型文件
        model_path = "models/model.feather"
        if not os.path.exists(model_path):
            self.log(f"Model not found: {model_path}", "ERROR")
            return RuleResult(
                decision="error",
                reasons=[f"ML model not found: {model_path}"],
                notes=["Train a model first using baseline/train_tools.py"],
                metrics=metrics,
            )

        # 构建 DataFrame
        df = self._build_dataframe(insights_records, ad_id)
        if df.empty:
            self.log("Empty dataframe after building", "WARNING")
            return RuleResult(
                decision="skip",
                reasons=["Insufficient data for ML prediction"],
                metrics=metrics,
            )

        # 清洗数据
        try:
            df_clean = clean_data(df)
            if df_clean.empty:
                self.log("No valid data after cleaning", "WARNING")
                return RuleResult(
                    decision="skip",
                    reasons=["Insufficient data after cleaning (low spend or samples)"],
                    metrics=metrics,
                )
        except Exception as exc:
            self.log(f"Data cleaning failed: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Data cleaning failed: {exc}"], metrics=metrics)

        # 构建特征
        try:
            features = build_features(df_clean, iloc_index=-1)
            if features.empty:
                self.log("Failed to build features", "WARNING")
                return RuleResult(
                    decision="skip",
                    reasons=["Failed to build features (insufficient historical data)"],
                    metrics=metrics,
                )
        except Exception as exc:
            self.log(f"Feature building failed: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"Feature building failed: {exc}"], metrics=metrics)

        # 加载模型并预测
        try:
            model_package = load_model(model_path)

            if isinstance(model_package, dict) and "model" in model_package:
                model = model_package["model"]
                saved_feature_names = model_package.get("feature_names", [])
                self.log(f"Loaded model with {len(saved_feature_names)} saved feature names")
            else:
                model = model_package
                saved_feature_names = []
                self.log("Loaded model without feature names (old format)", "WARNING")

            # 准备特征
            if saved_feature_names:
                available = set(features.columns)
                missing = [f for f in saved_feature_names if f not in available]
                if missing:
                    self.log(f"Missing {len(missing)} features: {missing[:5]}", "ERROR")
                    return RuleResult(
                        decision="error",
                        reasons=[f"Missing {len(missing)} features required by model"],
                        metrics=metrics,
                    )
                X = features[saved_feature_names].fillna(0)
            else:
                feature_cols = [c for c in features.columns if c not in ["ad_id", "date"]]
                X = features[feature_cols].fillna(0)

            # 预测
            stop_proba = float(model.predict_proba(X)[0, 1])
            self.log(f"ML Prediction: stop_probability={stop_proba:.2%}")

            # 获取特征重要性
            feature_importance = {}
            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                used_features = saved_feature_names if saved_feature_names else feature_cols
                top_indices = np.argsort(importances)[::-1][:10]
                for idx in top_indices:
                    if idx < len(used_features):
                        feature_importance[used_features[idx]] = float(importances[idx])

            if feature_importance:
                self.log("Top features: " + ", ".join(f"{k}={v:.4f}" for k, v in list(feature_importance.items())[:5]))

        except Exception as exc:
            self.log(f"ML prediction failed: {exc}", "ERROR")
            return RuleResult(decision="error", reasons=[f"ML prediction failed: {exc}"], metrics=metrics)

        # 更新 metrics
        metrics["ml_stop_probability"] = stop_proba
        metrics["ml_features_count"] = len(saved_feature_names) if saved_feature_names else len(feature_cols)

        # 决策逻辑
        actions = []
        reasons = []
        notes = []

        # 性能评级
        if stop_proba < 0.2:
            level, emoji = "优秀", "🌟"
        elif stop_proba < 0.4:
            level, emoji = "良好", "✅"
        elif stop_proba < 0.6:
            level, emoji = "一般", "⚠️"
        else:
            level, emoji = "较差", "❌"

        if stop_proba >= threshold:
            severity = "high" if stop_proba >= 0.85 else "medium"

            if not dry_run:
                actions.append({
                    "action": "pause_ad",
                    "entity_type": "ad",
                    "entity_id": ad_id,
                    "severity": severity,
                    "confidence": stop_proba,
                    "reason": f"ML model predicts {stop_proba:.1%} probability of underperformance",
                })
                self.log(f"ACTION: Will pause ad (severity={severity}, confidence={stop_proba:.1%})")
            else:
                self.log(f"DRY RUN: Would pause ad (severity={severity}, confidence={stop_proba:.1%})")
                notes.append(f"[试运行模式] 建议暂停广告（停止概率 {stop_proba:.1%}）")

            reasons.append(f"{emoji} 性能评级：{level}")
            reasons.append(f"📊 ML模型停止概率：{stop_proba:.1%}（阈值：{threshold:.1%}）")
            reasons.append(f"🔍 基于{metrics['ml_features_count']}个特征的综合分析")

            if feature_importance:
                top_features = list(feature_importance.keys())[:3]
                reasons.append(f"🎯 关键影响因素：{', '.join(top_features)}")

            decision = "stop_recommended" if dry_run else "stop_executed"
        else:
            self.log(f"CONTINUE: Stop probability {stop_proba:.1%} below threshold")

            reasons.append(f"{emoji} 性能评级：{level}")
            reasons.append(f"📊 ML模型停止概率：{stop_proba:.1%}（低于阈值 {threshold:.1%}）")

            if stop_proba < 0.1:
                reasons.append("✨ 建议：广告表现优异，建议继续当前投放策略")
            elif stop_proba < 0.3:
                reasons.append("👍 建议：广告表现良好，可考虑适度增加预算")
            else:
                reasons.append("⚠️ 建议：表现一般，建议密切监控关键指标变化")

            decision = "continue"

        return RuleResult(
            decision=decision,
            actions=actions,
            reasons=reasons,
            metrics=metrics,
            notes=notes,
        )

    def _build_dataframe(self, records: list[dict], ad_id: str):
        """将 insights 记录转换为 DataFrame"""
        import pandas as pd

        rows = []
        for record in records:
            m = record.get("metrics", {})
            rows.append({
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
                "onsite_web_add_to_cart_value": float(m.get("onsite_web_add_to_cart_value") or 0),
                "onsite_web_checkout_value": float(m.get("onsite_web_checkout_value") or 0),
                "onsite_web_purchase_value": float(m.get("onsite_web_purchase_value") or 0),
            })
        return pd.DataFrame(rows)
