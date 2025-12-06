"""
规则注册表 - 管理所有已注册的规则类
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from rules.base import RuleBase

logger = logging.getLogger(__name__)

# 全局规则注册表
RULE_REGISTRY: dict[str, Type[RuleBase]] = {}


def register_rule(cls: Type[RuleBase]) -> Type[RuleBase]:
    """
    装饰器：注册规则到全局注册表

    Usage:
        @register_rule
        class MyRule(RuleBase):
            name = "my_rule"
            ...
    """
    if not hasattr(cls, "name") or not cls.name:
        raise ValueError(f"Rule class {cls.__name__} must define 'name' class variable")

    if cls.name in RULE_REGISTRY:
        logger.warning(f"Rule '{cls.name}' already registered, overwriting")

    RULE_REGISTRY[cls.name] = cls
    logger.info(f"Registered rule: {cls.name} (v{cls.version})")
    return cls


def discover_rules(package_name: str = "rules.builtin") -> None:
    """
    自动发现并导入指定包下的所有规则模块

    这会触发模块加载，从而执行 @register_rule 装饰器
    """
    try:
        package = importlib.import_module(package_name)
    except ImportError as exc:
        logger.warning(f"Failed to import rule package '{package_name}': {exc}")
        return

    if not hasattr(package, "__path__"):
        logger.warning(f"Package '{package_name}' has no __path__, skipping discovery")
        return

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            # 递归发现子包
            discover_rules(f"{package_name}.{module_name}")
        else:
            try:
                importlib.import_module(f"{package_name}.{module_name}")
                logger.debug(f"Loaded rule module: {package_name}.{module_name}")
            except Exception as exc:
                logger.error(f"Failed to load rule module {package_name}.{module_name}: {exc}")


def get_rule_class(name: str) -> Type[RuleBase]:
    """获取规则类，若不存在则抛出 ValueError"""
    if name not in RULE_REGISTRY:
        available = ", ".join(RULE_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Rule '{name}' not found. Available rules: {available}")
    return RULE_REGISTRY[name]


def list_rules() -> list[dict]:
    """列出所有已注册规则的元数据"""
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "version": cls.version,
            "tags": cls.tags,
            "parameters_schema": cls.parameters_schema,
        }
        for cls in RULE_REGISTRY.values()
    ]


def get_rule_metadata(name: str) -> dict | None:
    """获取单个规则的元数据"""
    cls = RULE_REGISTRY.get(name)
    if cls is None:
        return None
    return {
        "name": cls.name,
        "description": cls.description,
        "version": cls.version,
        "tags": cls.tags,
        "parameters_schema": cls.parameters_schema,
    }
