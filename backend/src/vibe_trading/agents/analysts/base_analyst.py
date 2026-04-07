"""
基础分析师 Agent

提供分析师的通用实现。
"""
from typing import Dict, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config
from pi_logger import get_logger

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import (
    FUNDAMENTAL_ANALYST_PROMPT,
    NEWS_ANALYST_PROMPT,
    SENTIMENT_ANALYST_PROMPT,
)
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext

logger = get_logger(__name__)

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

        # ========== 改进: 使用create_trading_agent以获得tools支持 ==========
        from vibe_trading.agents.agent_factory import create_trading_agent

        self._agent = await create_trading_agent(
            config=self.config,
            tool_context=tool_context,
            enable_streaming=False,
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
                    response = "".join(getattr(c, "text", str(c)) for c in content)
                else:
                    response = str(content)
                
                # 记录分析结果到日志
                logger.info(f"{self.config.name} Analysis: {response}", tag="Analyst")
                
                return response

        return "Analysis failed - no response from agent"

    async def analyze_with_tools(self) -> str:
        """使用工具执行分析（不预取数据，让Agent自己调用工具）

        这是让Agent真正使用pi_agent_core工具框架的方法。
        Agent会根据需要调用get_current_price、get_fear_and_greed_index等工具。
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        symbol = self._tool_context.symbol
        interval = self._tool_context.interval

        # 构建简单提示 - 不包含预取的数据
        # Agent需要自己调用工具获取数据
        if self.config.role == AgentRole.FUNDAMENTAL_ANALYST:
            prompt = f"""请对 {symbol} ({interval}) 进行基本面分析。

请使用可用工具获取以下数据并分析：
1. 资金费率 (get_funding_rate)
2. 多空比例 (get_long_short_ratio)
3. 持仓量 (get_open_interest)

提供你的基本面分析报告，包括：
1. 链上指标评估 (1-5分)
2. 关键基本面因素
3. 需要监控的风险因素
4. 中长期展望 (用中文输出)
"""
        elif self.config.role == AgentRole.NEWS_ANALYST:
            prompt = f"""请分析影响 {symbol} 的新闻和宏观因素。

请使用可用工具获取：
1. 最新新闻情绪 (get_news_sentiment)
2. 恐惧贪婪指数 (get_fear_and_greed_index)

提供新闻分析报告，包括：
1. 重要新闻摘要
2. 潜在影响评估 (正面/负面/中性)
3. 预期市场反应
4. 需要关注的事件
"""
        elif self.config.role == AgentRole.SENTIMENT_ANALYST:
            prompt = f"""请分析 {symbol} 的市场情绪。

请使用可用工具获取：
1. 恐惧贪婪指数 (get_fear_and_greed_index)
2. 新闻情绪 (get_news_sentiment)
3. 资金费率 (get_funding_rate)
4. 多空比例 (get_long_short_ratio)
5. 持仓量 (get_open_interest)

提供情绪分析报告，包括：
1. 当前情绪状态 (极度恐惧/恐惧/中性/贪婪/极度贪婪)
2. 情绪趋势 (升温/降温/稳定)
3. 极端信号警告
4. 情绪反转可能性
"""
        else:
            prompt = f"""请分析 {symbol} ({interval}) 的市场状况。

使用可用工具获取相关数据，并提供综合分析。
"""

        # 执行分析 - Agent会根据需要调用工具
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
