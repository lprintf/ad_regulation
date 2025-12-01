"""
ML模型预测规则：基于历史数据训练的机器学习模型预测广告是否应该停止
使用 HistGradientBoostingClassifier 评估广告表现，输出停止概率和建议。
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
    Evaluate ad using ML model predictions.

    The model uses features like:
    - Lag features (spend, ROAS, CTR, CPC from last 1-7 days)
    - Decay-weighted averages
    - Trends and momentum
    - Volatility metrics
    """
    performance = context.get("performance", {}) or {}
    ad_meta = context.get("ad", {}) or {}

    # Extract parameters
    stop_probability_threshold = params.get("stop_probability_threshold", 0.7)
    dry_run = params.get("dry_run", True)

    # Get metrics from context
    spend = float(performance.get("spend") or 0.0)
    clicks = int(performance.get("clicks") or 0)
    impressions = int(performance.get("impressions") or 0)
    ctr = float(performance.get("ctr") or 0.0)
    window = performance.get("window", {})

    logger.info(f"========== ML Rule Evaluation Start ==========")
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

    # TODO: Call ML prediction service
    # For now, this is a placeholder that would integrate with:
    # - api/services/prediction_service.py
    # - baseline/train_tools.py (model training)
    #
    # The actual implementation would:
    # 1. Build features from daily_samples in performance data
    # 2. Load the trained model
    # 3. Get prediction probability
    # 4. Compare with threshold

    logger.warning("⚠️ ML model prediction not yet implemented in rule context")
    logger.info("This rule requires integration with PredictionService")

    # Placeholder logic - would be replaced with actual ML prediction
    pred_proba = 0.0  # Would come from model.predict_proba()

    logger.info(f"---------- ML Model Prediction ----------")
    logger.info(f"Predicted Stop Probability: {pred_proba:.2%}")

    if pred_proba > stop_probability_threshold:
        logger.warning(f"⚠️ Model recommends stopping (probability: {pred_proba:.2%} > {stop_probability_threshold:.2%})")

        action_message = f"❗ ML Model recommends pausing (stop probability: {pred_proba:.2%})" if dry_run else f"⚠️ Pausing ad based on ML prediction"
        actions.append({
            "action": "pause_ad" if not dry_run else "no_change",
            "type": "recommendation" if dry_run else "auto_execute",
            "severity": "high",
            "reason": f"ML model predicts {pred_proba:.2%} probability of needing to stop",
        })
        reasons.append(f"ML stop probability {pred_proba:.2%} exceeds threshold {stop_probability_threshold:.2%}")
        notes.append(action_message)

        logger.info(f"========== ML Rule Evaluation End: PAUSE RECOMMENDED ==========")
    else:
        logger.info(f"✅ Model prediction within acceptable range")
        logger.info(f"========== ML Rule Evaluation End: CONTINUE ==========")

        actions.append({
            "action": "no_change",
            "type": "informational",
            "message": "ML model suggests continuing",
        })
        reasons.append(f"ML stop probability {pred_proba:.2%} below threshold {stop_probability_threshold:.2%}")
        notes.append(f"✅ ML model prediction: continue running (stop probability: {pred_proba:.2%})")

    return {
        "actions": actions,
        "reasons": reasons,
        "metrics": {
            **metrics,
            "ml_stop_probability": pred_proba,
            "ml_threshold": stop_probability_threshold,
        },
        "notes": notes,
    }
