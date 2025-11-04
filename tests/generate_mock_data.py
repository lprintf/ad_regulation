"""
Utility script to build mock rule contexts from live Facebook data.

Usage examples:
    uv run python tests/generate_mock_data.py \\
        --ad-account-id act_1234567890 \\
        --ad-id 111222333444555 \\
        --output tests/mocks/generated_context.json

    uv run python tests/generate_mock_data.py \\
        --ad-account-id act_1234567890 \\
        --ad-id 111222333444555 \\
        --output tests/mocks/anonymized_context.json \\
        --anonymize \\
        --ml-template models/feat.feather

The script fetches a real execution context using RuleContextService,
optionally anonymises identifiers, and packages the data together with
an ML feature template (sampled from the provided feather file) to help
build realistic mock payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from api.services.rule_context_service import RuleContextService
from utils.db import close_db, init_db
from utils.fb_api_flyweight_factory import get_ad_object


@dataclass
class BindingStub:
    rule_name: str
    entity_type: str
    entity_id: str
    metadata: Dict[str, Any]
    rule_id: Optional[str] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate mock rule context data based on live fetches."
    )
    parser.add_argument(
        "--ad-account-id",
        default=os.getenv("TEST_AD_ACCOUNT_ID"),
        required=False,
        help="Ad account id (with act_ prefix).",
    )
    parser.add_argument(
        "--ad-id",
        default=os.getenv("TEST_AD_ID"),
        required=False,
        help="Ad id to inspect.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/mocks/generated_rule_context.json"),
        help="Path to write the resulting JSON mock data.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/mocks"),
        help="Output directory for batch generation.",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Replace identifiers with placeholder tokens.",
    )
    parser.add_argument(
        "--ml-template",
        type=Path,
        help="Optional Feather/Parquet file to sample ML feature template from.",
    )
    parser.add_argument(
        "--sample-index",
        type=int,
        help="Optional row index to pick from the ML template file (random if omitted).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON to stdout.",
    )
    parser.add_argument(
        "--synthesize-if-empty",
        action="store_true",
        help="Generate synthetic non-zero performance metrics when live data is empty.",
    )
    parser.add_argument(
        "--list-ads",
        action="store_true",
        help="Only list ad ids under the account without generating files.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Generate mock data for every ad under the specified ad account.",
    )
    return parser.parse_args()


def anonymize_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace sensitive identifiers with deterministic placeholders.
    """
    mapping: Dict[str, str] = {}

    def _anon(value: str, prefix: str) -> str:
        if value not in mapping:
            mapping[value] = f"{prefix}_{len(mapping) + 1:04d}"
        return mapping[value]

    anonymised = json.loads(json.dumps(context))  # deep copy

    if "entity_id" in anonymised:
        anonymised["entity_id"] = _anon(str(anonymised["entity_id"]), "entity")
    if "metadata" in anonymised and "ad_account_id" in anonymised["metadata"]:
        anonymised["metadata"]["ad_account_id"] = _anon(
            str(anonymised["metadata"]["ad_account_id"]), "account"
        )
    if "ad" in anonymised and anonymised["ad"]:
        ad = anonymised["ad"]
        if "ad_id" in ad:
            anon_ad_id = _anon(str(ad["ad_id"]), "ad")
            ad["ad_id"] = anon_ad_id
        if "account_id" in ad:
            anon_account_id = _anon(str(ad["account_id"]), "account")
            ad["account_id"] = anon_account_id
        if "name" in ad:
            ad["name"] = f"Mock Creative {ad['ad_id']}"

    # Replace country codes with generic placeholders if requested
    if "targeting" in anonymised and anonymised["targeting"].get("countries"):
        anonymised["targeting"]["countries"] = [
            f"COUNTRY_{idx+1:02d}"
            for idx, _ in enumerate(anonymised["targeting"]["countries"])
        ]
    return anonymised


def load_ml_template(path: Path, sample_index: Optional[int] = None) -> Dict[str, Any]:
    df = pd.read_feather(path)
    if df.empty:
        raise ValueError(f"Template file {path} is empty.")
    if sample_index is None:
        sample_index = random.randrange(len(df))
    if sample_index < 0 or sample_index >= len(df):
        raise IndexError(f"sample_index {sample_index} out of range for {len(df)} rows")
    row = df.iloc[sample_index]
    return row.to_dict()


async def fetch_context(ad_account_id: str, ad_id: str) -> Dict[str, Any]:
    binding_stub = BindingStub(
        rule_name="demo_spend_guard",
        entity_type="ad",
        entity_id=ad_id,
        metadata={"ad_account_id": ad_account_id},
    )
    return await RuleContextService.build_context(binding_stub)  # type: ignore[arg-type]


async def fetch_ad_ids(ad_account_id: str) -> list[str]:
    account = await get_ad_object(ad_account_id, ad_account_id)

    def _call() -> list[str]:
        ads = account.get_ads(fields=[])
        return [ad["id"] for ad in ads]

    return await asyncio.to_thread(_call)


def serialise(data: Dict[str, Any], pretty: bool = False) -> str:
    if pretty:
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return json.dumps(data, ensure_ascii=False, default=str)


def synthesize_performance(context: Dict[str, Any], days: int = 14) -> bool:
    """
    Populate performance metrics with synthetic non-zero samples when missing.
    Returns True if synthetic data was injected.
    """
    performance = context.get("performance")
    if not isinstance(performance, dict):
        performance = {}
        context["performance"] = performance

    spend = performance.get("spend") or 0
    daily_samples = performance.get("daily_samples") or []

    if spend and spend > 0:
        return False
    if daily_samples:
        # If there are samples but spend is zero, leave as-is to avoid conflict.
        if any(sample.get("spend") for sample in daily_samples):
            return False

    seed_source = str(context.get("entity_id") or context.get("rule_name") or "demo")
    rand = random.Random(seed_source)

    today = datetime.now(UTC)
    synthetic_samples: list[dict[str, Any]] = []
    for offset in range(days):
        day = today - timedelta(days=days - offset)
        spend_value = round(rand.uniform(4.0, 7.5), 2)
        clicks_value = rand.randint(4, 12)
        impressions_value = rand.randint(400, 1200)
        synthetic_samples.append(
            {
                "date_start": day.isoformat(),
                "date_stop": day.isoformat(),
                "spend": spend_value,
                "clicks": clicks_value,
                "impressions": impressions_value,
            }
        )

    total_spend = round(sum(item["spend"] for item in synthetic_samples), 2)
    total_clicks = sum(item["clicks"] for item in synthetic_samples)
    total_impressions = sum(item["impressions"] for item in synthetic_samples)

    ctr = (
        round((total_clicks / total_impressions * 100), 4) if total_impressions else 0.0
    )
    cpc = round((total_spend / total_clicks), 4) if total_clicks else None

    performance["spend"] = total_spend
    performance["clicks"] = total_clicks
    performance["impressions"] = total_impressions
    performance["ctr"] = ctr
    performance.setdefault("ctr_unit", "percent")
    performance["cpc"] = cpc
    performance.setdefault("currency", "USD")
    performance["daily_samples"] = synthetic_samples

    window = performance.get("window")
    if not isinstance(window, dict):
        window = {}
    window_since = synthetic_samples[0]["date_start"]
    window_until = synthetic_samples[-1]["date_stop"]
    performance["window"] = {
        "since": window.get("since") or window_since,
        "until": window.get("until") or window_until,
        "days": days,
    }

    fetch_errors = context.get("fetch_errors")
    if not isinstance(fetch_errors, list):
        fetch_errors = []
    fetch_errors.append("synthetic_performance_generated")
    context["fetch_errors"] = fetch_errors
    return True


async def main() -> None:
    args = parse_args()
    if not args.ad_account_id:
        raise SystemExit(
            "Argument --ad-account-id (or TEST_AD_ACCOUNT_ID) is required."
        )
    if not (args.ad_id or args.list_ads or args.batch):
        raise SystemExit("Provide --ad-id, --list-ads, or --batch to proceed.")

    ml_template_path = args.ml_template

    await init_db()
    try:
        if args.list_ads:
            ad_ids = await fetch_ad_ids(args.ad_account_id)
            print(
                json.dumps(
                    {"ad_account_id": args.ad_account_id, "ad_ids": ad_ids},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

        if args.batch:
            ad_ids = await fetch_ad_ids(args.ad_account_id)
            if not ad_ids:
                print("No ads found for the given ad account.")
                return

            args.output_dir.mkdir(parents=True, exist_ok=True)
            summary: list[dict[str, Any]] = []
            template = (
                load_ml_template(ml_template_path, sample_index=args.sample_index)
                if ml_template_path
                else None
            )

            for ad_id in ad_ids:
                context = await fetch_context(args.ad_account_id, ad_id)
                if args.synthesize_if_empty:
                    synthesize_performance(context)
                data: Dict[str, Any] = {"rule_context": context}
                if args.anonymize:
                    data["rule_context_anonymized"] = anonymize_context(context)
                if template is not None:
                    data["ml_feature_template"] = template

                output_path = args.output_dir / f"rule_context_{ad_id}.json"
                output_path.write_text(
                    serialise(data, pretty=args.pretty), encoding="utf-8"
                )
                summary.append({"ad_id": ad_id, "path": str(output_path)})

            if args.pretty:
                print(
                    json.dumps(
                        {"generated_files": summary},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"Generated {len(summary)} files under {args.output_dir}")
            return

        if not args.ad_id:
            raise SystemExit(
                "Argument --ad-id required when not using --batch/--list-ads."
            )

        context = await fetch_context(args.ad_account_id, args.ad_id)
        if args.synthesize_if_empty:
            synthesize_performance(context)
    finally:
        await close_db()

    result: Dict[str, Any] = {"rule_context": context}

    if args.anonymize:
        result["rule_context_anonymized"] = anonymize_context(context)

        if ml_template_path:
            template = load_ml_template(
                ml_template_path, sample_index=args.sample_index
            )
            result["ml_feature_template"] = template

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialise(result, pretty=args.pretty), encoding="utf-8")

    if args.pretty:
        print(serialise(result, pretty=True))
    else:
        print(f"Mock data written to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
