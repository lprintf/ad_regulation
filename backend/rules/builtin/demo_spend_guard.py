"""
演示规则：素材测试规则（花费守卫）
当广告花费达到阈值后，评估 CTR 和 CPC 是否达标，未达标时建议暂停。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, ClassVar

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@register_rule
class DemoSpendGuardRule(RuleBase):
    """素材测试规则 - 花费守卫"""

    name: ClassVar[str] = "demo_spend_guard"
    description: ClassVar[str] = "素材测试规则：花费≥阈值时评估CPC/CTR，未达标建议暂停"
    version: ClassVar[str] = "2.0.0"
    tags: ClassVar[list[str]] = ["demo", "spend_guard", "creative"]

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

    async def evaluate(self) -> RuleResult:
        """评估广告表现"""
        from api.services.insights_service import InsightsService
        from facebook_business.adobjects.ad import Ad
        from utils.db import AdEntityNamesDocument
        from utils.fb_api_flyweight_factory import get_api

        # 验证 binding
        if not self.binding:
            return RuleResult(decision="error", reasons=["No binding provided"])

        ad_account_id = self.binding.ad_account_id
        if not ad_account_id:
            return RuleResult(decision="error", reasons=["Missing ad_account_id in binding"])

        ad_id = self.binding.entity_id

        # 获取参数
        lookback_days = self.get_param("lookback_days", 14)
        spend_threshold = self.get_param("spend_threshold", 3.0)
        ctr_threshold = self.get_param("ctr_threshold", 1.0)
        north_america_cpc_threshold = self.get_param("north_america_cpc_threshold", 3.0)
        rest_of_world_cpc_threshold = self.get_param("rest_of_world_cpc_threshold", 1.5)
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

        # 聚合指标
        total_spend = sum(float(r.get("metrics", {}).get("spend") or 0) for r in insights_records)
        total_clicks = sum(int(r.get("metrics", {}).get("clicks") or 0) for r in insights_records)
        total_impressions = sum(int(r.get("metrics", {}).get("impressions") or 0) for r in insights_records)

        ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0
        cpc = (total_spend / total_clicks) if total_clicks else None

        metrics = {
            "spend": total_spend,
            "clicks": total_clicks,
            "impressions": total_impressions,
            "ctr": ctr,
            "cpc": cpc if cpc is not None else 0,
        }

        self.log(f"Metrics - Spend: ${total_spend:.2f}, Clicks: {total_clicks}, CTR: {ctr:.2f}%")
        self.log(f"Thresholds - Spend: ${spend_threshold:.2f}, CTR: {ctr_threshold:.2f}%")
        self.log(f"Dry Run Mode: {'ON' if dry_run else 'OFF'}")

        actions = []
        reasons = []
        notes = []

        # Decision Node 1: Check Spend Threshold
        self.log("---------- Decision Node 1: Spend Threshold Check ----------")
        if total_spend < spend_threshold:
            self.log(f"Spend ${total_spend:.2f} < threshold ${spend_threshold:.2f} - skipping")
            return RuleResult(
                decision="skip",
                actions=[{"type": "informational", "message": "Spend below threshold"}],
                reasons=[f"Spend ${total_spend:.2f} < threshold ${spend_threshold:.2f}"],
                metrics=metrics,
                notes=["Skipped evaluation - insufficient spend"],
            )

        self.log("Spend threshold met - proceeding")

        # Decision Node 2: Check Clicks
        self.log("---------- Decision Node 2: Clicks Check ----------")
        if total_clicks == 0:
            self.log(f"No clicks detected after spending ${total_spend:.2f}", "WARNING")
            action_msg = "Recommend pausing (no clicks)" if dry_run else "Pausing ad (no clicks)"
            actions.append({
                "action": "pause_ad" if not dry_run else "no_change",
                "type": "recommendation" if dry_run else "auto_execute",
                "entity_id": ad_id,
                "severity": "high",
                "reason": f"No clicks after ${total_spend:.2f} spend",
            })
            reasons.append(f"No clicks detected (spend: ${total_spend:.2f})")
            notes.append(action_msg)
            return RuleResult(
                decision="stop_recommended" if dry_run else "stop_executed",
                actions=actions,
                reasons=reasons,
                metrics=metrics,
                notes=notes,
            )

        self.log("Clicks detected - proceeding with performance check")

        # 获取定向国家（直接调用 Facebook API）
        targeting_countries: list[str] = []
        try:
            api = await get_api(ad_account_id)
            ad = Ad(ad_id, api=api)

            def _fetch_targeting() -> list[str]:
                ad_data = ad.api_get(fields=[Ad.Field.targeting])
                targeting = ad_data.get(Ad.Field.targeting) or {}
                countries = targeting.get("geo_locations", {}).get("countries") if isinstance(targeting, dict) else None
                return list(countries or [])

            targeting_countries = await asyncio.to_thread(_fetch_targeting)
        except Exception as exc:
            self.log(f"Failed to fetch targeting: {exc}", "WARNING")

        primary_segment = "north_america" if any(c in ["US", "CA"] for c in targeting_countries) else "rest_of_world"
        cpc_threshold = north_america_cpc_threshold if primary_segment == "north_america" else rest_of_world_cpc_threshold

        self.log(f"Targeting Countries: {', '.join(targeting_countries) if targeting_countries else 'Unknown'}")
        self.log(f"Primary Segment: {primary_segment}, CPC Threshold: ${cpc_threshold:.2f}")

        # Decision Node 3: Performance Evaluation
        self.log("---------- Decision Node 3: Performance Evaluation ----------")
        meets_ctr = ctr > ctr_threshold
        meets_cpc = cpc is not None and cpc < cpc_threshold

        self.log(f"CTR Check: {'PASS' if meets_ctr else 'FAIL'} ({ctr:.2f}% vs {ctr_threshold:.2f}%)")
        self.log(f"CPC Check: {'PASS' if meets_cpc else 'FAIL'} (${cpc or 0:.2f} vs ${cpc_threshold:.2f})")

        if meets_ctr and meets_cpc:
            self.log("Performance meets all thresholds - no action needed")
            return RuleResult(
                decision="continue",
                actions=[{"action": "no_change", "type": "informational", "message": "Performance OK"}],
                reasons=["CTR and CPC both meet thresholds"],
                metrics=metrics,
                notes=["Ad performance is healthy - continue running"],
            )
        else:
            failure_reasons = []
            if not meets_ctr:
                failure_reasons.append(f"CTR {ctr:.2f}% < {ctr_threshold:.2f}%")
            if not meets_cpc:
                failure_reasons.append(f"CPC ${cpc:.2f} > ${cpc_threshold:.2f}")

            self.log(f"Performance below thresholds: {', '.join(failure_reasons)}", "WARNING")

            actions.append({
                "action": "pause_ad" if not dry_run else "no_change",
                "type": "recommendation" if dry_run else "auto_execute",
                "entity_id": ad_id,
                "severity": "medium",
                "reason": "; ".join(failure_reasons),
            })
            reasons.extend(failure_reasons)
            notes.append(f"{'Recommend pausing' if dry_run else 'Pausing ad'} ({', '.join(failure_reasons)})")

            return RuleResult(
                decision="stop_recommended" if dry_run else "stop_executed",
                actions=actions,
                reasons=reasons,
                metrics=metrics,
                notes=notes,
            )
