import pytest
from datetime import datetime

import api.services.insights_service as insights_module
from api.services.insights_service import InsightsService


class _DummyAggregation:
    def __init__(self, results):
        self._results = results

    async def to_list(self):
        return self._results


@pytest.mark.asyncio
async def test_db_query_retains_campaign_filter_for_adset_level(monkeypatch):
    captured_pipeline = None
    sample_date = datetime(2025, 1, 1)

    def fake_get_collection(_document_cls):
        return None

    def fake_aggregate(pipeline):
        nonlocal captured_pipeline
        captured_pipeline = pipeline
        return _DummyAggregation(
            [
                {
                    "ad_id": "987654321",
                    "date_start": sample_date,
                    "spend": 12.5,
                    "impressions": 120,
                    "reach": 95,
                    "clicks": 6,
                    "inline_link_clicks": 4,
                    "outbound_clicks": 3,
                    "landing_page_view": 5,
                    "onsite_web_checkout": 2,
                    "onsite_web_add_to_cart": 3,
                    "onsite_web_purchase": 1,
                    "onsite_web_checkout_value": 18.0,
                    "onsite_web_add_to_cart_value": 7.0,
                    "onsite_web_purchase_value": 22.0,
                    "campaign_id": "cmp_1",
                }
            ]
        )

    async def fake_attach(records, level, account_id):
        return records

    monkeypatch.setattr(
        insights_module, "get_document_collection", lambda doc: fake_get_collection(doc)
    )
    monkeypatch.setattr(
        insights_module.InsightsDailyDocument, "aggregate", staticmethod(fake_aggregate)
    )
    monkeypatch.setattr(
        InsightsService, "_attach_entity_names", staticmethod(fake_attach)
    )

    result = await InsightsService.query_insights_from_db(
        ad_account_id="act_123",
        since="2025-01-01",
        until="2025-01-01",
        level="adset",
        object_level="campaign",
        object_ids=["cmp_1"],
    )

    assert result["total_records"] == 1
    record = result["insights"][0]
    assert record["ad_account_id"] == "act_123"
    assert record["campaign_id"] == "cmp_1"
    assert record["adset_id"] == "987654321"
    assert pytest.approx(record["metrics"]["spend"], rel=1e-6) == 12.5

    masked_result = await InsightsService.query_insights_from_db(
        ad_account_id="act_123",
        since="2025-01-01",
        until="2025-01-01",
        level="adset",
        object_level="campaign",
        object_ids=["cmp_1"],
        mask_ad_ids=True,
    )
    masked_record = masked_result["insights"][0]
    assert masked_record["ad_id"] is None
    assert masked_record["ad_account_id"] == "act_123"

    assert captured_pipeline is not None
    group_stage = captured_pipeline[1]["$group"]
    assert group_stage["campaign_id"] == {"$first": "$campaign_id"}
    assert group_stage["spend"] == {
        "$sum": {
            "$toDouble": {
                "$ifNull": ["$spend", 0]
            }
        }
    }
    assert group_stage["impressions"] == {
        "$sum": {
            "$toDouble": {
                "$ifNull": ["$impressions", 0]
            }
        }
    }
