import pytest

from api.services.insights_service import InsightsService


def _insight(
    *,
    ad_id: str,
    date: str,
    spend: float,
    campaign_id: str | None = None,
    ad_account_id: str = "act_123",
) -> dict:
    return {
        "ad_account_id": ad_account_id,
        "ad_id": ad_id,
        "adset_id": None,
        "campaign_id": campaign_id,
        "ad_name": None,
        "adset_name": None,
        "campaign_name": None,
        "configured_status": None,
        "effective_status": None,
        "date": date,
        "metrics": {"spend": spend},
    }


@pytest.mark.asyncio
async def test_query_insights_hybrid_merges_and_prefers_realtime(monkeypatch):
    async def fake_db(
        ad_account_id,
        since,
        until,
        level="ad",
        time_increment=None,
        breakdowns=None,
        object_level=None,
        object_ids=None,
        mask_ad_ids=False,
    ):
        assert ad_account_id == "act_123"
        assert since == "2025-01-01"
        assert until == "2025-01-03"
        assert mask_ad_ids is False
        return {
            "insights": [
                _insight(ad_id="ad_001", date="2025-01-01", spend=5.0),
                _insight(ad_id="ad_002", date="2025-01-02", spend=1.5),
            ],
            "total_records": 2,
            "date_range": {"since": since, "until": until},
        }

    async def fake_from_last(
        ad_account_id,
        until,
        level="ad",
        time_increment=None,
        breakdowns=None,
        fields=None,
        object_level=None,
        object_ids=None,
        cache_window_hint=None,
    ):
        assert ad_account_id == "act_123"
        assert until == "2025-01-03"
        assert cache_window_hint == "01:02:03"
        return {
            "insights": [
                _insight(ad_id="ad_001", date="2025-01-01", spend=8.5),
            ],
            "total_records": 1,
            "date_range": {"since": "2025-01-02", "until": until},
        }

    monkeypatch.setattr(
        InsightsService, "query_insights_from_db", staticmethod(fake_db)
    )
    monkeypatch.setattr(
        InsightsService,
        "query_insights_from_last_gap",
        staticmethod(fake_from_last),
    )

    result = await InsightsService.query_insights_hybrid(
        ad_account_id="act_123",
        since="2025-01-01",
        until="2025-01-03",
        level="ad",
        cache_window_hint="01:02:03",
    )

    assert result["date_range"] == {"since": "2025-01-01", "until": "2025-01-03"}
    assert result["total_records"] == 2
    ids = [record["ad_id"] for record in result["insights"]]
    assert ids == ["ad_001", "ad_002"]
    merged_first = result["insights"][0]
    assert pytest.approx(merged_first["metrics"]["spend"], rel=1e-6) == 8.5


@pytest.mark.asyncio
async def test_query_insights_hybrid_applies_object_filter(monkeypatch):
    async def fake_db(**kwargs):
        return {
            "insights": [
                _insight(
                    ad_id="ad_drop",
                    date="2025-02-01",
                    spend=3.0,
                    campaign_id="cmp_drop",
                    ad_account_id="act_321",
                )
            ],
            "total_records": 1,
            "date_range": {"since": "2025-02-01", "until": "2025-02-01"},
        }

    async def fake_from_last(**kwargs):
        return {
            "insights": [
                _insight(
                    ad_id="ad_keep",
                    date="2025-02-01",
                    spend=4.0,
                    campaign_id="cmp_keep",
                    ad_account_id="act_321",
                )
            ],
            "total_records": 1,
            "date_range": {"since": "2025-02-01", "until": "2025-02-01"},
        }

    monkeypatch.setattr(
        InsightsService, "query_insights_from_db", staticmethod(fake_db)
    )
    monkeypatch.setattr(
        InsightsService,
        "query_insights_from_last_gap",
        staticmethod(fake_from_last),
    )

    result = await InsightsService.query_insights_hybrid(
        ad_account_id="act_321",
        since="2025-02-01",
        until="2025-02-01",
        level="ad",
        object_level="campaign",
        object_ids=["cmp_keep"],
    )

    assert result["total_records"] == 1
    record = result["insights"][0]
    assert record["campaign_id"] == "cmp_keep"
    assert record["ad_id"] == "ad_keep"
