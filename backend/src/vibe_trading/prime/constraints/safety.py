"""
安全约束 - 保护资金安全

确保交易操作不会危及资金安全。
"""
from typing import Optional

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage
from vibe_trading.prime.constraints.base import BaseConstraint, ConstraintResult

logger = get_logger(__name__)


class SafetyConstraint(BaseConstraint):
    """
    安全约束 - 保护资金安全

    检查项：
    1. 单笔交易金额限制
    2. 总仓位限制
    3. 杠杆限制
    4. 保证金充足性
    """

    def __init__(
        self,
        max_single_trade: float = 1000.0,
        max_total_position: float = 0.3,
        max_leverage: int = 5,
        margin_threshold: float = 0.8,
        **kwargs
    ):
        """
        初始化安全约束

        Args:
            max_single_trade: 单笔交易最大金额（USDT）
            max_total_position: 总仓位最大比例（0-1）
            max_leverage: 最大杠杆倍数
            margin_threshold: 保证金阈值（比例）
        """
        super().__init__(name="safety_constraint", **kwargs)
        self.max_single_trade = max_single_trade
        self.max_total_position = max_total_position
        self.max_leverage = max_leverage
        self.margin_threshold = margin_threshold

        # 当前状态（需要从外部更新）
        self._current_total_position = 0.0
        self._account_balance = 10000.0
        self._current_margin_ratio = 0.0

    def update_state(
        self,
        total_position: Optional[float] = None,
        account_balance: Optional[float] = None,
        margin_ratio: Optional[float] = None,
    ) -> None:
        """更新当前状态"""
        if total_position is not None:
            self._current_total_position = total_position
        if account_balance is not None:
            self._account_balance = account_balance
        if margin_ratio is not None:
            self._current_margin_ratio = margin_ratio

    async def check(self, message: AgentMessage) -> ConstraintResult:
        """检查安全约束"""
        content = message.content

        # 1. 单笔交易金额限制
        if "trade_amount" in content:
            amount = content["trade_amount"]
            if amount > self.max_single_trade:
                return self._fail(
                    f"单笔交易金额超限: {amount} > {self.max_single_trade}",
                    metadata={
                        "trade_amount": amount,
                        "max_single_trade": self.max_single_trade,
                    },
                )

        # 2. 总仓位限制
        if "position_change" in content:
            position_change = content["position_change"]
            new_total = self._current_total_position + abs(position_change)
            max_position = self._account_balance * self.max_total_position

            if new_total > max_position:
                return self._fail(
                    f"总仓位超限: {new_total} > {max_position}",
                    metadata={
                        "current_total": self._current_total_position,
                        "position_change": position_change,
                        "new_total": new_total,
                        "max_total": max_position,
                    },
                )

        # 3. 杠杆限制
        if "leverage" in content:
            leverage = content["leverage"]
            if leverage > self.max_leverage:
                return self._fail(
                    f"杠杆超限: {leverage} > {self.max_leverage}",
                    metadata={
                        "leverage": leverage,
                        "max_leverage": self.max_leverage,
                    },
                )

        # 4. 保证金充足性
        if self._current_margin_ratio > self.margin_threshold:
            return self._fail(
                f"保证金不足: {self._current_margin_ratio:.1%} > {self.margin_threshold:.1%}",
                metadata={
                    "margin_ratio": self._current_margin_ratio,
                    "threshold": self.margin_threshold,
                },
            )

        return self._pass(
            "所有安全约束检查通过",
            metadata={
                "total_position": self._current_total_position,
                "account_balance": self._account_balance,
                "margin_ratio": self._current_margin_ratio,
            },
        )
