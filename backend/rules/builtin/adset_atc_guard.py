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

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from rules.base import RuleBase, RuleResult
from rules.registry import register_rule


@dataclass
class AdPerformance:
    """单个广告的表现数据"""

    ad_id: str
    ad_name: str | None
    spend: float
    clicks: int
    landing_page_view: int
    add_to_cart: int
    add_to_cart_value: float
    # 计算指标
    spend_share: float = 0.0  # 花费占比
    atc_share: float = 0.0  # 加购占比
    atc_rate: float = 0.0  # 加购率
    efficiency_score: float = 0.0  # 效率评分 (atc_share / spend_share)


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

        self.log(f"AdSet ID: {adset_id}")
        self.log(f"Evaluation Date: {date_str}")
        self.log(f"ATC Rate Threshold: {atc_threshold:.1%}")
        self.log(f"Dry Run: {'ON' if dry_run else 'OFF'}")

        # 获取广告组内所有广告的数据
        try:
            insights_data = await InsightsService.query_insights_mongo_redis(
                ad_account_id=ad_account_id,
                since=date_str,
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
        adset_ads = await self._filter_ads_by_adset(
            ad_account_id, adset_id, insights_records
        )

        if not adset_ads:
            self.log(f"No ads found for adset {adset_id}")
            return RuleResult(
                decision="skip",
                reasons=[f"No ads found in adset {adset_id}"],
            )

        # 构建广告表现数据
        ad_performances = self._build_ad_performances(adset_ads, min_spend)

        if not ad_performances:
            self.log("No ads meet minimum spend threshold")
            return RuleResult(
                decision="skip",
                reasons=[f"No ads with spend >= ${min_spend:.2f}"],
            )

        # 计算广告组整体 ATC 率
        total_lpv = sum(ad.landing_page_view for ad in ad_performances)
        total_clicks = sum(ad.clicks for ad in ad_performances)
        total_atc = sum(ad.add_to_cart for ad in ad_performances)
        total_spend = sum(ad.spend for ad in ad_performances)

        # 使用 LPV 计算 ATC 率，如果没有 LPV 则用 clicks
        denominator = total_lpv if total_lpv > 0 else total_clicks
        adset_atc_rate = total_atc / denominator if denominator > 0 else 0

        self.log(f"AdSet Total: Spend=${total_spend:.2f}, LPV={total_lpv}, ATC={total_atc}")
        self.log(f"AdSet ATC Rate: {adset_atc_rate:.2%} (threshold: {atc_threshold:.1%})")

        # 计算占比和效率分数
        self._calculate_shares_and_efficiency(ad_performances, total_spend, total_atc)

        # HHI 分析
        hhi_analysis = self._calculate_hhi(ad_performances)
        self.log(
            f"HHI Analysis: Spend HHI={hhi_analysis.spend_hhi:.0f}, "
            f"Effective Ads={hhi_analysis.effective_ad_count:.1f}, "
            f"Concentration={hhi_analysis.concentration_level}"
        )

        # 构建基础指标
        metrics = {
            "adset_id": adset_id,
            "evaluation_date": date_str,
            "total_spend": total_spend,
            "total_lpv": total_lpv,
            "total_atc": total_atc,
            "adset_atc_rate": adset_atc_rate,
            "spend_hhi": hhi_analysis.spend_hhi,
            "atc_hhi": hhi_analysis.atc_hhi,
            "effective_ad_count": hhi_analysis.effective_ad_count,
            "concentration_level": hhi_analysis.concentration_level,
            "ads_evaluated": len(ad_performances),
        }

        # 决策逻辑
        if adset_atc_rate >= atc_threshold:
            # ATC 率达标，继续投放
            self.log(f"ATC rate {adset_atc_rate:.2%} >= threshold {atc_threshold:.1%}, CONTINUE")

            reasons = [
                f"✅ 广告组加购率 {adset_atc_rate:.2%} 达标（阈值 {atc_threshold:.1%}）",
                f"📊 花费 ${total_spend:.2f}，加购 {total_atc} 次",
                f"📈 有效广告数: {hhi_analysis.effective_ad_count:.1f}（{hhi_analysis.concentration_level}）",
            ]

            # 添加表现最好的广告
            top_ads = sorted(ad_performances, key=lambda x: x.efficiency_score, reverse=True)[:3]
            if top_ads:
                reasons.append("🌟 表现最佳广告:")
                for ad in top_ads:
                    reasons.append(
                        f"  - {ad.ad_name or ad.ad_id}: "
                        f"效率={ad.efficiency_score:.2f}, ATC率={ad.atc_rate:.2%}"
                    )

            return RuleResult(
                decision="continue",
                reasons=reasons,
                metrics=metrics,
            )

        # ATC 率不达标，需要优化
        self.log(f"ATC rate {adset_atc_rate:.2%} < threshold {atc_threshold:.1%}, OPTIMIZE")

        # 识别低效广告
        inefficient_ads = self._identify_inefficient_ads(
            ad_performances, efficiency_threshold
        )

        # 确定要关闭的广告
        ads_to_pause = self._select_ads_to_pause(
            inefficient_ads,
            total_active=len(ad_performances),
            max_pause=max_pause,
            min_remaining=min_remaining,
        )

        # 构建结果
        actions = []
        reasons = [
            f"⚠️ 广告组加购率 {adset_atc_rate:.2%} 低于阈值 {atc_threshold:.1%}",
            f"📊 花费 ${total_spend:.2f}，仅获得 {total_atc} 次加购",
            f"📈 花费集中度: {hhi_analysis.concentration_level}（有效广告 {hhi_analysis.effective_ad_count:.1f} 个）",
        ]
        notes = []

        if inefficient_ads:
            reasons.append(f"🔍 识别到 {len(inefficient_ads)} 个低效广告（效率分数 < {efficiency_threshold}）:")
            for ad in inefficient_ads:
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"花费占比={ad.spend_share:.1%}, ATC占比={ad.atc_share:.1%}, "
                    f"效率={ad.efficiency_score:.2f}"
                )

        if ads_to_pause:
            reasons.append(f"❌ 建议关闭 {len(ads_to_pause)} 个广告:")
            for ad in ads_to_pause:
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"花费 ${ad.spend:.2f} ({ad.spend_share:.1%}), "
                    f"仅 {ad.add_to_cart} 次加购"
                )
                if not dry_run:
                    actions.append({
                        "action": "pause_ad",
                        "entity_type": "ad",
                        "entity_id": ad.ad_id,
                        "reason": f"低效广告: 花费占比 {ad.spend_share:.1%}, ATC占比 {ad.atc_share:.1%}",
                    })

            if dry_run:
                notes.append(f"[试运行模式] 建议关闭 {len(ads_to_pause)} 个低效广告")
        else:
            reasons.append("⚡ 未找到明显低效广告，建议观察或调整素材")
            notes.append("所有广告效率相近，可能需要整体优化素材或定向")

        # 保留的好广告
        remaining_ads = [
            ad for ad in ad_performances if ad not in ads_to_pause
        ]
        if remaining_ads:
            best_remaining = sorted(remaining_ads, key=lambda x: x.efficiency_score, reverse=True)[:3]
            reasons.append("✅ 保留继续投放的广告:")
            for ad in best_remaining:
                reasons.append(
                    f"  - {ad.ad_name or ad.ad_id}: "
                    f"效率={ad.efficiency_score:.2f}, ATC率={ad.atc_rate:.2%}"
                )

        # 更新指标
        metrics["inefficient_ads_count"] = len(inefficient_ads)
        metrics["ads_to_pause"] = [ad.ad_id for ad in ads_to_pause]
        metrics["ad_details"] = [
            {
                "ad_id": ad.ad_id,
                "ad_name": ad.ad_name,
                "spend": ad.spend,
                "spend_share": ad.spend_share,
                "atc": ad.add_to_cart,
                "atc_share": ad.atc_share,
                "atc_rate": ad.atc_rate,
                "efficiency_score": ad.efficiency_score,
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

            ad_obj = get_ad_object(ad_account_id, ad_id, "ad")
            ad_info = ad_obj.api_get(fields=["adset_id"])
            return ad_info.get("adset_id")
        except Exception as exc:
            self.log(f"Failed to get adset_id: {exc}", "WARNING")
            return None

    async def _filter_ads_by_adset(
        self,
        ad_account_id: str,
        adset_id: str,
        insights_records: list[dict],
    ) -> list[dict]:
        """过滤出属于指定广告组的广告"""
        # 获取广告组下的所有广告 ID
        try:
            from utils.fb_api_flyweight_factory import get_ad_object

            adset_obj = get_ad_object(ad_account_id, adset_id, "adset")
            ads = adset_obj.get_ads(fields=["id"])
            adset_ad_ids = {ad["id"] for ad in ads}
        except Exception as exc:
            self.log(f"Failed to get ads for adset: {exc}", "WARNING")
            # 尝试从 insights 数据中推断（如果有 adset_id 字段）
            adset_ad_ids = None

        filtered = []
        for record in insights_records:
            ad_id = record.get("ad_id")
            if adset_ad_ids is not None:
                if ad_id in adset_ad_ids:
                    filtered.append(record)
            else:
                # 如果无法获取广告组广告列表，假设所有数据都属于该广告组
                filtered.append(record)

        return filtered

    def _build_ad_performances(
        self,
        records: list[dict],
        min_spend: float,
    ) -> list[AdPerformance]:
        """构建广告表现数据"""
        performances = []

        for record in records:
            m = record.get("metrics", {})
            spend = float(m.get("spend") or 0)

            if spend < min_spend:
                continue

            clicks = int(m.get("clicks") or 0)
            lpv = int(m.get("landing_page_view") or 0)
            atc = int(m.get("onsite_web_add_to_cart") or 0)
            atc_value = float(m.get("onsite_web_add_to_cart_value") or 0)

            # 计算 ATC 率
            denominator = lpv if lpv > 0 else clicks
            atc_rate = atc / denominator if denominator > 0 else 0

            performances.append(
                AdPerformance(
                    ad_id=record.get("ad_id", ""),
                    ad_name=record.get("ad_name"),
                    spend=spend,
                    clicks=clicks,
                    landing_page_view=lpv,
                    add_to_cart=atc,
                    add_to_cart_value=atc_value,
                    atc_rate=atc_rate,
                )
            )

        return performances

    def _calculate_shares_and_efficiency(
        self,
        performances: list[AdPerformance],
        total_spend: float,
        total_atc: int,
    ) -> None:
        """计算花费占比、ATC占比和效率分数"""
        for ad in performances:
            ad.spend_share = ad.spend / total_spend if total_spend > 0 else 0
            ad.atc_share = ad.add_to_cart / total_atc if total_atc > 0 else 0

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
    ) -> list[AdPerformance]:
        """识别低效广告"""
        inefficient = []

        for ad in performances:
            # 低效条件：
            # 1. 效率分数低于阈值
            # 2. 有一定花费但加购很少或为0
            if ad.efficiency_score < efficiency_threshold:
                inefficient.append(ad)

        # 按效率分数升序排列（最低效的在前）
        inefficient.sort(key=lambda x: x.efficiency_score)

        return inefficient

    def _select_ads_to_pause(
        self,
        inefficient_ads: list[AdPerformance],
        total_active: int,
        max_pause: int,
        min_remaining: int,
    ) -> list[AdPerformance]:
        """选择要关闭的广告"""
        if not inefficient_ads:
            return []

        # 确保至少保留 min_remaining 个广告
        max_can_pause = max(0, total_active - min_remaining)

        # 取最低效的几个，但不超过限制
        num_to_pause = min(len(inefficient_ads), max_pause, max_can_pause)

        return inefficient_ads[:num_to_pause]
