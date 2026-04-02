"""
技术分析师 Agent

负责技术分析，识别趋势和信号。
"""
import logging
from typing import Dict, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import TECHNICAL_ANALYST_PROMPT
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, format_market_data_for_agent, setup_streaming

logger = logging.getLogger(__name__)


class TechnicalAnalystAgent:
    """技术分析师 Agent"""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Technical Analyst",
            role=AgentRole.TECHNICAL_ANALYST,
            temperature=0.5,
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
                    "system_prompt": TECHNICAL_ANALYST_PROMPT,
                    "model": model,
                }
            )
        )

        # 设置流式打印
        if enable_streaming:
            setup_streaming(self._agent, "Technical Analyst", "cyan")

        logger.info(f"Technical Analyst Agent initialized for {tool_context.symbol}")

    async def analyze(self, market_data: Dict) -> str:
        """执行技术分析"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建分析提示
        prompt = f"""Please analyze the following market data for {self._tool_context.symbol}:

{format_market_data_for_agent(market_data)}

Provide your technical analysis including:
1. Trend direction (strong_up/up/neutral/down/strong_down)
2. Key technical signals
3. Support and resistance levels
4. Short-term outlook (4-8 hours)
"""

        # 执行分析
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

        return "Analysis failed - no response from agent"

    async def analyze_with_indicators(self, indicators_data: Dict) -> str:
        """使用指标数据进行分析"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 格式化指标数据
        ind = indicators_data.get("indicators", {})
        current_price = indicators_data.get("current_price", 0)

        indicator_text = f"""Current Price: {current_price}

Technical Indicators:
- RSI (14): {ind.get('rsi', 'N/A')}
- MACD: {ind.get('macd', 'N/A')}
- MACD Signal: {ind.get('macd_signal', 'N/A')}
- MACD Histogram: {ind.get('macd_histogram', 'N/A')}
- Bollinger Upper: {ind.get('bollinger_upper', 'N/A')}
- Bollinger Middle: {ind.get('bollinger_middle', 'N/A')}
- Bollinger Lower: {ind.get('bollinger_lower', 'N/A')}
- SMA 20: {ind.get('sma_20', 'N/A')}
- SMA 50: {ind.get('sma_50', 'N/A')}
- ATR: {ind.get('atr', 'N/A')}
"""

        prompt = f"""Analyze the technical indicators for {self._tool_context.symbol}:

{indicator_text}

Provide your technical analysis including:
1. Overall trend assessment
2. Key signals from each indicator
3. Overbought/oversold conditions
4. Support and resistance levels
5. Short-term trading recommendation
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

        return "Analysis failed - no response from agent"


async def create_technical_analyst(tool_context: ToolContext) -> TechnicalAnalystAgent:
    """创建并初始化技术分析师"""
    analyst = TechnicalAnalystAgent()
    await analyst.initialize(tool_context)
    return analyst
