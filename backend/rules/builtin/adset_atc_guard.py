"""
广告组加购率守卫规则

逻辑：
1. 检查广告组整体加购率（ATC率）
2. 如果 ATC率 >= 阈值（默认5%），继续投放
3. 如果 ATC率 < 阈值：
   - 使用 HHI 分析花费集中度，确定有效广告数
   - 识别"花费多但没加购"的低效广告
   - 关闭低效广告，让表现好的继续跑
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@dataclass
class AdPerformance:
    """单个广告的表现数据"""

    ad_id: str
    ad_name: str | None
    # 评估日当天数据（用于决策）
    spend_today: float
    clicks_today: int
    lpv_today: int
    atc_today: int
    # 7天累计数据（用于趋势分析）
    spend_7d: float
    clicks_7d: int
    lpv_7d: int
    atc_7d: int
    atc_value_7d: float
    impressions_7d: int = 0  # 7天展示次数
    # 计算指标（基于7天数据）
    spend_share: float = 0.0  # 花费占比
    atc_share: float = 0.0  # 加购占比
    atc_rate: float = 0.0  # 加购率
    efficiency_score: float = 0.0  # 效率评分 (atc_share / spend_share)
    ctr: float = 0.0  # 点击率 (clicks / impressions)
    cpm: float = 0.0  # 千次展示成本 (spend / impressions * 1000)
    # 多窗口活跃度分析
    active_windows: dict = None  # {"1d": True, "3d": True, "5d": False, "7d": False}
    daily_spends: list = None  # 每天的花费记录 [(date, spend), ...]
    is_active_today: bool = False  # 评估日当天是否有花费

    def __post_init__(self):
        if self.active_windows is None:
            self.active_windows = {}
        if self.daily_spends is None:
            self.daily_spends = []


@dataclass
class HHIAnalysis:
    """HHI 分析结果"""

    spend_hhi: float  # 花费 HHI
    atc_hhi: float  # 加购 HHI
    effective_ad_count: float  # 有效广告数 (1/HHI)
    concentration_level: str  # 集中度等级


@register_rule
class AdSetATCGuardRule(RuleBase):
    """广告组加购率守卫规则"""

    name: ClassVar[str] = "luopan@adset_atc_guard"
    description: ClassVar[str] = (
        "监控广告组加购率，当低于阈值时自动识别并关闭低效广告素材（罗盼定制）"
    )
    version: ClassVar[str] = "1.0.0"
    tags: ClassVar[list[str]] = ["adset", "atc", "hhi", "creative_optimization"]

    parameters_schema: ClassVar[dict[str, Any]] = {
        "evaluation_date": {
            "type": "string",
            "label": "评估日期",
            "description": "规则评估的时间点，格式：YYYY-MM-DD（留空使用昨天）",
            "default": "",
            "required": False,
            "hint": "通常评估前一天完整数据",
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
            "hint": "默认 5%，即 ATC/LPV < 5% 时触发",
        },
        "min_spend_for_evaluation": {
            "type": "number",
            "default": 10.0,
            "label": "最小花费门槛",
            "description": "广告至少花费多少美元才纳入评估",
            "min": 1.0,
            "max": 100.0,
            "unit": "USD",
            "hint": "花费太少的广告数据不具代表性",
        },
        "efficiency_threshold": {
            "type": "number",
            "default": 0.5,
            "label": "效率阈值",
            "description": "效率分数（ATC占比/花费占比）低于此值视为低效",
            "min": 0.1,
            "max": 1.0,
            "step": 0.1,
            "hint": "效率分数 = ATC占比 / 花费占比，<1 表示低于平均",
        },
        "max_ads_to_pause": {
            "type": "integer",
            "default": 2,
            "label": "单次最多关闭数",
            "description": "单次执行最多关闭几个低效广告",
            "min": 1,
            "max": 5,
            "hint": "避免一次关闭太多，保留测试机会",
        },
        "min_remaining_ads": {
            "type": "integer",
            "default": 2,
            "label": "最少保留广告数",
            "description": "至少保留几个活跃广告",
            "min": 1,
            "max": 5,
            "hint": "即使效率低也要保留一定数量进行测试",
        },
        "dry_run": {
            "type": "boolean",
            "default": True,
            "label": "试运行模式",
            "description": "启用后仅输出建议，不自动执行操作",
        },
    }

    async def evaluate(self) -> RuleResult:
        """执行广告组加购率守卫评估"""
        from api.services.insights_service import InsightsService

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
            # 从广告获取其所属广告组
            adset_id = await self._get_adset_id_from_ad(ad_account_id, entity_id)
            if not adset_id:
                return RuleResult(
                    decision="error",
                    reasons=[f"Cannot get adset_id for ad {entity_id}"],
                )
        else:
            return RuleResult(
                decision="error",
                reasons=[f"Unsupported entity_type: {entity_type}. Use 'adset' or 'ad'"],
            )

        # 获取参数
        atc_threshold = self.get_param("atc_rate_threshold", 0.05)
        min_spend = self.get_param("min_spend_for_evaluation", 10.0)
        efficiency_threshold = self.get_param("efficiency_threshold", 0.5)
        max_pause = self.get_param("max_ads_to_pause", 2)
        min_remaining = self.get_param("min_remaining_ads", 2)
        dry_run = self.get_param("dry_run", True)

        # 确定评估日期（默认昨天）
        eval_date_str = self.get_param("evaluation_date")
        if eval_date_str:
            try:
                eval_date = datetime.strptime(eval_date_str, "%Y-%m-%d")
            except ValueError:
                eval_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        else:
            eval_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)

        date_str = eval_date.strftime("%Y-%m-%d")
        # 7天前的日期，用于趋势分析
        seven_days_ago = eval_date - timedelta(days=6)
        since_str = seven_days_ago.strftime("%Y-%m-%d")

        self.log(f"AdSet ID: {adset_id}")
        self.log(f"Evaluation Date: {date_str}")
        self.log(f"Data Range: {since_str} ~ {date_str} (7 days)")
        self.log(f"ATC Rate Threshold: {atc_threshold:.1%}")
        self.log(f"Dry Run: {'ON' if dry_run else 'OFF'}")

        # 获取 7 天数据用于趋势分析
        # 注意：这里获取的是整个广告账号的数据，后面通过 adset_id 字段过滤
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
            self.log("No insights data available", "WARNING")
            return RuleResult(
                decision="skip",
                reasons=["No insights data for the evaluation date"],
            )

        # 过滤出该广告组的广告
        adset_ads = await self._filter_ads_by_adset(adset_id, insights_records)
        self.log(f"Found {len(adset_ads)} ad-day records for adset {adset_id}")

        if not adset_ads:
            self.log(f"No ads found for adset {adset_id}")
            return RuleResult(
                decision="skip",
                reasons=[f"No ads found in adset {adset_id}"],
            )

        # 分析 7 天数据，构建广告表现
        ad_performances, low_spend_ads = self._build_ad_performances_with_trend(
            adset_ads, min_spend, date_str
        )

        # 记录广告组中的广告情况
        self.log(f"AdSet has {len(ad_performances)} ads, {len(low_spend_ads)} with low spend (< ${min_spend:.2f})")

        # 显示花费不足的广告（帮助投手理解，这些广告可能因预算竞争不足）
        if low_spend_ads:
            self.log(f"Low spend ads (may benefit from pausing inefficient ads):")
            for ad in low_spend_ads:
                self.log(f"  - {ad['ad_name'] or ad['ad_id']}: {ad['note']}")

        if not ad_performances:
            self.log("No ads meet minimum spend threshold")
            return RuleResult(
                decision="skip",
                reasons=[f"No ads with 7-day spend >= ${min_spend:.2f}"],
            )

        # 使用全部7天数据计算广告组整体指标（用于决策）
        total_lpv_7d = sum(ad.lpv_7d for ad in ad_performances)
        total_clicks_7d = sum(ad.clicks_7d for ad in ad_performances)
        total_atc_7d = sum(ad.atc_7d for ad in ad_performances)
        total_spend_7d = sum(ad.spend_7d for ad in ad_performances)

        # 使用 LPV 计算 ATC 率，如果没有 LPV 则用 clicks
        denominator = total_lpv_7d if total_lpv_7d > 0 else total_clicks_7d
        adset_atc_rate = total_atc_7d / denominator if denominator > 0 else 0

        self.log(f"AdSet 7D Total: Spend=${total_spend_7d:.2f}, LPV={total_lpv_7d}, ATC={total_atc_7d}")
        self.log(f"AdSet ATC Rate (7D): {adset_atc_rate:.2%} (threshold: {atc_threshold:.1%})")

        # 计算占比和效率分数（基于7天数据，用于决策）
        self._calculate_shares_and_efficiency(ad_performances, total_spend_7d, total_atc_7d)

        # HHI 分析（基于所有广告）
        hhi_analysis = self._calculate_hhi(ad_performances)
        self.log(
            f"HHI Analysis: Spend HHI={hhi_analysis.spend_hhi:.0f}, "
            f"Effective Ads={hhi_analysis.effective_ad_count:.1f}, "
            f"Concentration={hhi_analysis.concentration_level}"
        )

        # 辅助信息：今天活跃 vs 不活跃的广告（仅用于日志输出）
        active_today = [ad for ad in ad_performances if ad.is_active_today]
        inactive_today = [ad for ad in ad_performances if not ad.is_active_today]
        total_spend_today = sum(ad.spend_today for ad in active_today)
        total_atc_today = sum(ad.atc_today for ad in active_today)

        self.log(f"Today Active: {len(active_today)}, Inactive: {len(inactive_today)}")
        self.log(f"Today Spend: ${total_spend_today:.2f}, ATC: {total_atc_today}")

        # 构建基础指标
        metrics = {
            "adset_id": adset_id,
            "evaluation_date": date_str,
            "data_range": f"{since_str} ~ {date_str}",
            # 7天数据（用于决策）
            "total_spend_7d": total_spend_7d,
            "total_lpv_7d": total_lpv_7d,
            "total_atc_7d": total_atc_7d,
            "adset_atc_rate_7d": adset_atc_rate,
            # 当天数据（辅助分析）
            "total_spend_today": total_spend_today,
            "total_atc_today": total_atc_today,
            # HHI 分析
            "spend_hhi": hhi_analysis.spend_hhi,
            "atc_hhi": hhi_analysis.atc_hhi,
            "effective_ad_count": hhi_analysis.effective_ad_count,
            "concentration_level": hhi_analysis.concentration_level,
            # 广告统计
            "total_ads": len(ad_performances),
            "low_spend_ads_count": len(low_spend_ads),
            "active_today": len(active_today),
            "inactive_today": len(inactive_today),
            # 花费不足的广告详情（可能有潜力）
            "low_spend_ads": low_spend_ads,
        }

        # 决策逻辑（基于7天数据）
        if adset_atc_rate >= atc_threshold:
            # ATC 率达标，继续投放
            self.log(f"ATC rate {adset_atc_rate:.2%} >= threshold {atc_threshold:.1%}, CONTINUE")

            reasons = [
                f"✅ 广告组7天加购率 {adset_atc_rate:.2%} 达标（阈值 {atc_threshold:.1%}）",
                f"📊 7天花费 ${total_spend_7d:.2f}，加购 {total_atc_7d} 次",
                f"📈 有效广告数: {hhi_analysis.effective_ad_count:.1f}（{hhi_analysis.concentration_level}）",
                f"📅 广告组共 {len(ad_performances)} 个广告，今日活跃 {len(active_today)} 个",
            ]

            # 显示花费不足的广告（可能因预算竞争）
            if low_spend_ads:
                reasons.append(f"💡 {len(low_spend_ads)} 个广告花费较少（可能因预算竞争）:")
                for ad in low_spend_ads[:3]:
                    reasons.append(f"  - {ad['ad_name'] or ad['ad_id']}: {ad['note']}")
                if len(low_spend_ads) > 3:
                    reasons.append(f"  ... 还有 {len(low_spend_ads) - 3} 个")

            # 添加表现最好的广告
            top_ads = sorted(ad_performances, key=lambda x: x.efficiency_score, reverse=True)[:3]
            if top_ads:
                reasons.append("🌟 表现最佳广告:")
                for ad in top_ads:
                    window_info = self._format_active_windows(ad.active_windows)
                    reasons.append(
                        f"  - {ad.ad_name or ad.ad_id}: "
                        f"效率={ad.efficiency_score:.2f}, 7D花费=${ad.spend_7d:.2f}, "
                        f"7D加购={ad.atc_7d}, 活跃窗口={window_info}"
                    )

            return RuleResult(
                decision="continue",
                reasons=reasons,
                metrics=metrics,
            )

        # ATC 率不达标，需要优化
        self.log(f"ATC rate {adset_atc_rate:.2%} < threshold {atc_threshold:.1%}, OPTIMIZE")

        # 在所有广告中识别"高消耗低转化"的广告（基于7天数据和HHI有效广告数）
        inefficient_ads = self._identify_inefficient_ads(
            ad_performances, efficiency_threshold, hhi_analysis.effective_ad_count
        )

        # 确定要关闭的广告
        ads_to_pause = self._select_ads_to_pause(
            inefficient_ads,
            total_ads=len(ad_performances),
            max_pause=max_pause,
            min_remaining=min_remaining,
        )

        # 构建结果
        actions = []
        # 计算"吃到预算"的阈值，用于分类广告（提前计算，后面多处使用）
        spend_share_threshold = 1.0 / hhi_analysis.effective_ad_count if hhi_analysis.effective_ad_count > 0 else 0

        reasons = [
            f"⚠️ 广告组7天加购率 {adset_atc_rate:.2%} 低于阈值 {atc_threshold:.1%}",
            f"📊 7天花费 ${total_spend_7d:.2f}，仅获得 {total_atc_7d} 次加购",
            f"📈 花费集中度: {hhi_analysis.concentration_level}（有效广告 {hhi_analysis.effective_ad_count:.1f} 个）",
            f"📅 广告组共 {len(ad_performances)} 个广告，今日活跃 {len(active_today)} 个",
        ]
        notes = []

        # 显示吃到预算的广告（花费占比 > 1/有效广告数）
        eating_budget_ads = [ad for ad in ad_performances if ad.spend_share > spend_share_threshold]
        if eating_budget_ads:
            # 按花费占比降序排列
            eating_budget_ads_sorted = sorted(eating_budget_ads, key=lambda x: x.spend_share, reverse=True)
            reasons.append(f"💰 {len(eating_budget_ads)} 个广告吃到预算:")
            for ad in eating_budget_ads_sorted[:5]:
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"7D花费 ${ad.spend_7d:.2f}，CTR={ad.ctr:.2%}，CPM=${ad.cpm:.2f}，"
                    f"效率={ad.efficiency_score:.2f}"
                )
            if len(eating_budget_ads) > 5:
                reasons.append(f"  ... 还有 {len(eating_budget_ads) - 5} 个")

        # 显示花费不足的广告（关停低效广告后可能获得预算）
        if low_spend_ads:
            reasons.append(f"💡 {len(low_spend_ads)} 个广告花费较少（关停低效广告后可能获得预算）:")
            for ad in low_spend_ads[:3]:
                reasons.append(f"  - {ad['ad_name'] or ad['ad_id']}: {ad['note']}")
            if len(low_spend_ads) > 3:
                reasons.append(f"  ... 还有 {len(low_spend_ads) - 3} 个")

        # 报告今天不活跃但有历史数据的广告（辅助分析）
        if inactive_today:
            reasons.append(f"ℹ️ 今日无花费的广告 ({len(inactive_today)} 个):")
            for ad in inactive_today[:3]:
                window_info = self._format_active_windows(ad.active_windows)
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"7D花费=${ad.spend_7d:.2f}, 7D加购={ad.atc_7d}, 活跃窗口={window_info}"
                )
            if len(inactive_today) > 3:
                reasons.append(f"  ... 还有 {len(inactive_today) - 3} 个")

        if inefficient_ads:
            reasons.append(f"🔍 识别到 {len(inefficient_ads)} 个高消耗低转化广告（效率分数 < {efficiency_threshold}）:")
            for ad in inefficient_ads:
                window_info = self._format_active_windows(ad.active_windows)
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"花费占比={ad.spend_share:.1%}, ATC占比={ad.atc_share:.1%}, "
                    f"效率={ad.efficiency_score:.2f}, 7D花费=${ad.spend_7d:.2f}, 活跃={window_info}"
                )

        if ads_to_pause:
            reasons.append(f"❌ 建议关闭 {len(ads_to_pause)} 个广告:")
            for ad in ads_to_pause:
                window_info = self._format_active_windows(ad.active_windows)
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"7D花费 ${ad.spend_7d:.2f} ({ad.spend_share:.1%}), "
                    f"7D加购 {ad.atc_7d} 次, 活跃={window_info}"
                )
                if not dry_run:
                    actions.append({
                        "action": "pause_ad",
                        "entity_type": "ad",
                        "entity_id": ad.ad_id,
                        "reason": f"高消耗低转化(7D): 花费占比 {ad.spend_share:.1%}, ATC占比 {ad.atc_share:.1%}",
                    })

            if dry_run:
                notes.append(f"[试运行模式] 建议关闭 {len(ads_to_pause)} 个高消耗低转化广告")
        elif inefficient_ads:
            # 识别到高消耗低转化广告，但因为最少保留数限制无法关闭
            reasons.append(
                f"⚠️ 识别到 {len(inefficient_ads)} 个高消耗低转化广告，"
                f"但需保留至少 {min_remaining} 个广告，暂不关闭"
            )
            notes.append("建议：手动检查广告素材质量，或降低最少保留数后重试")
        else:
            reasons.append("⚡ 未找到高消耗低转化广告（没有广告同时满足：效率低 + 吃到预算）")

        # 分类剩余广告
        remaining_ads = [ad for ad in ad_performances if ad not in ads_to_pause]

        # 1. 表现良好的广告（效率 >= 阈值）
        good_ads = [ad for ad in remaining_ads if ad.efficiency_score >= efficiency_threshold]

        # 2. 因保留数限制未关闭的高消耗低转化广告（在 inefficient_ads 中但不在 ads_to_pause 中）
        kept_high_spend_inefficient = [ad for ad in inefficient_ads if ad not in ads_to_pause]

        # 3. 没吃到预算的低效广告（效率低但花费占比 <= 阈值）
        low_spend_inefficient = [
            ad for ad in remaining_ads
            if ad.efficiency_score < efficiency_threshold and ad.spend_share <= spend_share_threshold
        ]

        if good_ads:
            best_good = sorted(good_ads, key=lambda x: x.efficiency_score, reverse=True)[:3]
            reasons.append("✅ 表现良好的广告:")
            for ad in best_good:
                window_info = self._format_active_windows(ad.active_windows)
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"效率={ad.efficiency_score:.2f}, 7D花费=${ad.spend_7d:.2f}, "
                    f"7D加购={ad.atc_7d}, 活跃={window_info}"
                )

        if kept_high_spend_inefficient:
            reasons.append(f"⚠️ 因保留数限制未关闭的高消耗低转化广告 ({len(kept_high_spend_inefficient)} 个):")
            for ad in kept_high_spend_inefficient[:3]:
                window_info = self._format_active_windows(ad.active_windows)
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"效率={ad.efficiency_score:.2f}, 花费占比={ad.spend_share:.1%}, "
                    f"7D花费=${ad.spend_7d:.2f}, 活跃={window_info}"
                )
            if len(kept_high_spend_inefficient) > 3:
                reasons.append(f"  ... 还有 {len(kept_high_spend_inefficient) - 3} 个")

        if low_spend_inefficient:
            reasons.append(f"💤 未吃到预算的广告 ({len(low_spend_inefficient)} 个):")
            for ad in low_spend_inefficient[:3]:
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"7D花费 ${ad.spend_7d:.2f}，CTR={ad.ctr:.2%}，CPM=${ad.cpm:.2f}，"
                    f"效率={ad.efficiency_score:.2f}"
                )
            if len(low_spend_inefficient) > 3:
                reasons.append(f"  ... 还有 {len(low_spend_inefficient) - 3} 个")
            notes.append("💡 关停高消耗低转化广告后，未吃到预算的广告可能获得更多展示机会")

        # 更新指标
        metrics["inefficient_ads_count"] = len(inefficient_ads)
        metrics["ads_to_pause"] = [ad.ad_id for ad in ads_to_pause]
        metrics["ad_details"] = [
            {
                "ad_id": ad.ad_id,
                "ad_name": ad.ad_name,
                "spend_today": ad.spend_today,
                "spend_7d": ad.spend_7d,
                "spend_share": ad.spend_share,
                "atc_today": ad.atc_today,
                "atc_7d": ad.atc_7d,
                "atc_share": ad.atc_share,
                "atc_rate": ad.atc_rate,
                "efficiency_score": ad.efficiency_score,
                "active_windows": ad.active_windows,
                "is_active_today": ad.is_active_today,
            }
            for ad in ad_performances
        ]

        decision = "stop_recommended" if (ads_to_pause and dry_run) else (
            "stop_executed" if ads_to_pause else "continue"
        )

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

    async def _filter_ads_by_adset(
        self,
        adset_id: str,
        insights_records: list[dict],
    ) -> list[dict]:
        """过滤出属于指定广告组的广告（直接使用 adset_id 字段过滤）"""
        filtered = []
        for record in insights_records:
            record_adset_id = record.get("adset_id")
            if record_adset_id == adset_id:
                filtered.append(record)

        self.log(f"Filtered {len(filtered)} ads from {len(insights_records)} total records for adset {adset_id}")
        return filtered

    def _build_ad_performances_with_trend(
        self,
        records: list[dict],
        min_spend: float,
        eval_date_str: str,
    ) -> tuple[list[AdPerformance], list[dict]]:
        """
        构建广告表现数据（包含多窗口活跃度分析）

        分析不同时间窗口（1d, 3d, 5d, 7d）的活跃情况：
        - 广告可能没跑满7天（新广告）
        - 中途关停或被平台算法调低预算也会导致某些日期无数据
        - 使用多窗口分析判断广告活跃状态

        返回:
        - performances: 所有有数据的广告列表
        - low_spend_ads: 花费不足但可能有潜力的广告（用于日志）
        """
        from collections import defaultdict
        from datetime import datetime, timedelta

        # 解析评估日期
        eval_date = datetime.strptime(eval_date_str, "%Y-%m-%d")

        # 计算各窗口的日期范围
        windows = {
            "1d": [eval_date_str],
            "3d": [(eval_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)],
            "5d": [(eval_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)],
            "7d": [(eval_date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)],
        }

        # 按广告 ID 分组，收集每天的数据
        ad_daily_data: dict[str, dict[str, dict]] = defaultdict(dict)

        for record in records:
            ad_id = record.get("ad_id", "")
            date = record.get("date", "")
            if ad_id and date:
                ad_daily_data[ad_id][date] = record

        performances = []
        low_spend_ads = []  # 记录花费不足的广告（用于日志提示）

        for ad_id, daily_records in ad_daily_data.items():
            # 计算 7 天总花费和数据（用于趋势分析）
            total_spend_7d = 0.0
            total_clicks_7d = 0
            total_lpv_7d = 0
            total_atc_7d = 0
            total_atc_value_7d = 0.0
            total_impressions_7d = 0

            # 收集每天的花费
            daily_spends: list[tuple[str, float]] = []

            for date, record in sorted(daily_records.items()):
                m = record.get("metrics", {})
                spend = float(m.get("spend") or 0)
                daily_spends.append((date, spend))

                total_spend_7d += spend
                total_clicks_7d += int(m.get("clicks") or 0)
                total_lpv_7d += int(m.get("landing_page_view") or 0)
                total_atc_7d += int(m.get("onsite_web_add_to_cart") or 0)
                total_atc_value_7d += float(m.get("onsite_web_add_to_cart_value") or 0)
                total_impressions_7d += int(m.get("impressions") or 0)

            # 获取广告名称
            latest_record = list(daily_records.values())[-1]
            ad_name = latest_record.get("ad_name")

            # 计算效率指标
            # CTR = clicks / impressions
            ctr = total_clicks_7d / total_impressions_7d if total_impressions_7d > 0 else 0
            # CPM = spend / impressions * 1000
            cpm = (total_spend_7d / total_impressions_7d * 1000) if total_impressions_7d > 0 else 0
            # ATC率 = atc / lpv (或 clicks)
            denominator = total_lpv_7d if total_lpv_7d > 0 else total_clicks_7d
            atc_rate = total_atc_7d / denominator if denominator > 0 else 0

            # 记录花费不足的广告（仅用于日志，不过滤）
            is_low_spend = total_spend_7d < min_spend
            if is_low_spend:
                low_spend_ads.append({
                    "ad_id": ad_id,
                    "ad_name": ad_name,
                    "spend_7d": total_spend_7d,
                    "impressions_7d": total_impressions_7d,
                    "clicks_7d": total_clicks_7d,
                    "ctr": ctr,
                    "cpm": cpm,
                    "atc_rate": atc_rate,
                    "note": f"7D花费 ${total_spend_7d:.2f}，CTR={ctr:.2%}，CPM=${cpm:.2f}",
                })

            # 获取评估日当天的数据
            today_record = daily_records.get(eval_date_str)
            if today_record:
                m = today_record.get("metrics", {})
                spend_today = float(m.get("spend") or 0)
                clicks_today = int(m.get("clicks") or 0)
                lpv_today = int(m.get("landing_page_view") or 0)
                atc_today = int(m.get("onsite_web_add_to_cart") or 0)
                is_active_today = spend_today > 0
            else:
                spend_today = 0.0
                clicks_today = 0
                lpv_today = 0
                atc_today = 0
                is_active_today = False

            # 计算多窗口活跃度
            active_windows = {}
            for window_name, window_dates in windows.items():
                # 该窗口内至少有一天有花费才算活跃
                window_spend = sum(
                    float(daily_records.get(d, {}).get("metrics", {}).get("spend") or 0)
                    for d in window_dates
                    if d in daily_records
                )
                active_windows[window_name] = window_spend > 0

            # 获取广告名称（从最近一条记录）
            latest_record = today_record or list(daily_records.values())[-1]
            ad_name = latest_record.get("ad_name")

            performances.append(
                AdPerformance(
                    ad_id=ad_id,
                    ad_name=ad_name,
                    spend_today=spend_today,
                    clicks_today=clicks_today,
                    lpv_today=lpv_today,
                    atc_today=atc_today,
                    spend_7d=total_spend_7d,
                    clicks_7d=total_clicks_7d,
                    lpv_7d=total_lpv_7d,
                    atc_7d=total_atc_7d,
                    atc_value_7d=total_atc_value_7d,
                    impressions_7d=total_impressions_7d,
                    atc_rate=atc_rate,
                    ctr=ctr,
                    cpm=cpm,
                    active_windows=active_windows,
                    daily_spends=daily_spends,
                    is_active_today=is_active_today,
                )
            )

        return performances, low_spend_ads

    def _format_active_windows(self, active_windows: dict) -> str:
        """格式化活跃窗口信息，如 '1d✓,3d✓,5d✗,7d✗'"""
        if not active_windows:
            return "无数据"
        parts = []
        for window in ["1d", "3d", "5d", "7d"]:
            if window in active_windows:
                symbol = "✓" if active_windows[window] else "✗"
                parts.append(f"{window}{symbol}")
        return ",".join(parts) if parts else "无数据"

    def _calculate_shares_and_efficiency(
        self,
        performances: list[AdPerformance],
        total_spend: float,
        total_atc: int,
    ) -> None:
        """计算花费占比、ATC占比和效率分数（基于7天数据，用于决策）"""
        for ad in performances:
            ad.spend_share = ad.spend_7d / total_spend if total_spend > 0 else 0
            ad.atc_share = ad.atc_7d / total_atc if total_atc > 0 else 0

            # 效率分数 = ATC占比 / 花费占比
            # > 1 表示超出平均，< 1 表示低于平均
            if ad.spend_share > 0:
                ad.efficiency_score = ad.atc_share / ad.spend_share
            else:
                ad.efficiency_score = 0

    def _calculate_hhi(self, performances: list[AdPerformance]) -> HHIAnalysis:
        """
        计算 HHI (赫芬达尔-赫希曼指数)

        HHI = Σ(share_i * 100)²
        范围: 0 ~ 10000
        - 10000: 完全垄断（1个广告占100%）
        - 2500: 4个均等广告
        - 1000: 10个均等广告
        """
        # 花费 HHI
        spend_hhi = sum((ad.spend_share * 100) ** 2 for ad in performances)

        # ATC HHI
        atc_hhi = sum((ad.atc_share * 100) ** 2 for ad in performances)

        # 有效广告数 = 10000 / HHI (近似值)
        effective_count = 10000 / spend_hhi if spend_hhi > 0 else len(performances)

        # 集中度等级
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

    def _identify_inefficient_ads(
        self,
        performances: list[AdPerformance],
        efficiency_threshold: float,
        effective_ad_count: float,
    ) -> list[AdPerformance]:
        """
        识别高消耗低转化广告

        高消耗低转化的定义：
        1. 效率分数低于阈值（ATC占比/花费占比 < threshold）
        2. 花费占比高于"有效广告"的平均份额（花费占比 > 1/有效广告数）

        有效广告数由 HHI（赫芬达尔-赫希曼指数）计算：
        - 有效广告数 = 10000 / HHI（逆辛普森指数）
        - 这个值反映了"实际在吃预算"的广告数量

        例如：3个广告，HHI=5000，有效广告数=2
        - 阈值 = 1/2 = 50%
        - 只有花费占比 > 50% 的广告才算"吃到预算"
        """
        if not performances or effective_ad_count <= 0:
            return []

        # 基于有效广告数计算"吃到预算"的阈值
        # 花费占比 > 1/有效广告数 的广告才算占用了有效预算份额
        spend_share_threshold = 1.0 / effective_ad_count

        inefficient = []

        for ad in performances:
            # 高消耗低转化条件：
            # 1. 效率分数低于阈值
            # 2. 花费占比高于有效广告的平均份额（真正"吃到预算"的广告）
            is_low_efficiency = ad.efficiency_score < efficiency_threshold
            is_eating_budget = ad.spend_share > spend_share_threshold

            if is_low_efficiency and is_eating_budget:
                inefficient.append(ad)

        # 按花费占比降序排列（花费最高的低效广告优先关停）
        inefficient.sort(key=lambda x: x.spend_share, reverse=True)

        return inefficient

    def _select_ads_to_pause(
        self,
        inefficient_ads: list[AdPerformance],
        total_ads: int,
        max_pause: int,
        min_remaining: int,
    ) -> list[AdPerformance]:
        """
        选择要关闭的广告

        逻辑：
        1. 如果低效广告数 < 总广告数，说明有好广告，保留好广告即可
        2. 如果所有广告都低效，至少保留1个（避免广告组完全停止）
        3. 单次最多关闭 max_pause 个
        """
        if not inefficient_ads:
            return []

        # 计算有多少"好广告"（不在低效列表中的）
        good_ads_count = total_ads - len(inefficient_ads)

        if good_ads_count >= min_remaining:
            # 有足够的好广告，可以关闭所有低效广告（但不超过 max_pause）
            num_to_pause = min(len(inefficient_ads), max_pause)
        else:
            # 好广告不足，需要保留一些低效广告
            # 但至少保留1个广告让广告组继续运行
            must_keep = max(1, min_remaining - good_ads_count)
            max_can_pause = max(0, len(inefficient_ads) - must_keep)
            num_to_pause = min(max_can_pause, max_pause)

        return inefficient_ads[:num_to_pause]
