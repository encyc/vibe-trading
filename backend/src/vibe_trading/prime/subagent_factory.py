"""
Subagent Factory - Subagent工厂

负责创建和管理所有Subagent实例。
"""
import asyncio
from typing import Dict, List, Optional

from pi_agent_core import Agent
from pi_logger import get_logger

from vibe_trading.agents.analysts.technical_analyst import TechnicalAnalystAgent
from vibe_trading.agents.researchers.researcher_agents import (
    BullResearcherAgent,
    BearResearcherAgent,
    ResearchManagerAgent,
)
from vibe_trading.agents.risk_mgmt.risk_agents import RiskAnalystAgent
from vibe_trading.agents.decision.decision_agents import (
    TraderAgent,
    PortfolioManagerAgent,
)
from vibe_trading.agents.macro_agent import MacroAnalysisAgent
from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.prime.message_channel import MessageChannel, MessagePriority
from vibe_trading.prime.models import SubagentConfig
from vibe_trading.prime.subagent_handle import SubagentHandle

logger = get_logger(__name__)


class SubagentFactory:
    """
    Subagent工厂

    负责创建所有可用的Subagent并返回对应的Handle。

    注意：部分Agent尚未实现，已标记为disabled。
    """

    # 所有Subagent的配置
    SUBAGENT_CONFIGS: Dict[str, SubagentConfig] = {
        # Phase 1: 分析师
        "technical_analyst": SubagentConfig(
            agent_id="technical_analyst",
            agent_type="analyst",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "fundamental_analyst": SubagentConfig(
            agent_id="fundamental_analyst",
            agent_type="analyst",
            enabled=False,  # TODO: 尚未实现
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "news_analyst": SubagentConfig(
            agent_id="news_analyst",
            agent_type="analyst",
            enabled=False,  # TODO: 尚未实现
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=False,
        ),
        "sentiment_analyst": SubagentConfig(
            agent_id="sentiment_analyst",
            agent_type="analyst",
            enabled=False,  # TODO: 尚未实现
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),

        # Phase 2: 研究员
        "bull_researcher": SubagentConfig(
            agent_id="bull_researcher",
            agent_type="researcher",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "bear_researcher": SubagentConfig(
            agent_id="bear_researcher",
            agent_type="researcher",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "research_manager": SubagentConfig(
            agent_id="research_manager",
            agent_type="researcher",
            enabled=True,
            priority=MessagePriority.HIGH,
            can_direct_trade=False,
            required_for_decision=True,
        ),

        # Phase 3: 风控
        "aggressive_risk_analyst": SubagentConfig(
            agent_id="aggressive_risk_analyst",
            agent_type="risk",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "neutral_risk_analyst": SubagentConfig(
            agent_id="neutral_risk_analyst",
            agent_type="risk",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "conservative_risk_analyst": SubagentConfig(
            agent_id="conservative_risk_analyst",
            agent_type="risk",
            enabled=True,
            priority=MessagePriority.NORMAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),

        # Phase 4: 决策层
        "trader": SubagentConfig(
            agent_id="trader",
            agent_type="decision",
            enabled=True,
            priority=MessagePriority.HIGH,
            can_direct_trade=False,
            required_for_decision=True,
        ),
        "portfolio_manager": SubagentConfig(
            agent_id="portfolio_manager",
            agent_type="decision",
            enabled=True,
            priority=MessagePriority.CRITICAL,
            can_direct_trade=False,
            required_for_decision=True,
        ),

        # 宏观分析
        "macro_analyst": SubagentConfig(
            agent_id="macro_analyst",
            agent_type="macro",
            enabled=True,
            priority=MessagePriority.HIGH,
            can_direct_trade=False,
            required_for_decision=True,
        ),
    }

    @classmethod
    def create_subagent(
        cls,
        agent_id: str,
        channel: MessageChannel,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
    ) -> Optional[SubagentHandle]:
        """
        创建单个Subagent

        Args:
            agent_id: Agent ID
            channel: 消息通道
            symbol: 交易对符号
            interval: K线间隔

        Returns:
            SubagentHandle或None（如果agent_id无效或未启用）
        """
        config = cls.SUBAGENT_CONFIGS.get(agent_id)
        if not config:
            logger.warning(f"Unknown subagent: {agent_id}")
            return None

        if not config.enabled:
            logger.info(f"Subagent {agent_id} is disabled, skipping")
            return None

        try:
            # 创建Agent实例（传递symbol和interval）
            agent = cls._create_agent_instance(agent_id, symbol, interval)

            if agent is None:
                logger.warning(f"Failed to create agent instance: {agent_id}")
                return None

            # 创建SubagentHandle
            handle = SubagentHandle(
                agent_id=agent_id,
                agent=agent,
                channel=channel,
                config=config,
                symbol=symbol,
                interval=interval,
            )

            logger.info(f"Created subagent: {agent_id}", tag="SUBAGENT_FACTORY")
            return handle

        except Exception as e:
            logger.error(
                f"Error creating subagent {agent_id}: {e}",
                exc_info=True,
                tag="SUBAGENT_FACTORY",
            )
            return None

    @classmethod
    def create_all_subagents(
        cls,
        channel: MessageChannel,
        enabled_only: bool = True,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
    ) -> Dict[str, SubagentHandle]:
        """
        创建所有Subagent

        Args:
            channel: 消息通道
            enabled_only: 是否只创建启用的Subagent
            symbol: 交易对符号
            interval: K线间隔

        Returns:
            agent_id到SubagentHandle的映射
        """
        subagents = {}

        for agent_id, config in cls.SUBAGENT_CONFIGS.items():
            if enabled_only and not config.enabled:
                continue

            handle = cls.create_subagent(agent_id, channel, symbol, interval)
            if handle:
                subagents[agent_id] = handle

        logger.info(
            f"Created {len(subagents)} subagents (enabled only={enabled_only})",
            tag="SUBAGENT_FACTORY",
        )

        return subagents

    @classmethod
    def _create_agent_instance(
        cls,
        agent_id: str,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
    ) -> Optional[Agent]:
        """
        创建Agent实例

        Args:
            agent_id: Agent ID
            symbol: 交易对符号
            interval: K线间隔

        Returns:
            Agent实例或None
        """
        try:
            # Phase 1: 分析师
            if agent_id == "technical_analyst":
                return TechnicalAnalystAgent()
            # TODO: 添加其他分析师
            # elif agent_id == "fundamental_analyst":
            #     return FundamentalAnalystAgent()

            # Phase 2: 研究员
            elif agent_id == "bull_researcher":
                return BullResearcherAgent()
            elif agent_id == "bear_researcher":
                return BearResearcherAgent()
            elif agent_id == "research_manager":
                return ResearchManagerAgent()

            # Phase 3: 风控
            elif agent_id == "aggressive_risk_analyst":
                return RiskAnalystAgent(config=AgentConfig(
                    name="Aggressive Risk Analyst",
                    role=AgentRole.AGGRESSIVE_DEBATOR,
                    temperature=0.5,
                ))
            elif agent_id == "neutral_risk_analyst":
                return RiskAnalystAgent(config=AgentConfig(
                    name="Neutral Risk Analyst",
                    role=AgentRole.NEUTRAL_DEBATOR,
                    temperature=0.5,
                ))
            elif agent_id == "conservative_risk_analyst":
                return RiskAnalystAgent(config=AgentConfig(
                    name="Conservative Risk Analyst",
                    role=AgentRole.CONSERVATIVE_DEBATOR,
                    temperature=0.5,
                ))

            # Phase 4: 决策层
            elif agent_id == "trader":
                return TraderAgent()
            elif agent_id == "portfolio_manager":
                return PortfolioManagerAgent()

            # 宏观分析
            elif agent_id == "macro_analyst":
                return MacroAnalysisAgent()

            else:
                logger.warning(f"Unknown agent_id: {agent_id}")
                return None

        except Exception as e:
            logger.error(
                f"Error creating agent instance for {agent_id}: {e}",
                exc_info=True,
            )
            return None

    @classmethod
    def get_config(cls, agent_id: str) -> Optional[SubagentConfig]:
        """获取Subagent配置"""
        return cls.SUBAGENT_CONFIGS.get(agent_id)

    @classmethod
    def list_subagents(cls, enabled_only: bool = False) -> List[str]:
        """列出所有Subagent ID"""
        if enabled_only:
            return [
                agent_id
                for agent_id, config in cls.SUBAGENT_CONFIGS.items()
                if config.enabled
            ]
        return list(cls.SUBAGENT_CONFIGS.keys())

    @classmethod
    def get_subagents_by_type(cls, agent_type: str) -> List[str]:
        """按类型获取Subagent ID列表"""
        return [
            agent_id
            for agent_id, config in cls.SUBAGENT_CONFIGS.items()
            if config.agent_type == agent_type and config.enabled
        ]

    @classmethod
    def get_available_subagents(cls) -> Dict[str, str]:
        """
        获取所有可用的Subagent及其状态

        Returns:
            {agent_id: status} 其中status为"enabled"或"disabled"
        """
        return {
            agent_id: "enabled" if config.enabled else "disabled"
            for agent_id, config in cls.SUBAGENT_CONFIGS.items()
        }
