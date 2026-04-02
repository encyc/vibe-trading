"""
基础分析师 Agent

提供分析师的通用实现。
"""
import logging
from typing import Dict, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    FUNDAMENTAL_ANALYST_PROMPT,
    NEWS_ANALYST_PROMPT,
    SENTIMENT_ANALYST_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext

logger = logging.getLogger(__name__)

# Prompt 映射
ANALYST_PROMPTS = {
    AgentRole.FUNDAMENTAL_ANALYST: FUNDAMENTAL_ANALYST_PROMPT,
    AgentRole.NEWS_ANALYST: NEWS_ANALYST_PROMPT,
    AgentRole.SENTIMENT_ANALYST: SENTIMENT_ANALYST_PROMPT,
}


class BaseAnalystAgent:
    """基础分析师 Agent"""

    def __init__(self, config: AgentConfig):
        if config.role not in ANALYST_PROMPTS:
            raise ValueError(f"Unsupported analyst role: {config.role}")

        self.config = config
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

    async def initialize(self, tool_context: ToolContext) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context
        settings = get_settings()

        model = get_model_from_config(settings.llm_config_name)

        system_prompt = ANALYST_PROMPTS[self.config.role]

        self._agent = Agent(
            AgentOptions(
                initial_state={
                    "system_prompt": system_prompt,
                    "model": model,
                }
            )
        )

        logger.info(f"{self.config.name} Agent initialized for {tool_context.symbol}")

    async def analyze(self, context_data: Dict) -> str:
        """执行分析"""
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 构建分析提示
        prompt = self._build_prompt(context_data)

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

    def _build_prompt(self, context_data: Dict) -> str:
        """构建分析提示词"""
        symbol = self._tool_context.symbol

        if self.config.role == AgentRole.FUNDAMENTAL_ANALYST:
            return self._build_fundamental_prompt(symbol, context_data)
        elif self.config.role == AgentRole.NEWS_ANALYST:
            return self._build_news_prompt(symbol, context_data)
        elif self.config.role == AgentRole.SENTIMENT_ANALYST:
            return self._build_sentiment_prompt(symbol, context_data)

        return f"Please analyze the following data for {symbol}:\n{context_data}"

    def _build_fundamental_prompt(self, symbol: str, data: Dict) -> str:
        """构建基本面分析提示"""
        prompt = f"""Please analyze the fundamental data for {symbol}:

"""

        # 添加资金费率
        if "funding_rate" in data:
            fr = data["funding_rate"]
            prompt += f"""
Funding Rate: {fr.get('funding_rate', 'N/A')}
Mark Price: {fr.get('mark_price', 'N/A')}
"""

        # 添加多空比例
        if "long_short_ratio" in data:
            lsr = data["long_short_ratio"]
            prompt += f"""
Long/Short Ratio: {lsr.get('long_short_ratio', 'N/A')}
Long Accounts: {lsr.get('long_account', 'N/A')}%
Short Accounts: {lsr.get('short_account', 'N/A')}%
"""

        # 添加持仓量
        if "open_interest" in data:
            oi = data["open_interest"]
            prompt += f"""
Open Interest: {oi.get('open_interest', 'N/A')}
Change: {oi.get('change_percent', 'N/A')}%
"""

        prompt += """

Provide your fundamental analysis including:
1. On-chain metrics assessment (1-5 scale)
2. Key fundamental factors
3. Risk factors to monitor
4. Medium to long-term outlook
"""
        return prompt

    def _build_news_prompt(self, symbol: str, data: Dict) -> str:
        """构建新闻分析提示"""
        prompt = f"""Please analyze the news and macro factors affecting {symbol}:

"""

        if "news" in data:
            news = data["news"]
            prompt += f"Recent News:\n"
            for item in news.get("news", [])[:5]:
                prompt += f"- {item.get('title', 'N/A')}\n"

        prompt += """

Provide your news analysis including:
1. Key news summary
2. Potential impact assessment (positive/negative/neutral)
3. Expected market reaction
4. Events to watch
"""
        return prompt

    def _build_sentiment_prompt(self, symbol: str, data: Dict) -> str:
        """构建情绪分析提示"""
        prompt = f"""Please analyze the market sentiment for {symbol}:

"""

        # 添加恐惧贪婪指数
        if "fear_greed" in data:
            fg = data["fear_greed"]
            prompt += f"""
Fear & Greed Index: {fg.get('value', 'N/A')}
Classification: {fg.get('classification', 'N/A')}
"""

        # 添加社交媒体情绪
        if "social_sentiment" in data:
            ss = data["social_sentiment"]
            prompt += f"""
Social Sentiment Score: {ss.get('sentiment_score', 'N/A')}
Social Mentions: {ss.get('mentions', {}).get('total', 'N/A')}
"""

        # 添加资金费率（反映情绪）
        if "funding_rate" in data:
            fr = data["funding_rate"]["funding_rate"]
            if fr > 0.01:
                sentiment = "Highly Bullish"
            elif fr > 0:
                sentiment = "Bullish"
            elif fr > -0.01:
                sentiment = "Neutral/Bearish"
            else:
                sentiment = "Highly Bearish"
            prompt += f"Funding Rate Sentiment: {sentiment} ({fr})\n"

        prompt += """

Provide your sentiment analysis including:
1. Current sentiment state (extreme fear/fear/neutral/greed/extreme_greed)
2. Sentiment trend (heating up/cooling down/stable)
3. Extreme signal warnings
4. Likelihood of sentiment reversal
"""
        return prompt


async def create_analyst(
    role: AgentRole,
    tool_context: ToolContext,
    config: Optional[AgentConfig] = None,
) -> BaseAnalystAgent:
    """创建并初始化分析师"""
    if config is None:
        config = AgentConfig(
            name=role.value.replace("_", " ").title(),
            role=role,
            temperature=0.6 if role == AgentRole.NEWS_ANALYST else 0.5,
        )

    analyst = BaseAnalystAgent(config)
    await analyst.initialize(tool_context)
    return analyst
