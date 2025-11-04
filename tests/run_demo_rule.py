"""
Interactive test script for the demo spend guard rule.

Features:
1. Fetches live ad/insight data and prints the entire execution context for inspection.
2. Supports mocking by loading a JSON context file that mirrors the live data structure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.models.rules import (
    BindingEntityType,
    BindingSource,
    RuleBindingCreate,
    RuleBindingResponse,
    RuleBindingUpdate,
    RuleExecutionRequest,
    RuleTrigger,
)
from api.services.rule_engine_service import RuleEngineService
from utils.db import close_db, init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demo runner for spend guard rule with optional mocking."
    )
    parser.add_argument(
        "--ad-account-id",
        default=os.getenv("TEST_AD_ACCOUNT_ID"),
        help="Ad account id (e.g. act_123...). Required for live mode.",
    )
    parser.add_argument(
        "--ad-id",
        default=os.getenv("TEST_AD_ID"),
        help="Ad id for live mode.",
    )
    parser.add_argument(
        "--mock-context",
        type=Path,
        help="Path to JSON file providing mock execution context. If set, live data is not fetched.",
    )
    parser.add_argument(
        "--dump-context",
        type=Path,
        help="Optional path to write the fetched context snapshot as JSON.",
    )
    parser.add_argument(
        "--dump-execution",
        type=Path,
        help="Optional path to write the entire execution payload as JSON.",
    )
    return parser.parse_args()


async def ensure_binding(
    rule_id: str, ad_id: str, ad_account_id: str
) -> RuleBindingResponse:
    metadata = {"ad_account_id": ad_account_id}
    try:
        return await RuleEngineService.create_binding(
            RuleBindingCreate(
                rule_id=rule_id,
                entity_type=BindingEntityType.AD,
                entity_id=ad_id,
                source=BindingSource.MANUAL,
                metadata=metadata,
            )
        )
    except ValueError:
        bindings = await RuleEngineService.list_bindings(
            rule_id=rule_id, entity_id=ad_id, active_only=False
        )
        if not bindings:
            raise

        binding = bindings[0]
        if binding.metadata.get("ad_account_id") != ad_account_id:
            binding = await RuleEngineService.update_binding(
                binding.id,
                RuleBindingUpdate(metadata=metadata),
            )
        return binding


def _dump_json(data: Any, label: str) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(json.loads(json.dumps(data, default=str)), indent=2, ensure_ascii=False)


def _print_section(title: str, payload: Dict[str, Any]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(_dump_json(payload, title))


async def run_demo(args: argparse.Namespace) -> None:
    mock_metadata: Dict[str, Any] = {}
    use_mock = args.mock_context is not None
    if use_mock:
        raw_mock_data = json.loads(args.mock_context.read_text(encoding="utf-8"))
        if isinstance(raw_mock_data, dict) and "rule_context" in raw_mock_data:
            mock_context = raw_mock_data["rule_context"]
            mock_metadata = {
                k: v for k, v in raw_mock_data.items() if k != "rule_context"
            }
        else:
            mock_context = raw_mock_data
            mock_metadata = {}
        if not isinstance(mock_context, dict):
            raise ValueError("Mock context must be a JSON object.")
    else:
        if not args.ad_account_id or not args.ad_id:
            raise SystemExit(
                "Live mode requires --ad-account-id and --ad-id (or corresponding environment variables)."
            )

    await init_db()
    try:
        await RuleEngineService.ensure_demo_rule_seed()
        demo_rule = next(
            (rule for rule in await RuleEngineService.list_rules() if rule.name == "demo_spend_guard"),
            None,
        )
        if not demo_rule:
            raise RuntimeError("Demo rule not found after seeding.")

        if use_mock:
            request = RuleExecutionRequest(
                rule_id=demo_rule.id,
                context=mock_context,  # type: ignore[arg-type]
                trigger=RuleTrigger.TEST,
            )
            binding_info = None
        else:
            binding = await ensure_binding(demo_rule.id, args.ad_id, args.ad_account_id)
            request = RuleExecutionRequest(
                binding_id=binding.id,
                trigger=RuleTrigger.TEST,
            )
            binding_info = binding

        execution = await RuleEngineService.execute_rule(request)

        print("=" * 80)
        print("Demo Spend Guard Rule Execution Result")
        print("=" * 80)
        print(f"Rule: {execution.rule_name} v{execution.rule_version}")
        if binding_info:
            print(f"Binding: {execution.binding_id} -> entity {execution.entity_id}")
        else:
            print("Binding: (mock context)")
        print(f"Trigger: {execution.trigger.value}")
        print(f"Status: {execution.status.value}")

        metrics = execution.metrics or {}
        reasons = execution.reasons or []
        actions = execution.actions or []
        context_snapshot = execution.context_snapshot or {}

        _print_section("Metrics", metrics)
        _print_section("Actions", {"actions": actions})
        _print_section("Reasons", {"reasons": reasons})
        _print_section("Context Snapshot", context_snapshot)
        if use_mock and mock_metadata:
            _print_section("Mock Metadata", mock_metadata)

        if args.dump_context:
            args.dump_context.write_text(
                _dump_json(context_snapshot, "context"),
                encoding="utf-8",
            )
            print(f"\nSaved context snapshot to {args.dump_context}")

        if args.dump_execution:
            args.dump_execution.write_text(
                _dump_json(execution.model_dump(), "execution"),
                encoding="utf-8",
            )
            print(f"Saved full execution payload to {args.dump_execution}")
    finally:
        await close_db()


if __name__ == "__main__":
    cli_args = parse_args()
    asyncio.run(run_demo(cli_args))
