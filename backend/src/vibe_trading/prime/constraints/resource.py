"""
资源约束 - LLM调用和成本控制

确保资源使用在合理范围内，控制成本。
"""
from datetime import datetime, timedelta

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage
from vibe_trading.prime.constraints.base import BaseConstraint, ConstraintResult, ConstraintStatus

logger = get_logger(__name__)


class ResourceConstraint(BaseConstraint):
    """
    资源约束 - LLM调用和成本控制

    检查项：
    1. LLM调用频率限制
    2. 每日成本限制
    3. Token使用限制
    4. API限流
    """

    def __init__(
        self,
        max_llm_calls_per_day: int = 1000,
        max_daily_cost: float = 10.0,
        max_tokens_per_message: int = 8000,
        max_calls_per_minute: int = 60,
        **kwargs
    ):
        """
        初始化资源约束

        Args:
            max_llm_calls_per_day: 每日最大LLM调用次数
            max_daily_cost: 每日最大成本（美元）
            max_tokens_per_message: 每条消息最大token数
            max_calls_per_minute: 每分钟最大调用次数
        """
        super().__init__(name="resource_constraint", **kwargs)
        self.max_llm_calls_per_day = max_llm_calls_per_day
        self.max_daily_cost = max_daily_cost
        self.max_tokens_per_message = max_tokens_per_message
        self.max_calls_per_minute = max_calls_per_minute

        # 资源使用跟踪
        self._llm_calls_today = 0
        self._cost_today = 0.0
        self._last_reset_date = datetime.now().date()

        # 每分钟调用跟踪
        self._calls_in_last_minute: list[datetime] = []

    async def check(self, message: AgentMessage) -> ConstraintResult:
        """检查资源约束"""
        # 重置每日计数
        self._reset_daily_if_needed()

        content = message.content

        # 1. LLM调用频率限制
        if "llm_call" in content or message.message_type.value.endswith("analysis"):
            # 检查每分钟限制
            await self._cleanup_old_calls()
            if len(self._calls_in_last_minute) >= self.max_calls_per_minute:
                return self._fail(
                    f"LLM调用频率过高: {len(self._calls_in_last_minute)}/分钟",
                    metadata={
                        "calls_per_minute": len(self._calls_in_last_minute),
                        "max_calls_per_minute": self.max_calls_per_minute,
                    },
                )

            # 检查每日限制
            if self._llm_calls_today >= self.max_llm_calls_per_day:
                return self._fail(
                    f"每日LLM调用次数已达上限: {self._llm_calls_today}/{self.max_llm_calls_per_day}",
                    metadata={
                        "daily_calls": self._llm_calls_today,
                        "max_daily": self.max_llm_calls_per_day,
                    },
                )

            self._llm_calls_today += 1
            self._calls_in_last_minute.append(datetime.now())

        # 2. 每日成本限制
        if "estimated_cost" in content:
            cost = content["estimated_cost"]
            new_total = self._cost_today + cost

            if new_total > self.max_daily_cost:
                return self._fail(
                    f"每日成本超限: ${new_total:.2f} > ${self.max_daily_cost:.2f}",
                    metadata={
                        "current_cost": self._cost_today,
                        "new_cost": cost,
                        "total_cost": new_total,
                        "max_daily_cost": self.max_daily_cost,
                    },
                )

            self._cost_today += cost

        # 3. Token使用限制
        if "token_count" in content:
            tokens = content["token_count"]
            if tokens > self.max_tokens_per_message:
                return self._fail(
                    f"Token数量超限: {tokens} > {self.max_tokens_per_message}",
                    metadata={
                        "token_count": tokens,
                        "max_tokens": self.max_tokens_per_message,
                    },
                )

        return self._pass(
            "资源约束检查通过",
            metadata={
                "llm_calls_today": self._llm_calls_today,
                "cost_today": self._cost_today,
                "calls_per_minute": len(self._calls_in_last_minute),
            },
        )

    async def _cleanup_old_calls(self) -> None:
        """清理超过1分钟的调用记录"""
        cutoff = datetime.now() - timedelta(minutes=1)
        self._calls_in_last_minute = [
            t for t in self._calls_in_last_minute
            if t > cutoff
        ]

    def _reset_daily_if_needed(self) -> None:
        """如果需要，重置每日统计"""
        today = datetime.now().date()
        if today != self._last_reset_date:
            self._llm_calls_today = 0
            self._cost_today = 0.0
            self._last_reset_date = today
            logger.info("Daily resource stats reset")

    def record_llm_call(self, tokens: int, cost: float) -> None:
        """记录LLM调用"""
        self._llm_calls_today += 1
        self._cost_today += cost
        self._calls_in_last_minute.append(datetime.now())

    async def get_status(self) -> ConstraintStatus:
        """获取约束状态"""
        # 计算资源使用率
        call_usage = self._llm_calls_today / self.max_llm_calls_per_day
        cost_usage = self._cost_today / self.max_daily_cost

        # 确定状态
        if call_usage > 0.9 or cost_usage > 0.9:
            status = "error"
        elif call_usage > 0.7 or cost_usage > 0.7:
            status = "warning"
        else:
            status = "ok"

        return ConstraintStatus(
            name=self.name,
            enabled=self.enabled,
            violations_today=self.violations_today,
            last_check_time=self.last_check_time,
            last_violation_time=self.last_violation_time,
            current_value=float(max(call_usage, cost_usage)),
            threshold_value=1.0,
            status=status,
        )

        # 计算资源使用率
        call_usage = self._llm_calls_today / self.max_llm_calls_per_day
        cost_usage = self._cost_today / self.max_daily_cost

        # 确定状态
        if call_usage > 0.9 or cost_usage > 0.9:
            status = "error"
        elif call_usage > 0.7 or cost_usage > 0.7:
            status = "warning"
        else:
            status = "ok"

        return ConstraintStatus(
            name=self.name,
            enabled=self.enabled,
            violations_today=self.violations_today,
            last_check_time=self.last_check_time,
            last_violation_time=self.last_violation_time,
            current_value=float(max(call_usage, cost_usage)),
            threshold_value=1.0,
            status=status,
        )
