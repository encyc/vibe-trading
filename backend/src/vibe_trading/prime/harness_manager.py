"""
Harness Manager - 多层次约束管理

管理和协调所有约束的检查。
"""
from typing import Dict

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage
from vibe_trading.prime.constraints.base import BaseConstraint, ConstraintResult, ConstraintStatus
from vibe_trading.prime.constraints.safety import SafetyConstraint
from vibe_trading.prime.constraints.operational import OperationalConstraint
from vibe_trading.prime.constraints.behavioral import BehavioralConstraint
from vibe_trading.prime.constraints.resource import ResourceConstraint
from vibe_trading.prime.models import HarnessConfig

logger = get_logger(__name__)


class HarnessManager:
    """
    Harness Manager - 约束管理器

    管理多层次约束：
    1. 安全约束 - 资金安全、风险限制
    2. 操作约束 - 交易频率、仓位限制
    3. 行为约束 - Agent行为边界
    4. 资源约束 - LLM调用、成本控制
    """

    def __init__(self, config: HarnessConfig):
        """
        初始化约束管理器

        Args:
            config: 约束配置
        """
        self.config = config

        # 初始化约束
        self.constraints: Dict[str, BaseConstraint] = {}

        if config.enable_safety_constraint:
            self.constraints["safety"] = SafetyConstraint()

        if config.enable_operational_constraint:
            self.constraints["operational"] = OperationalConstraint()

        if config.enable_behavioral_constraint:
            self.constraints["behavioral"] = BehavioralConstraint()

        if config.enable_resource_constraint:
            self.constraints["resource"] = ResourceConstraint()

        logger.info(
            f"Harness Manager initialized with {len(self.constraints)} constraints: "
            f"{', '.join(self.constraints.keys())}"
        )

    async def check_all_constraints(self, message: AgentMessage) -> bool:
        """
        检查所有约束

        Args:
            message: 要检查的消息

        Returns:
            是否通过所有约束检查
        """
        for name, constraint in self.constraints.items():
            result = await constraint.check_and_record(message)

            if not result.passed:
                logger.warning(
                    f"违反{name}约束: {result.reason}",
                    tag="HARNESS",
                )

                # 根据配置决定如何处理违规
                if self.config.violation_action == "block":
                    return False
                elif self.config.violation_action == "warn":
                    # 仅记录警告，继续处理
                    continue
                elif self.config.violation_action == "log":
                    # 仅记录日志，继续处理
                    continue

        return True

    async def check_constraint(
        self,
        constraint_name: str,
        message: AgentMessage,
    ) -> ConstraintResult:
        """
        检查单个约束

        Args:
            constraint_name: 约束名称
            message: 要检查的消息

        Returns:
            约束检查结果
        """
        if constraint_name not in self.constraints:
            return ConstraintResult(
                passed=False,
                constraint_name=constraint_name,
                reason=f"约束不存在: {constraint_name}",
            )

        constraint = self.constraints[constraint_name]
        return await constraint.check_and_record(message)

    async def get_constraint_status(
        self,
        constraint_name: str,
    ) -> ConstraintStatus:
        """
        获取约束状态

        Args:
            constraint_name: 约束名称

        Returns:
            约束状态
        """
        if constraint_name not in self.constraints:
            raise ValueError(f"约束不存在: {constraint_name}")

        constraint = self.constraints[constraint_name]
        return await constraint.get_status()

    async def get_all_constraint_statuses(self) -> Dict[str, ConstraintStatus]:
        """获取所有约束的状态"""
        return {
            name: await constraint.get_status()
            for name, constraint in self.constraints.items()
        }

    def get_constraint(self, constraint_name: str) -> BaseConstraint:
        """
        获取约束实例

        Args:
            constraint_name: 约束名称

        Returns:
            约束实例
        """
        if constraint_name not in self.constraints:
            raise ValueError(f"约束不存在: {constraint_name}")

        return self.constraints[constraint_name]

    def update_safety_state(
        self,
        total_position: float = None,
        account_balance: float = None,
        margin_ratio: float = None,
    ) -> None:
        """更新安全约束的状态"""
        if "safety" in self.constraints:
            safety_constraint = self.constraints["safety"]
            if isinstance(safety_constraint, SafetyConstraint):
                safety_constraint.update_state(
                    total_position=total_position,
                    account_balance=account_balance,
                    margin_ratio=margin_ratio,
                )

    def reset_daily_stats(self) -> None:
        """重置所有约束的每日统计"""
        for constraint in self.constraints.values():
            constraint.reset_daily_stats()

        logger.info("All constraint daily stats reset")

    async def get_violation_summary(self) -> Dict[str, int]:
        """获取违规统计摘要"""
        return {
            name: constraint.violations_today
            for name, constraint in self.constraints.items()
        }

    def enable_constraint(self, constraint_name: str) -> None:
        """启用约束"""
        if constraint_name in self.constraints:
            self.constraints[constraint_name].enabled = True
            logger.info(f"Constraint enabled: {constraint_name}")

    def disable_constraint(self, constraint_name: str) -> None:
        """禁用约束"""
        if constraint_name in self.constraints:
            self.constraints[constraint_name].enabled = False
            logger.info(f"Constraint disabled: {constraint_name}")

    def is_constraint_enabled(self, constraint_name: str) -> bool:
        """检查约束是否启用"""
        if constraint_name not in self.constraints:
            return False
        return self.constraints[constraint_name].enabled
