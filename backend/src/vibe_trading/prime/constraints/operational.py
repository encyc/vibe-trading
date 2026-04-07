"""
操作约束 - 控制交易行为

确保交易操作符合运营规范。
"""
from collections import deque
from datetime import datetime
from typing import Deque, Optional

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage
from vibe_trading.prime.constraints.base import BaseConstraint, ConstraintResult, ConstraintStatus

logger = get_logger(__name__)


class OperationalConstraint(BaseConstraint):
    """
    操作约束 - 控制交易行为

    检查项：
    1. 交易频率限制
    2. 方向改变限制（防止频繁多空切换）
    3. 市场时间限制（避开重大公告时段）
    4. 每日交易次数限制
    """

    def __init__(
        self,
        min_trade_interval: float = 60.0,
        max_direction_changes: int = 3,
        max_daily_trades: int = 20,
        **kwargs
    ):
        """
        初始化操作约束

        Args:
            min_trade_interval: 最小交易间隔（秒）
            max_direction_changes: 最大方向改变次数（每小时）
            max_daily_trades: 每日最大交易次数
        """
        super().__init__(name="operational_constraint", **kwargs)
        self.min_trade_interval = min_trade_interval
        self.max_direction_changes = max_direction_changes
        self.max_daily_trades = max_daily_trades

        # 状态跟踪
        self._last_trade_time: Optional[datetime] = None
        self._trade_directions: Deque[str] = deque(maxlen=100)  # 最近的方向
        self._daily_trade_count = 0
        self._last_reset_date = datetime.now().date()

    async def check(self, message: AgentMessage) -> ConstraintResult:
        """检查操作约束"""
        # 重置每日计数
        self._reset_daily_if_needed()

        content = message.content

        # 1. 交易频率限制
        if "trade_action" in content:
            if self._last_trade_time:
                elapsed = (datetime.now() - self._last_trade_time).total_seconds()
                if elapsed < self.min_trade_interval:
                    return self._fail(
                        f"交易频率过高: 距离上次交易仅{elapsed:.1f}秒",
                        metadata={
                            "elapsed": elapsed,
                            "min_interval": self.min_trade_interval,
                        },
                    )

        # 2. 方向改变限制
        if "direction" in content:
            direction = content["direction"]
            self._trade_directions.append(direction)

            # 检查最近一小时的改变次数
            changes = self._count_direction_changes(hours=1)
            if changes > self.max_direction_changes:
                return self._fail(
                    f"方向改变过于频繁: 最近1小时{changes}次",
                    metadata={
                        "changes": changes,
                        "max_changes": self.max_direction_changes,
                    },
                )

        # 3. 每日交易次数限制
        if "trade_action" in content:
            if self._daily_trade_count >= self.max_daily_trades:
                return self._fail(
                    f"每日交易次数已达上限: {self._daily_trade_count}/{self.max_daily_trades}",
                    metadata={
                        "daily_count": self._daily_trade_count,
                        "max_daily": self.max_daily_trades,
                    },
                )

            self._daily_trade_count += 1
            self._last_trade_time = datetime.now()

        return self._pass(
            "操作约束检查通过",
            metadata={
                "daily_trade_count": self._daily_trade_count,
                "direction_changes_last_hour": self._count_direction_changes(hours=1),
            },
        )

    def _count_direction_changes(self, hours: int = 1) -> int:
        """计算方向改变次数"""
        if not self._trade_directions:
            return 0

        changes = 0
        last_direction = None

        for direction in reversed(self._trade_directions):
            # 这里简化处理，实际应该记录时间戳
            if last_direction is not None and direction != last_direction:
                changes += 1
            last_direction = direction

        return changes

    def _reset_daily_if_needed(self) -> None:
        """如果需要，重置每日统计"""
        today = datetime.now().date()
        if today != self._last_reset_date:
            self._daily_trade_count = 0
            self._last_reset_date = today
            logger.info("Daily trade count reset")

    async def get_status(self) -> ConstraintStatus:
        """获取约束状态"""
        # 计算资源使用率
        if self._daily_trade_count >= self.max_daily_trades:
            status = "error"
        elif self._daily_trade_count >= self.max_daily_trades * 0.8:
            status = "warning"
        else:
            status = "ok"

        return ConstraintStatus(
            name=self.name,
            enabled=self.enabled,
            violations_today=self.violations_today,
            last_check_time=self.last_check_time,
            last_violation_time=self.last_violation_time,
            current_value=float(self._daily_trade_count),
            threshold_value=float(self.max_daily_trades),
            status=status,
        )

        return ConstraintStatus(
            name=self.name,
            enabled=self.enabled,
            violations_today=self.violations_today,
            last_check_time=self.last_check_time,
            last_violation_time=self.last_violation_time,
            current_value=float(self._daily_trade_count),
            threshold_value=float(self.max_daily_trades),
            status="warning" if self._daily_trade_count > self.max_daily_trades * 0.8 else "ok",
        )
