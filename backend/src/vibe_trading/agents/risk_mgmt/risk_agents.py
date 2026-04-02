"""
风控团队 Agent

包括激进、中立和保守风控分析师。
"""
import logging
from typing import Dict, List, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    AGGRESSIVE_DEBATOR_PROMPT,
    NEUTRAL_DEBATOR_PROMPT,
    CONSERVATIVE_DEBATOR_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, setup_streaming

logger = logging.getLogger(__name__)

# Prompt 映射
RISK_PROMPTS = {
    AgentRole.AGGRESSIVE_DEBATOR: AGGRESSIVE_DEBATOR_PROMPT,
    AgentRole.NEUTRAL_DEBATOR: NEUTRAL_DEBATOR_PROMPT,
    AgentRole.CONSERVATIVE_DEBATOR: CONSERVATIVE_DEBATOR_PROMPT,
}


class RiskAnalystAgent:
    """风控分析师 Agent"""

    def __init__(self, config: AgentConfig):
        if config.role not in RISK_PROMPTS:
            raise ValueError(f"Unsupported risk analyst role: {config.role}")

        self.config = config
        self._system_prompt = RISK_PROMPTS[config.role]
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
                    "system_prompt": self._system_prompt,
                    "model": model,
                }
            )
        )

        # 设置流式打印
        if enable_streaming:
            setup_streaming(self._agent, self.config.name, "yellow")

        logger.info(f"{self.config.name} Agent initialized for {tool_context.symbol}")

    async def assess_risk(
        self,
        investment_plan: str,
        current_positions: List[Dict],
        account_balance: float,
        debate_history: Optional[Dict[str, str]] = None,
    ) -> str:
        """评估风险"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建提示
        prompt = f"""Please assess the risk for the following investment plan on {self._tool_context.symbol}:

INVESTMENT PLAN:
{investment_plan}

CURRENT ACCOUNT STATUS:
Account Balance: {account_balance} USDT
Current Positions: {len(current_positions)}
"""

        for pos in current_positions:
            prompt += f"""
  - {pos.get('symbol', 'N/A')}: {pos.get('position_amount', 'N/A')} @ {pos.get('entry_price', 'N/A')}
    PnL: {pos.get('unrealized_profit', 'N/A')}
"""

        if debate_history:
            prompt += f"\nRISK DEBATE HISTORY:\n"
            for role, history in debate_history.items():
                prompt += f"\n{role.upper()}:\n{history}\n"

        prompt += f"""
As a {self.config.name}, please provide:
1. Your risk assessment of this plan
2. Recommended position size (5-30% of balance)
3. Stop loss percentage
4. Take profit percentage
5. Risk/reward ratio evaluation
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

        return "Risk assessment failed - no response from agent"


async def run_risk_debate(
    aggressive: RiskAnalystAgent,
    neutral: RiskAnalystAgent,
    conservative: RiskAnalystAgent,
    investment_plan: str,
    current_positions: List[Dict],
    account_balance: float,
    rounds: int = 1,
) -> Dict[str, str]:
    """执行风控辩论"""
    debate_history = {
        "aggressive": "",
        "neutral": "",
        "conservative": "",
    }

    for round_num in range(rounds):
        logger.info(f"Risk debate round {round_num + 1}")

        # 激进分析师
        aggressive_response = await aggressive.assess_risk(
            investment_plan=investment_plan,
            current_positions=current_positions,
            account_balance=account_balance,
            debate_history=debate_history if round_num > 0 else None,
        )
        debate_history["aggressive"] += f"\nRound {round_num + 1}:\n{aggressive_response}"

        # 中立分析师
        neutral_response = await neutral.assess_risk(
            investment_plan=investment_plan,
            current_positions=current_positions,
            account_balance=account_balance,
            debate_history=debate_history if round_num > 0 else None,
        )
        debate_history["neutral"] += f"\nRound {round_num + 1}:\n{neutral_response}"

        # 保守分析师
        conservative_response = await conservative.assess_risk(
            investment_plan=investment_plan,
            current_positions=current_positions,
            account_balance=account_balance,
            debate_history=debate_history if round_num > 0 else None,
        )
        debate_history["conservative"] += f"\nRound {round_num + 1}:\n{conservative_response}"

    return debate_history


async def create_risk_analyst(
    role: AgentRole,
    tool_context: ToolContext,
    config: Optional[AgentConfig] = None,
) -> RiskAnalystAgent:
    """创建并初始化风控分析师"""
    if config is None:
        config = AgentConfig(
            name=role.value.replace("_", " ").title(),
            role=role,
            temperature=0.6 if role == AgentRole.AGGRESSIVE_DEBATOR else 0.5,
        )

    analyst = RiskAnalystAgent(config)
    await analyst.initialize(tool_context)
    return analyst
