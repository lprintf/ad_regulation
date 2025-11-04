"""
Lightweight sandbox for executing rule scripts with restricted built-ins.
The sandbox expects each script to expose an ``evaluate(context, params)`` function
that returns a dictionary containing execution output (actions, reasons, etc.).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable


class RuleExecutionError(Exception):
    """Raised when a rule script fails to execute."""


class RuleValidationError(Exception):
    """Raised when a rule script is missing required structures."""


SAFE_BUILTINS: MappingProxyType[str, Any] = MappingProxyType(
    {
        "__import__": __import__,
        "abs": abs,
        "all": all,
        "any": any,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "sorted": sorted,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }
)


def execute_rule_script(
    code: str, context: dict[str, Any], params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Execute a rule script in a restricted environment.

    Args:
        code: Rule script containing an ``evaluate`` function.
        context: Execution context data such as ad metrics, predictions, etc.
        params: Optional parameter overrides.

    Returns:
        Dictionary with execution outputs.

    Raises:
        RuleValidationError: If the script is missing ``evaluate``.
        RuleExecutionError: If execution fails.
    """
    params = params or {}
    local_vars: dict[str, Any] = {}
    global_vars: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
    }

    try:
        exec(code, global_vars, local_vars)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuleExecutionError(f"Failed to compile rule: {exc}") from exc

    evaluate_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = (
        local_vars.get("evaluate") or global_vars.get("evaluate")
    )

    if evaluate_fn is None or not callable(evaluate_fn):
        raise RuleValidationError("Rule script must define callable evaluate(context, params)")

    try:
        result = evaluate_fn(context, params)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuleExecutionError(f"Rule execution failed: {exc}") from exc

    if not isinstance(result, dict):
        raise RuleValidationError("Rule evaluate function must return a dictionary")

    return result
