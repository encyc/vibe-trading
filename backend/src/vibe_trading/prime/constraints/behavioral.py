"""
行为约束 - Agent行为边界

确保Agent在其职责范围内行动，防止越权行为。
"""
from typing import Dict, List, Optional, Set

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage, MessageType
from vibe_trading.prime.constraints.base import BaseConstraint, ConstraintResult

logger = get_logger(__name__)


class BehavioralConstraint(BaseConstraint):
    """
    行为约束 - Agent行为边界

    检查项：
    1. Agent只能在自己的领域内做决策
    2. 禁止某些Agent直接下单（只能提供建议）
    3. 决策一致性检查（检测异常行为）
    4. 消息格式验证
    """

    def __init__(
        self,
        **kwargs
    ):
        """
        初始化行为约束
        """
        super().__init__(name="behavioral_constraint", **kwargs)

        # Agent权限定义
        self._can_direct_trade: Set[str] = {
            "trader",
            "portfolio_manager",
        }

        # Agent领域定义
        self._agent_domains: Dict[str, List[str]] = {
            "technical_analyst": ["technical_analysis", "trend", "support_resistance"],
            "fundamental_analyst": ["fundamental_analysis", "funding_rate", "open_interest"],
            "news_analyst": ["news_analysis", "market_events"],
            "sentiment_analyst": ["sentiment_analysis", "social_sentiment"],
            "bull_researcher": ["bull_argument", "investment_advice"],
            "bear_researcher": ["bear_argument", "risk_warning"],
            "research_manager": ["investment_recommendation", "final_decision"],
            "aggressive_risk_analyst": ["aggressive_risk_assessment"],
            "neutral_risk_analyst": ["neutral_risk_assessment"],
            "conservative_risk_analyst": ["conservative_risk_assessment"],
            "trader": ["trading_plan", "execution_plan"],
            "portfolio_manager": ["portfolio_decision", "final_approval"],
            "macro_analyst": ["macro_analysis", "market_regime"],
        }

        # 异常行为检测
        self._agent_message_history: Dict[str, List[MessageType]] = {}

    async def check(self, message: AgentMessage) -> ConstraintResult:
        """检查行为约束"""
        sender = message.sender
        content = message.content

        # 1. Agent只能在自己的领域内做决策
        if sender in self._agent_domains:
            domains = self._agent_domains[sender]
            message_domain = self._extract_domain(content)

            if message_domain and message_domain not in domains:
                return self._fail(
                    f"Agent越权: {sender} 尝试操作 {message_domain}（不在其职责范围内）",
                    metadata={
                        "agent": sender,
                        "attempted_domain": message_domain,
                        "allowed_domains": domains,
                    },
                )

        # 2. 禁止某些Agent直接下单
        if "direct_order" in content:
            if sender not in self._can_direct_trade:
                return self._fail(
                    f"Agent无权直接下单: {sender}",
                    metadata={
                        "agent": sender,
                        "action": "direct_order",
                    },
                )

        # 3. 决策一致性检查
        if await self._is_abnormal_behavior(message):
            return self._fail(
                "检测到异常行为模式",
                metadata={
                    "agent": sender,
                    "message_type": message.message_type.value,
                },
            )

        # 4. 消息格式验证
        if not self._validate_message_format(message):
            return self._fail(
                "消息格式无效",
                metadata={
                    "message_type": message.message_type.value,
                },
            )

        return self._pass(
            "行为约束检查通过",
            metadata={
                "agent": sender,
                "message_type": message.message_type.value,
            },
        )

    def _extract_domain(self, content: Dict) -> Optional[str]:
        """从消息内容提取领域"""
        # 根据content的内容判断领域
        if "technical_indicators" in content:
            return "technical_analysis"
        elif "funding_rate" in content or "open_interest" in content:
            return "fundamental_analysis"
        elif any(key.startswith("news") for key in content.keys()):
            return "news_analysis"
        elif any("sentiment" in key for key in content.keys()):
            return "sentiment_analysis"
        elif "bull_argument" in content:
            return "bull_argument"
        elif "bear_argument" in content:
            return "bear_argument"
        elif "trading_plan" in content:
            return "trading_plan"
        elif "final_decision" in content:
            return "portfolio_decision"
        # ... 更多领域判断
        return None

    async def _is_abnormal_behavior(self, message: AgentMessage) -> bool:
        """检查是否是异常行为"""
        sender = message.sender

        # 初始化历史记录
        if sender not in self._agent_message_history:
            self._agent_message_history[sender] = []

        # 记录消息类型
        self._agent_message_history[sender].append(message.message_type)

        # 只保留最近100条
        if len(self._agent_message_history[sender]) > 100:
            self._agent_message_history[sender] = self._agent_message_history[sender][-100:]

        # 异常检测：发送不属于自己的消息类型
        # 例如：技术分析师发送投资建议
        expected_types = self._get_expected_message_types(sender)
        if message.message_type not in expected_types:
            # 警告而不是失败（因为可能有合理的跨域协作）
            logger.warning(
                f"Agent {sender} 发送非预期消息类型: {message.message_type.value}"
            )
            return False  # 不视为异常行为

        # 异常检测：消息频率异常
        recent_count = len([
            mt for mt in self._agent_message_history[sender][-10:]
            if mt == message.message_type
        ])
        if recent_count >= 8:  # 最近10条消息中有8条相同类型
            logger.warning(f"Agent {sender} 消息类型过于单一")
            return True

        return False

    def _get_expected_message_types(self, agent_id: str) -> Set[MessageType]:
        """获取Agent预期应该发送的消息类型"""
        # 简化版本，实际应该更详细
        all_types = set(MessageType)
        return all_types  # 暂时返回所有类型

    def _validate_message_format(self, message: AgentMessage) -> bool:
        """验证消息格式"""
        # 基本格式检查
        if not message.message_id:
            return False
        if not message.sender:
            return False
        if not message.message_type:
            return False
        if message.content is None:
            return False

        return True
