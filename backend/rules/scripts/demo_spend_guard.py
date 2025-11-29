"""
演示规则：素材测试规则（花费守卫）
当广告花费达到阈值后，评估 CTR 和 CPC 是否达标，未达标时建议暂停。
"""

from typing import Any, Dict

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
        "default": 14,
        "label": "数据回溯天数",
        "description": "从评估日期往前回溯的天数",
        "min": 7,
        "max": 30,
        "unit": "天",
        "hint": "建议7-30天",
    },
    "spend_threshold": {
        "type": "number",
        "default": 3.0,
        "unit": "USD",
        "label": "最低花费阈值",
        "description": "达到此花费后才开始评估",
        "min": 0.1,
        "max": 1000.0,
        "step": 0.1,
        "hint": "低于此花费的广告将跳过评估",
    },
    "north_america_cpc_threshold": {
        "type": "number",
        "default": 3.0,
        "unit": "USD",
        "label": "北美 CPC 阈值",
        "description": "北美地区的最大可接受 CPC",
        "min": 0.1,
        "max": 100.0,
        "step": 0.1,
    },
    "rest_of_world_cpc_threshold": {
        "type": "number",
        "default": 1.5,
        "unit": "USD",
        "label": "其他地区 CPC 阈值",
        "description": "非北美地区的最大可接受 CPC",
        "min": 0.1,
        "max": 100.0,
        "step": 0.1,
    },
    "ctr_threshold": {
        "type": "number",
        "default": 1.0,
        "unit": "percent",
        "label": "最低 CTR 阈值",
        "description": "最小可接受的点击率（百分比）",
        "min": 0.01,
        "max": 100.0,
        "step": 0.01,
        "hint": "例如：1.0 表示 1%",
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
    """Evaluate ad performance based on spend, CTR, and CPC thresholds."""
    performance = context.get("performance", {}) or {}
    targeting = context.get("targeting", {}) or {}
    ad_meta = context.get("ad", {}) or {}

    # Extract parameters with defaults
    spend_threshold = params.get("spend_threshold", 3.0)
    ctr_threshold = params.get("ctr_threshold", 1.0)
    north_america_cpc_threshold = params.get("north_america_cpc_threshold", 3.0)
    rest_of_world_cpc_threshold = params.get("rest_of_world_cpc_threshold", 1.5)
    dry_run = params.get("dry_run", True)

    spend = float(performance.get("spend") or 0.0)
    clicks = int(performance.get("clicks") or 0)
    impressions = int(performance.get("impressions") or 0)
    ctr = float(performance.get("ctr") or 0.0)
    cpc = performance.get("cpc")
    window = performance.get("window", {})

    countries = targeting.get("countries", [])
    primary_segment = "north_america" if any(c in ["US", "CA"] for c in countries) else "rest_of_world"
    cpc_threshold = north_america_cpc_threshold if primary_segment == "north_america" else rest_of_world_cpc_threshold

    # Log evaluation start
    logger.info(f"========== Rule Evaluation Start ==========")
    logger.info(f"Ad ID: {ad_meta.get('ad_id')}, Name: {ad_meta.get('name')}")
    logger.info(f"Evaluation Window: {window.get('since')} to {window.get('until')} ({window.get('days')} days)")
    logger.info(f"Raw Metrics - Spend: ${spend:.2f}, Clicks: {clicks}, Impressions: {impressions}, CTR: {ctr:.2f}%")

    # Log targeting info
    logger.info(f"Targeting Countries: {', '.join(countries) if countries else 'Unknown'}")
    logger.info(f"Primary Segment: {primary_segment}")
    logger.info(f"Applied Thresholds - Spend: ${spend_threshold:.2f}, CTR: {ctr_threshold:.2f}%, CPC: ${cpc_threshold:.2f}")
    logger.info(f"Dry Run Mode: {'ON (recommendations only)' if dry_run else 'OFF (will auto-execute)'}")

    actions = []
    reasons = []
    metrics = {
        "spend": spend,
        "ctr": ctr,
        "cpc": cpc if cpc is not None else 0,
        "clicks": clicks,
        "impressions": impressions,
    }
    notes = []

    # ========== Decision Node 1: Check Spend Threshold ==========
    logger.info(f"---------- Decision Node 1: Spend Threshold Check ----------")
    logger.info(f"Current Spend: ${spend:.2f}, Required Threshold: ${spend_threshold:.2f}")

    if spend < spend_threshold:
        logger.warning(f"❌ Spend below threshold - skipping evaluation")
        logger.info(f"========== Rule Evaluation End: SKIPPED (Insufficient Spend) ==========")
        return {
            "actions": [{"type": "informational", "message": "Spend below threshold"}],
            "reasons": [f"Spend ${spend:.2f} < threshold ${spend_threshold:.2f}"],
            "metrics": metrics,
            "notes": ["Skipped evaluation - insufficient spend"],
        }

    logger.info(f"✅ Spend threshold met - proceeding with evaluation")

    # ========== Decision Node 2: Check Clicks ==========
    logger.info(f"---------- Decision Node 2: Clicks Check ----------")
    logger.info(f"Total Clicks: {clicks}")

    if clicks == 0:
        logger.warning(f"❌ No clicks detected after spending ${spend:.2f}")
        logger.info(f"📋 Recommendation: PAUSE AD (no clicks after spend)")

        action_message = "❗ Recommend pausing (no clicks after spend)" if dry_run else "⚠️ Pausing ad (no clicks)"
        actions.append({
            "action": "pause_ad" if not dry_run else "no_change",
            "type": "recommendation" if dry_run else "auto_execute",
            "severity": "high",
            "reason": f"No clicks after ${spend:.2f} spend",
        })
        reasons.append(f"No clicks detected (spend: ${spend:.2f})")
        notes.append(action_message)

        logger.info(f"========== Rule Evaluation End: PAUSE RECOMMENDED (No Clicks) ==========")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
        }

    logger.info(f"✅ Clicks detected - proceeding with performance check")

    # ========== Decision Node 3: Performance Evaluation ==========
    logger.info(f"---------- Decision Node 3: Performance Evaluation ----------")
    logger.info(f"CTR Evaluation: {ctr:.2f}% vs threshold {ctr_threshold:.2f}%")
    logger.info(f"CPC Evaluation: ${(cpc if cpc is not None else 0):.2f} vs threshold ${cpc_threshold:.2f}")

    meets_ctr = ctr > ctr_threshold
    meets_cpc = cpc is not None and cpc < cpc_threshold

    logger.info(f"CTR Check: {'✅ PASS' if meets_ctr else '❌ FAIL'} ({ctr:.2f}% {'>' if meets_ctr else '<='} {ctr_threshold:.2f}%)")
    logger.info(f"CPC Check: {'✅ PASS' if meets_cpc else '❌ FAIL'} (${(cpc if cpc is not None else 0):.2f} {'<' if meets_cpc else '>='} ${cpc_threshold:.2f})")

    if meets_ctr and meets_cpc:
        logger.info(f"✅ Performance meets all thresholds - no action needed")
        logger.info(f"========== Rule Evaluation End: PERFORMANCE OK ==========")

        actions.append({
            "action": "no_change",
            "type": "informational",
            "message": "Performance within acceptable range",
        })
        reasons.append("CTR and CPC both meet thresholds")
        notes.append("✅ Ad performance is healthy - continue running")
    else:
        logger.warning(f"⚠️ Performance below thresholds - pause recommended")
        logger.info(f"📋 Recommendation: PAUSE AD (performance below threshold)")

        failure_reasons = []
        if not meets_ctr:
            failure_reasons.append(f"CTR {ctr:.2f}% < {ctr_threshold:.2f}%")
            logger.warning(f"  - CTR too low: {ctr:.2f}% (threshold: {ctr_threshold:.2f}%)")
        if not meets_cpc:
            failure_reasons.append(f"CPC ${cpc:.2f} > ${cpc_threshold:.2f}")
            logger.warning(f"  - CPC too high: ${cpc:.2f} (threshold: ${cpc_threshold:.2f})")

        action_message = f"❗ Recommend pausing ({', '.join(failure_reasons)})" if dry_run else f"⚠️ Pausing ad ({', '.join(failure_reasons)})"
        actions.append({
            "action": "pause_ad" if not dry_run else "no_change",
            "type": "recommendation" if dry_run else "auto_execute",
            "severity": "medium",
            "reason": "; ".join(failure_reasons),
        })
        reasons.extend(failure_reasons)
        notes.append(action_message)

        logger.info(f"========== Rule Evaluation End: PAUSE RECOMMENDED ==========")

    return {
        "actions": actions,
        "reasons": reasons,
        "metrics": metrics,
        "notes": notes,
    }
