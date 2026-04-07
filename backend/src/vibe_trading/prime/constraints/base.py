"""
基础约束接口

定义所有约束的基类和通用接口。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from vibe_trading.agents.messaging import AgentMessage


class ConstraintSeverity(str, Enum):
    """约束严重程度"""
    INFO = "info"          # 信息性（不违规）
    WARNING = "warning"    # 警告（可以继续但需注意）
    ERROR = "error"        # 错误（应该阻止）
    CRITICAL = "critical"  # 严重（必须阻止）


@dataclass
class ConstraintResult:
    """约束检查结果"""
    passed: bool
    constraint_name: str
    reason: str = ""
    severity: ConstraintSeverity = ConstraintSeverity.INFO
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __bool__(self) -> bool:
        return self.passed


@dataclass
class ConstraintStatus:
    """约束状态"""
    name: str
    enabled: bool
    violations_today: int = 0
    last_check_time: Optional[datetime] = None
    last_violation_time: Optional[datetime] = None
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    status: str = "ok"  # ok, warning, error


class BaseConstraint(ABC):
    """
    约束基类

    所有约束都继承自这个基类，实现check方法。
    """

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        severity: ConstraintSeverity = ConstraintSeverity.ERROR,
    ):
        """
        初始化约束

        Args:
            name: 约束名称
            enabled: 是否启用
            severity: 违规严重程度
        """
        self.name = name
        self.enabled = enabled
        self.severity = severity
        self.violations_today = 0
        self.last_check_time = None
        self.last_violation_time = None

    @abstractmethod
    async def check(self, message: AgentMessage) -> ConstraintResult:
        """
        检查消息是否违反约束

        Args:
            message: 要检查的消息

        Returns:
            约束检查结果
        """
        pass

    async def check_and_record(self, message: AgentMessage) -> ConstraintResult:
        """
        检查约束并记录统计

        Args:
            message: 要检查的消息

        Returns:
            约束检查结果
        """
        self.last_check_time = datetime.now()

        if not self.enabled:
            return ConstraintResult(
                passed=True,
                constraint_name=self.name,
                reason="Constraint is disabled",
            )

        result = await self.check(message)

        if not result.passed:
            self.violations_today += 1
            self.last_violation_time = datetime.now()

        return result

    async def get_status(self) -> ConstraintStatus:
        """
        获取约束状态

        Returns:
            约束状态
        """
        # 子类可以覆盖这个方法提供更详细的状态
        return ConstraintStatus(
            name=self.name,
            enabled=self.enabled,
            violations_today=self.violations_today,
            last_check_time=self.last_check_time,
            last_violation_time=self.last_violation_time,
        )

    def reset_daily_stats(self) -> None:
        """重置每日统计"""
        self.violations_today = 0
        self.last_violation_time = None

    def _pass(
        self,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConstraintResult:
        """创建通过结果"""
        return ConstraintResult(
            passed=True,
            constraint_name=self.name,
            reason=reason or "Constraint check passed",
            severity=ConstraintSeverity.INFO,
            metadata=metadata or {},
        )

    def _fail(
        self,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConstraintResult:
        """创建失败结果"""
        return ConstraintResult(
            passed=False,
            constraint_name=self.name,
            reason=reason,
            severity=self.severity,
            metadata=metadata or {},
        )
