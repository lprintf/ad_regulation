"""
ML自动停止规则：基于机器学习模型预测广告停止概率，自动评估广告表现
使用 HistGradientBoostingClassifier 模型，结合历史表现数据进行智能决策。
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

PARAMETERS_SCHEMA = {
    "evaluation_date": {
        "type": "string",
        "label": "评估日期",
        "description": "规则评估的时间点，格式：YYYY-MM-DD",
        "default": "",
        "required": False,
        "hint": "留空使用当前日期；填入历史日期可验证规则在该时间点的表现"
    },
    "lookback_days": {
        "type": "integer",
        "default": 10,
        "label": "数据回溯天数",
        "description": "从评估日期往前回溯的天数用于特征构建",
        "min": 7,
        "max": 30,
        "unit": "天",
        "hint": "建议7-30天，用于计算lag特征和趋势",
    },
    "enable_ml_prediction": {
        "type": "boolean",
        "default": True,
        "label": "启用ML预测",
        "description": "开启后系统会自动计算ML模型预测概率",
        "hint": "需要训练好的模型文件（models/model.feather）",
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


def evaluate(context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    使用ML模型预测评估广告是否应该停止。

    模型基于以下特征：
    - Lag特征（过去1-7天的spend、ROAS、CTR、CPC）
    - 衰减加权平均
    - 趋势和动量指标
    - 波动率指标
    """
    performance = context.get("performance", {}) or {}
    ad_meta = context.get("ad", {}) or {}
    ml_prediction = context.get("ml_prediction") or {}

    # 提取参数
    stop_probability_threshold = params.get("stop_probability_threshold", 0.7)
    dry_run = params.get("dry_run", True)
    enable_ml = params.get("enable_ml_prediction", True)

    # 获取指标
    spend = float(performance.get("spend") or 0.0)
    clicks = int(performance.get("clicks") or 0)
    impressions = int(performance.get("impressions") or 0)
    ctr = float(performance.get("ctr") or 0.0)
    window = performance.get("window", {})

    logger.info(f"========== ML Auto-Stop Rule Evaluation ==========")
    logger.info(f"Ad ID: {ad_meta.get('ad_id')}, Name: {ad_meta.get('name')}")
    logger.info(f"Evaluation Window: {window.get('since')} to {window.get('until')} ({window.get('days')} days)")
    logger.info(f"Metrics - Spend: ${spend:.2f}, Clicks: {clicks}, Impressions: {impressions}, CTR: {ctr:.2f}%")
    logger.info(f"Threshold: Stop Probability > {stop_probability_threshold:.2%}")
    logger.info(f"Dry Run Mode: {'ON (recommendations only)' if dry_run else 'OFF (will auto-execute)'}")

    actions = []
    reasons = []
    metrics = {
        "spend": spend,
        "ctr": ctr,
        "clicks": clicks,
        "impressions": impressions,
    }
    notes = []

    # 检查ML预测是否可用
    if not enable_ml:
        logger.info("[ML DISABLED] enable_ml_prediction=False, skipping ML evaluation")
        reasons.append("ML prediction disabled by parameter")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
            "decision": "skip",
        }

    if not ml_prediction:
        logger.warning("[ML UNAVAILABLE] No ML prediction data in context")
        reasons.append("ML prediction data not available in context")
        reasons.append("Set enable_ml_prediction=True in params to enable ML")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
            "decision": "skip",
        }

    if not ml_prediction.get("available"):
        error_msg = ml_prediction.get("error", "Unknown error")
        logger.warning(f"[ML ERROR] {error_msg}")
        reasons.append(f"ML prediction failed: {error_msg}")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
            "decision": "error",
        }

    # 获取ML预测结果
    stop_proba = ml_prediction.get("stop_probability", 0.0)
    features_used = ml_prediction.get("features_used", 0)
    feature_importance = ml_prediction.get("feature_importance", {})

    logger.info(f"[ML RESULT] Stop Probability: {stop_proba:.2%} (threshold: {stop_probability_threshold:.2%})")
    logger.info(f"[ML INFO] Features Used: {features_used}, Model: {ml_prediction.get('model_path')}")

    # 记录最重要的特征
    if feature_importance:
        logger.info("[FEATURE IMPORTANCE] Top factors:")
        for feature, importance in list(feature_importance.items())[:5]:
            logger.info(f"  - {feature}: {importance:.4f}")

    # 决策逻辑
    metrics["ml_stop_probability"] = stop_proba
    metrics["ml_features_count"] = features_used

    # 性能评级
    if stop_proba < 0.2:
        performance_level = "优秀"
        performance_emoji = "🌟"
    elif stop_proba < 0.4:
        performance_level = "良好"
        performance_emoji = "✅"
    elif stop_proba < 0.6:
        performance_level = "一般"
        performance_emoji = "⚠️"
    else:
        performance_level = "较差"
        performance_emoji = "❌"

    if stop_proba >= stop_probability_threshold:
        # 高概率需要停止
        severity = "high" if stop_proba >= 0.85 else "medium"

        action = {
            "action": "pause_ad",
            "entity_type": "ad",
            "entity_id": ad_meta.get("ad_id"),
            "severity": severity,
            "confidence": float(stop_proba),
            "reason": f"ML model predicts {stop_proba:.1%} probability of underperformance",
        }

        if not dry_run:
            actions.append(action)
            logger.info(f"[ACTION] Will pause ad (severity={severity}, confidence={stop_proba:.1%})")
        else:
            logger.info(f"[DRY RUN] Would pause ad (severity={severity}, confidence={stop_proba:.1%})")
            notes.append(f"[试运行模式] 建议暂停广告（停止概率 {stop_proba:.1%}）")

        reasons.append(f"{performance_emoji} 性能评级：{performance_level}")
        reasons.append(f"📊 ML模型停止概率：{stop_proba:.1%}（阈值：{stop_probability_threshold:.1%}）")
        reasons.append(f"🔍 基于{features_used}个特征的综合分析（包括滞后指标、趋势、波动率）")

        # 添加关键特征说明
        if feature_importance:
            top_features = list(feature_importance.items())[:3]
            top_feature_str = "、".join([f.replace("_", " ").title() for f, _ in top_features])
            reasons.append(f"🎯 关键影响因素：{top_feature_str}")

        decision = "stop_recommended" if dry_run else "stop_executed"

    else:
        # 概率低于阈值，继续投放
        logger.info(f"[CONTINUE] Stop probability {stop_proba:.1%} below threshold, ad should continue")

        reasons.append(f"{performance_emoji} 性能评级：{performance_level}")
        reasons.append(f"📊 ML模型停止概率：{stop_proba:.1%}（远低于阈值 {stop_probability_threshold:.1%}）")

        # 提供具体建议
        if stop_proba < 0.1:
            reasons.append("✨ 建议：广告表现优异，建议继续当前投放策略")
            if ctr > 3.0:
                reasons.append(f"💡 亮点：CTR {ctr:.2f}% 表现优秀，用户互动活跃")
            if spend > 0 and clicks > 100:
                cpc_value = spend / clicks
                if cpc_value < 0.5:
                    reasons.append(f"💰 亮点：CPC ${cpc_value:.2f} 成本控制良好")
        elif stop_proba < 0.3:
            reasons.append("👍 建议：广告表现良好，可考虑适度增加预算测试扩量")
            if feature_importance:
                top_feature = list(feature_importance.keys())[0]
                if "lag" in top_feature:
                    reasons.append(f"📈 近期趋势稳定，建议保持观察")
        else:
            reasons.append("⚠️ 建议：表现一般，建议密切监控关键指标变化")
            if ctr < 2.0:
                reasons.append("💡 优化方向：CTR偏低，考虑优化创意素材或受众定向")

        # 添加关键特征洞察
        if feature_importance:
            top_features = list(feature_importance.items())[:3]
            top_feature_str = "、".join([f.replace("_", " ").title() for f, _ in top_features])
            reasons.append(f"🔍 关键健康指标：{top_feature_str}")

        decision = "continue"

    logger.info(f"========== Evaluation Complete: {decision.upper()} ==========")

    return {
        "actions": actions,
        "reasons": reasons,
        "metrics": metrics,
        "notes": notes,
        "decision": decision,
    }
