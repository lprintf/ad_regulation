"""
规则基类 - 所有规则必须继承此类
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from utils.db import RuleBindingDocument


@dataclass
class RuleResult:
    """规则执行结果"""

    decision: str  # continue, stop_recommended, stop_executed, skip, error
    actions: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


class RuleBase(ABC):
    """
    规则基类 - 所有规则必须继承此类

    子类必须定义:
    - name: 规则唯一标识
    - description: 规则描述
    - parameters_schema: 参数定义（用于前端渲染）

    子类必须实现:
    - async evaluate() -> RuleResult
    """

    # 类级别元数据（子类必须定义）
    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    tags: ClassVar[list[str]] = []

    # 参数 schema（用于前端渲染和验证）
    parameters_schema: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        binding: RuleBindingDocument | None = None,
        params: dict[str, Any] | None = None,
    ):
        self.binding = binding
        self.params = params or {}
        self.logger = logging.getLogger(f"rule.{self.name}")
        self._logs: list[str] = []

    def log(self, message: str, level: str = "INFO"):
        """记录执行日志（同时写入内部日志列表和 logger）"""
        entry = f"[{level}] {message}"
        self._logs.append(entry)
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)

    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数，优先使用运行时 params，其次使用 schema 默认值"""
        if key in self.params:
            return self.params[key]
        schema = self.parameters_schema.get(key, {})
        return schema.get("default", default)

    @abstractmethod
    async def evaluate(self) -> RuleResult:
        """
        执行规则评估 - 子类必须实现

        规则内部可以:
        - 直接调用 InsightsService 获取数据
        - 直接加载 ML 模型进行预测
        - 直接调用 Facebook API
        - 使用 async/await
        """
        raise NotImplementedError

    async def execute(self) -> RuleResult:
        """执行入口（带日志收集和异常处理）"""
        self.log(f"========== Rule Execution Start: {self.name} ==========")

        if self.binding:
            self.log(f"Binding: entity_type={self.binding.entity_type}, entity_id={self.binding.entity_id}")

        try:
            result = await self.evaluate()
            result.logs = self._logs
            self.log(f"========== Rule Execution End: {result.decision.upper()} ==========")
            return result
        except Exception as exc:
            self.log(f"Rule execution failed: {exc}", "ERROR")
            return RuleResult(
                decision="error",
                reasons=[f"Execution error: {exc}"],
                logs=self._logs,
            )
