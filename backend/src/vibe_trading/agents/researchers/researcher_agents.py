"""
研究员团队 Agent

包括看涨研究员、看跌研究员和研究经理。
"""
import logging
from typing import Dict, List, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    BULL_RESEARCHER_PROMPT,
    BEAR_RESEARCHER_PROMPT,
    RESEARCH_MANAGER_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, setup_streaming

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """研究员 Agent 基类"""

    def __init__(self, config: AgentConfig, system_prompt: str):
        self.config = config
        self._system_prompt = system_prompt
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
            setup_streaming(self._agent, self.config.name, "green")

        logger.info(f"{self.config.name} Agent initialized for {tool_context.symbol}")

    async def respond(
        self,
        context: str,
        debate_history: Optional[str] = None,
        opponent_argument: Optional[str] = None,
    ) -> str:
        """生成回应"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建提示
        prompt = self._build_debate_prompt(context, debate_history, opponent_argument)

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

        return "Response failed - no response from agent"

    def _build_debate_prompt(
        self,
        context: str,
        debate_history: Optional[str] = None,
        opponent_argument: Optional[str] = None,
    ) -> str:
        """构建辩论提示"""
        prompt = f"""Market Context for {self._tool_context.symbol}:

{context}

"""

        if debate_history:
            prompt += f"""
Previous Debate History:
{debate_history}

"""

        if opponent_argument:
            prompt += f"""
Opponent's Argument:
{opponent_argument}

"""

        prompt += f"""
Please provide your {self.config.role.value.replace('_', ' ')} perspective.
"""

        return prompt


class BullResearcherAgent(ResearcherAgent):
    """看涨研究员 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        config = config or AgentConfig(
            name="Bull Researcher",
            role=AgentRole.BULL_RESEARCHER,
            temperature=0.8,
        )
        super().__init__(config, BULL_RESEARCHER_PROMPT)


class BearResearcherAgent(ResearcherAgent):
    """看跌研究员 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        config = config or AgentConfig(
            name="Bear Researcher",
            role=AgentRole.BEAR_RESEARCHER,
            temperature=0.8,
        )
        super().__init__(config, BEAR_RESEARCHER_PROMPT)


class ResearchManagerAgent:
    """研究经理 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Research Manager",
            role=AgentRole.RESEARCH_MANAGER,
            temperature=0.5,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

    async def initialize(self, tool_context: ToolContext) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context
        settings = get_settings()

        model = get_model_from_config(settings.llm_config_name)

        self._agent = Agent(
            AgentOptions(
                initial_state={
                    "system_prompt": RESEARCH_MANAGER_PROMPT,
                    "model": model,
                }
            )
        )

        logger.info(f"Research Manager Agent initialized for {tool_context.symbol}")

    async def make_decision(
        self,
        context: str,
        bull_history: str,
        bear_history: str,
        analyst_reports: Dict[str, str],
    ) -> str:
        """做出投资决策"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建提示
        prompt = f"""As the Research Manager, please review all inputs and make an investment recommendation for {self._tool_context.symbol}.

MARKET CONTEXT:
{context}

ANALYST REPORTS:
"""
        for role, report in analyst_reports.items():
            prompt += f"\n{role.upper()}:\n{report}\n"

        prompt += f"""
DEBATE HISTORY:

Bull Researcher:
{bull_history}

Bear Researcher:
{bear_history}

Please provide your裁决 including:
1. Debate summary (which side was more persuasive)
2. Investment recommendation (BUY/SELL/HOLD)
3. Rationale for your decision
4. Initial investment plan (direction, target, stop loss)
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

        return "Decision failed - no response from agent"


async def run_debate_round(
    bull: BullResearcherAgent,
    bear: BearResearcherAgent,
    context: str,
    bull_history: str,
    bear_history: str,
) -> tuple:
    """执行一轮辩论"""
    from pi_logger import step, info

    step("Bull 发言...", tag="Debate")
    # Bull 回应
    bull_response = await bull.respond(
        context=context,
        debate_history=f"Bull: {bull_history}\nBear: {bear_history}",
        opponent_argument=bear_history.split("\n")[-1] if bear_history else None,
    )
    info("Bull 回应完成", tag="Bull")

    step("Bear 发言...", tag="Debate")
    # Bear 回应
    bear_response = await bear.respond(
        context=context,
        debate_history=f"Bull: {bull_history}\nBear: {bear_history}",
        opponent_argument=bull_response.split("\n")[-1] if bull_response else None,
    )
    info("Bear 回应完成", tag="Bear")

    return bull_response, bear_response
