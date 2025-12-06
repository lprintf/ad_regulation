"""
规则系统入口

自动发现并注册 rules/builtin/ 下的所有规则
"""

from rules.base import RuleBase, RuleResult
from rules.registry import (
    RULE_REGISTRY,
    discover_rules,
    get_rule_class,
    get_rule_metadata,
    list_rules,
    register_rule,
)

__all__ = [
    "RuleBase",
    "RuleResult",
    "RULE_REGISTRY",
    "register_rule",
    "discover_rules",
    "get_rule_class",
    "get_rule_metadata",
    "list_rules",
]


def init_rules() -> None:
    """初始化规则系统，自动发现所有内置规则"""
    discover_rules("rules.builtin")
