"""
Lightweight sandbox for executing rule scripts with restricted built-ins.
The sandbox expects each script to expose an ``evaluate(context, params)`` function
that returns a dictionary containing execution output (actions, reasons, etc.).
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from types import MappingProxyType
from typing import Any, Callable


class RuleExecutionError(Exception):
    """Raised when a rule script fails to execute."""


class RuleValidationError(Exception):
    """Raised when a rule script is missing required structures."""


class ExecutionLogger:
    """Simple logger for rule scripts to capture execution details."""

    def __init__(self):
        self.logs: list[str] = []

    def log(self, message: str, level: str = "INFO"):
        """Add a log entry."""
        self.logs.append(f"[{level}] {message}")

    def info(self, message: str):
        """Log info level message."""
        self.log(message, "INFO")

    def warning(self, message: str):
        """Log warning level message."""
        self.log(message, "WARNING")

    def debug(self, message: str):
        """Log debug level message."""
        self.log(message, "DEBUG")


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
        "print": print,  # Allow print for debugging
        "range": range,
        "round": round,
        "sorted": sorted,
        "str": str,
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
        Dictionary with execution outputs, including execution_logs.

    Raises:
        RuleValidationError: If the script is missing ``evaluate``.
        RuleExecutionError: If execution fails.
    """
    params = params or {}

    # Create logger for the script
    logger = ExecutionLogger()

    # Capture stdout
    stdout_capture = io.StringIO()

    local_vars: dict[str, Any] = {}
    global_vars: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "logger": logger,  # Provide logger to the script
    }

    try:
        with redirect_stdout(stdout_capture):
            exec(code, global_vars, local_vars)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuleExecutionError(f"Failed to compile rule: {exc}") from exc

    evaluate_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = (
        local_vars.get("evaluate") or global_vars.get("evaluate")
    )

    if evaluate_fn is None or not callable(evaluate_fn):
        raise RuleValidationError("Rule script must define callable evaluate(context, params)")

    try:
        with redirect_stdout(stdout_capture):
            result = evaluate_fn(context, params)
    except Exception as exc:  # pragma: no cover - defensive
        raise RuleExecutionError(f"Rule execution failed: {exc}") from exc

    if not isinstance(result, dict):
        raise RuleValidationError("Rule evaluate function must return a dictionary")

    # Collect all logs
    execution_logs = []

    # Add structured logs from logger
    execution_logs.extend(logger.logs)

    # Add stdout output (from print statements)
    stdout_output = stdout_capture.getvalue()
    if stdout_output.strip():
        for line in stdout_output.strip().split("\n"):
            if line.strip():
                execution_logs.append(f"[PRINT] {line}")

    # Include logs in result
    result["execution_logs"] = execution_logs

    return result
