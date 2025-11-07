"""
Persistence utilities for APScheduler task configuration/state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict

RULE_SCHEDULER_NAMESPACE = "rule_scheduler"
INSIGHTS_SCHEDULER_NAMESPACE = "insights_scheduler"

_STATE_LOCK = Lock()


def _state_file_path() -> Path:
    custom_path = os.getenv("SCHEDULER_STATE_PATH")
    if custom_path:
        return Path(custom_path)
    return Path("output") / "scheduler_state.json"


def _load_state_unlocked() -> Dict[str, Any]:
    path = _state_file_path()
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
            if isinstance(payload, dict):
                return payload
    except Exception:
        # Corrupted payloads should not break scheduler startup.
        return {}
    return {}


def load_namespace(namespace: str) -> Dict[str, Any]:
    with _STATE_LOCK:
        state = _load_state_unlocked()
        value = state.get(namespace, {})
    return value if isinstance(value, dict) else {}


def save_namespace(namespace: str, payload: Dict[str, Any]) -> None:
    path = _state_file_path()
    with _STATE_LOCK:
        state = _load_state_unlocked()
        state[namespace] = payload

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2)
        tmp_path.replace(path)
