curl --resolve fb-dev.moondeity.dpdns.org:8080:127.0.0.1 \
  -X POST "http://fb-dev.moondeity.dpdns.org:8080/api/insights/drilldown" \
  -H "Content-Type: application/json" \
  -d '{
    "selections": [
      {
        "account_id": "act_1707499729759767",
        "campaign_id": null,
        "adset_id": null,
        "ad_id": null
      }
    ],
    "level": "ad",
    "since": "2025-12-01",
    "until": "2025-12-12",
    "source": "mongo_redis"
  }'