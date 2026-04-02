"""
Agent 角色配置

定义所有 Agent 的配置，包括启用状态、模型选择等。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class AgentRole(str, Enum):
    """Agent 角色枚举"""

    # 分析师团队
    TECHNICAL_ANALYST = "technical_analyst"
    FUNDAMENTAL_ANALYST = "fundamental_analyst"
    NEWS_ANALYST = "news_analyst"
    SENTIMENT_ANALYST = "sentiment_analyst"

    # 研究员团队
    BULL_RESEARCHER = "bull_researcher"
    BEAR_RESEARCHER = "bear_researcher"
    RESEARCH_MANAGER = "research_manager"

    # 风控团队
    AGGRESSIVE_DEBATOR = "aggressive_debator"
    NEUTRAL_DEBATOR = "neutral_debator"
    CONSERVATIVE_DEBATOR = "conservative_debator"

    # 决策层
    TRADER = "trader"
    PORTFOLIO_MANAGER = "portfolio_manager"


@dataclass
class AgentConfig:
    """单个 Agent 配置"""

    name: str
    role: AgentRole
    enabled: bool = True
    model: Optional[str] = None  # 覆盖默认模型
    temperature: float = 0.7
    max_tokens: int = 2000


@dataclass
class AgentTeamConfig:
    """Agent 团队配置"""

    # 分析师团队
    technical_analyst: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Technical Analyst",
        role=AgentRole.TECHNICAL_ANALYST,
        temperature=0.5,
    ))
    fundamental_analyst: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Fundamental Analyst",
        role=AgentRole.FUNDAMENTAL_ANALYST,
        temperature=0.5,
    ))
    news_analyst: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="News Analyst",
        role=AgentRole.NEWS_ANALYST,
        temperature=0.6,
    ))
    sentiment_analyst: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Sentiment Analyst",
        role=AgentRole.SENTIMENT_ANALYST,
        temperature=0.6,
    ))

    # 研究员团队
    bull_researcher: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Bull Researcher",
        role=AgentRole.BULL_RESEARCHER,
        temperature=0.8,
    ))
    bear_researcher: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Bear Researcher",
        role=AgentRole.BEAR_RESEARCHER,
        temperature=0.8,
    ))
    research_manager: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Research Manager",
        role=AgentRole.RESEARCH_MANAGER,
        temperature=0.5,
    ))

    # 风控团队
    aggressive_debator: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Aggressive Analyst",
        role=AgentRole.AGGRESSIVE_DEBATOR,
        temperature=0.7,
    ))
    neutral_debator: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Neutral Analyst",
        role=AgentRole.NEUTRAL_DEBATOR,
        temperature=0.5,
    ))
    conservative_debator: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Conservative Analyst",
        role=AgentRole.CONSERVATIVE_DEBATOR,
        temperature=0.5,
    ))

    # 决策层
    trader: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Trader",
        role=AgentRole.TRADER,
        temperature=0.6,
    ))
    portfolio_manager: AgentConfig = field(default_factory=lambda: AgentConfig(
        name="Portfolio Manager",
        role=AgentRole.PORTFOLIO_MANAGER,
        temperature=0.4,
    ))

    def get_all_configs(self) -> Dict[AgentRole, AgentConfig]:
        """获取所有 Agent 配置"""
        return {
            AgentRole.TECHNICAL_ANALYST: self.technical_analyst,
            AgentRole.FUNDAMENTAL_ANALYST: self.fundamental_analyst,
            AgentRole.NEWS_ANALYST: self.news_analyst,
            AgentRole.SENTIMENT_ANALYST: self.sentiment_analyst,
            AgentRole.BULL_RESEARCHER: self.bull_researcher,
            AgentRole.BEAR_RESEARCHER: self.bear_researcher,
            AgentRole.RESEARCH_MANAGER: self.research_manager,
            AgentRole.AGGRESSIVE_DEBATOR: self.aggressive_debator,
            AgentRole.NEUTRAL_DEBATOR: self.neutral_debator,
            AgentRole.CONSERVATIVE_DEBATOR: self.conservative_debator,
            AgentRole.TRADER: self.trader,
            AgentRole.PORTFOLIO_MANAGER: self.portfolio_manager,
        }

    def get_enabled_configs(self) -> Dict[AgentRole, AgentConfig]:
        """获取启用的 Agent 配置"""
        return {
            role: config
            for role, config in self.get_all_configs().items()
            if config.enabled
        }

    def get_analysts(self) -> List[AgentConfig]:
        """获取分析师团队"""
        return [
            self.technical_analyst,
            self.fundamental_analyst,
            self.news_analyst,
            self.sentiment_analyst,
        ]

    def get_researchers(self) -> List[AgentConfig]:
        """获取研究员团队"""
        return [self.bull_researcher, self.bear_researcher]

    def get_risk_analysts(self) -> List[AgentConfig]:
        """获取风控团队"""
        return [
            self.aggressive_debator,
            self.neutral_debator,
            self.conservative_debator,
        ]


# 预定义的 Agent 团队配置
ANALYST_TEAM_ONLY = AgentTeamConfig(
    # 只启用分析师团队
    technical_analyst=AgentConfig(
        name="Technical Analyst",
        role=AgentRole.TECHNICAL_ANALYST,
        enabled=True,
    ),
    fundamental_analyst=AgentConfig(
        name="Fundamental Analyst",
        role=AgentRole.FUNDAMENTAL_ANALYST,
        enabled=True,
    ),
    news_analyst=AgentConfig(
        name="News Analyst",
        role=AgentRole.NEWS_ANALYST,
        enabled=True,
    ),
    sentiment_analyst=AgentConfig(
        name="Sentiment Analyst",
        role=AgentRole.SENTIMENT_ANALYST,
        enabled=True,
    ),
    # 禁用其他角色
    bull_researcher=AgentConfig(
        name="Bull Researcher",
        role=AgentRole.BULL_RESEARCHER,
        enabled=False,
    ),
    bear_researcher=AgentConfig(
        name="Bear Researcher",
        role=AgentRole.BEAR_RESEARCHER,
        enabled=False,
    ),
    research_manager=AgentConfig(
        name="Research Manager",
        role=AgentRole.RESEARCH_MANAGER,
        enabled=False,
    ),
    aggressive_debator=AgentConfig(
        name="Aggressive Analyst",
        role=AgentRole.AGGRESSIVE_DEBATOR,
        enabled=False,
    ),
    neutral_debator=AgentConfig(
        name="Neutral Analyst",
        role=AgentRole.NEUTRAL_DEBATOR,
        enabled=False,
    ),
    conservative_debator=AgentConfig(
        name="Conservative Analyst",
        role=AgentRole.CONSERVATIVE_DEBATOR,
        enabled=False,
    ),
    trader=AgentConfig(
        name="Trader",
        role=AgentRole.TRADER,
        enabled=False,
    ),
    portfolio_manager=AgentConfig(
        name="Portfolio Manager",
        role=AgentRole.PORTFOLIO_MANAGER,
        enabled=False,
    ),
)
