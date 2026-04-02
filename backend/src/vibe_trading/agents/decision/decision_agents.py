"""
决策层 Agent

包括交易员和投资组合经理。
"""
import logging
from typing import Dict, List, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import TRADER_PROMPT, PORTFOLIO_MANAGER_PROMPT
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, setup_streaming

logger = logging.getLogger(__name__)


class TraderAgent:
    """交易员 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Trader",
            role=AgentRole.TRADER,
            temperature=0.6,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

    async def initialize(self, tool_context: ToolContext, enable_streaming: bool = True) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context
        settings = get_settings()

        model = get_model_from_config(settings.llm_config_name)

        self._agent = Agent(
            AgentOptions(
                initial_state={
                    "system_prompt": TRADER_PROMPT,
                    "model": model,
                }
            )
        )

        # 设置流式打印
        if enable_streaming:
            setup_streaming(self._agent, "Trader", "magenta")

        logger.info(f"Trader Agent initialized for {tool_context.symbol}")

    async def create_trading_plan(
        self,
        investment_recommendation: str,
        risk_assessment: Dict[str, str],
        current_price: float,
        account_balance: float,
    ) -> str:
        """创建交易计划"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        prompt = f"""Based on the research manager's recommendation, please create a detailed trading plan for {self._tool_context.symbol}.

INVESTMENT RECOMMENDATION:
{investment_recommendation}

RISK ASSESSMENT:
"""

        for role, assessment in risk_assessment.items():
            prompt += f"\n{role.upper()}:\n{assessment}\n"

        prompt += f"""
CURRENT MARKET:
Symbol: {self._tool_context.symbol}
Current Price: {current_price}
Account Balance: {account_balance} USDT

Please provide a detailed trading plan including:
1. Trading direction (LONG/SHORT)
2. Entry price and method (market/limit)
3. Position size (in USDT and quantity)
4. Stop loss price and logic
5. Take profit targets (with partial profit levels)
6. Expected holding time
7. Add-on or reduction plan
"""

        await self._agent.prompt(prompt)

        # 获取响应
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    return "".join(getattr(c, "text", str(c)) for c in content)
                return str(content)

        return "Trading plan creation failed - no response from agent"


class PortfolioManagerAgent:
    """投资组合经理 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Portfolio Manager",
            role=AgentRole.PORTFOLIO_MANAGER,
            temperature=0.4,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

    async def initialize(
        self,
        tool_context: ToolContext,
        memory: Optional[object] = None,
    ) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context
        self._memory = memory
        settings = get_settings()

        model = get_model_from_config(settings.llm_config_name)

        # 如果有记忆系统，可以在这里检索相关经验
        memory_context = ""
        if memory and hasattr(memory, "retrieve_relevant"):
            relevant_memories = memory.retrieve_relevant(
                f"{tool_context.symbol} {tool_context.interval}",
                top_k=3,
            )
            if relevant_memories:
                memory_context = f"\nRELEVANT HISTORICAL EXPERIENCES:\n" + "\n".join(relevant_memories)

        system_prompt = PORTFOLIO_MANAGER_PROMPT
        if memory_context:
            system_prompt += "\n\n" + memory_context

        self._agent = Agent(
            AgentOptions(
                initial_state={
                    "system_prompt": system_prompt,
                    "model": model,
                }
            )
        )

        # 设置流式打印
        setup_streaming(self._agent, "Portfolio Manager", "blue")

        logger.info(f"Portfolio Manager Agent initialized for {tool_context.symbol}")

    async def make_final_decision(
        self,
        analyst_reports: Dict[str, str],
        investment_plan: str,
        trading_plan: str,
        risk_debate: Dict[str, str],
        current_positions: List[Dict],
        account_balance: float,
        current_price: float,
    ) -> str:
        """做出最终交易决策"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        prompt = f"""As the Portfolio Manager, please make the final trading decision for {self._tool_context.symbol}.

ANALYST REPORTS:
"""
        for role, report in analyst_reports.items():
            prompt += f"\n{role.upper()}:\n{report}\n"

        prompt += f"""
INVESTMENT PLAN (Research Manager):
{investment_plan}

TRADING PLAN (Trader):
{trading_plan}

RISK DEBATE:
"""
        for role, assessment in risk_debate.items():
            prompt += f"\n{role.upper()}:\n{assessment}\n"

        prompt += f"""
CURRENT STATUS:
Account Balance: {account_balance} USDT
Current Price: {current_price}
Current Positions: {len(current_positions)}
"""

        for pos in current_positions:
            prompt += f"  - {pos.get('symbol', 'N/A')}: {pos.get('position_amount', 'N/A')} @ {pos.get('entry_price', 'N/A')} (PnL: {pos.get('unrealized_profit', 'N/A')})\n"

        prompt += """
Please provide your FINAL DECISION including:
1. Decision rating (STRONG BUY/BUY/WEAK BUY/HOLD/WEAK SELL/SELL/STRONG SELL)
2. Rationale for your decision
3. Specific execution instructions (if deciding to trade)
4. Risk warnings

This decision will be executed, so be specific and careful.
"""

        await self._agent.prompt(prompt)

        # 获取响应
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    return "".join(getattr(c, "text", str(c)) for c in content)
                return str(content)

        return "Final decision failed - no response from agent"


async def create_trader(tool_context: ToolContext) -> TraderAgent:
    """创建并初始化交易员"""
    trader = TraderAgent()
    await trader.initialize(tool_context)
    return trader


async def create_portfolio_manager(
    tool_context: ToolContext,
    memory: Optional[object] = None,
) -> PortfolioManagerAgent:
    """创建并初始化投资组合经理"""
    pm = PortfolioManagerAgent()
    await pm.initialize(tool_context, memory)
    return pm
