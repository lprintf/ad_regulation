"""
Demo rule script: creative spend guard.
Evaluates recent performance metrics and recommends pausing if thresholds not met.
"""

from __future__ import annotations

from typing import Any, Dict, List


def evaluate(context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    performance = context.get("performance", {}) or {}
    targeting = context.get("targeting", {}) or {}
    ad_meta = context.get("ad", {}) or {}

    spend = float(performance.get("spend") or 0.0)
    clicks = int(performance.get("clicks") or 0)
    impressions = int(performance.get("impressions") or 0)
    ctr = float(performance.get("ctr") or 0.0)
    cpc = performance.get("cpc")
    window = performance.get("window", {})

    countries: List[str] = [
        str(code).upper() for code in targeting.get("countries", []) if code
    ]
    primary_segment = "north_america" if any(
        code in {"US", "CA"} for code in countries
    ) else "rest_of_world"

    ctr_threshold = 1.0  # percent
    cpc_threshold = 3.0 if primary_segment == "north_america" else 1.5

    actions: List[Dict[str, Any]] = []
    reasons: List[str] = []
    notes: List[str] = []

    metrics = {
        "spend": spend,
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "ctr_threshold": ctr_threshold,
        "cpc": cpc,
        "cpc_threshold": cpc_threshold,
        "evaluation_window": window,
        "countries": countries,
        "primary_segment": primary_segment,
        "ad_id": ad_meta.get("ad_id"),
    }

    if spend < 3.0:
        reasons.append("Spend has not reached the USD 3 evaluation threshold.")
        notes.append("Rule exits early without recommendations.")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
        }

    if clicks == 0:
        reasons.append("Spend reached threshold but clicks remain zero.")
        actions.append(
            {
                "type": "recommendation",
                "action": "pause_ad",
                "reason": "no_clicks_after_spend",
                "severity": "high",
                "auto_execute": False,
            }
        )
        notes.append("Manual review recommended before pausing.")
        return {
            "actions": actions,
            "reasons": reasons,
            "metrics": metrics,
            "notes": notes,
        }

    if cpc is None:
        cpc = spend / clicks if clicks else None
        metrics["cpc"] = cpc

    meets_ctr = ctr > ctr_threshold
    meets_cpc = cpc is not None and cpc < cpc_threshold

    if meets_ctr and meets_cpc:
        reasons.append("Performance meets segment thresholds; keep running.")
        actions.append(
            {
                "type": "informational",
                "action": "no_change",
                "reason": "performance_ok",
                "auto_execute": False,
            }
        )
    else:
        reasons.append(
            "Performance below thresholds; recommend pausing for manual confirmation."
        )
        actions.append(
            {
                "type": "recommendation",
                "action": "pause_ad",
                "reason": "performance_below_threshold",
                "details": {
                    "meets_ctr": meets_ctr,
                    "meets_cpc": meets_cpc,
                },
                "auto_execute": False,
                "severity": "medium",
            }
        )
        notes.append(
            "No automatic ad control is performed; follow up manually in Ads Manager."
        )

    return {
        "actions": actions,
        "reasons": reasons,
        "metrics": metrics,
        "notes": notes,
    }
