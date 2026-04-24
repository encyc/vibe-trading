"""
Agent 工厂基类

提供创建交易 Agent 的基础类。
"""
import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional
from pi_agent_core import Agent, AgentOptions, AgentEvent
from pi_agent_core.types import TextContent, ThinkingContent
from pi_ai.config import get_model_from_config
from pydantic import BaseModel
from pi_logger import get_logger

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import get_agent_prompt
from vibe_trading.config.settings import get_settings

logger = logging.getLogger(__name__)
log = get_logger("AgentFactory")


class StreamPrinter:
    """流式打印器 - 实时打印 LLM 输出"""

    def __init__(self, agent_name: str, color: str = "cyan"):
        self.agent_name = agent_name
        self.color = color
        self._buffer = ""
        self._last_printed_len = 0
        self._line_buffer = ""
        self._is_thinking = False
        self._started = False

    def on_event(self, event: AgentEvent):
        """处理 Agent 事件"""
        if event.type == "message_start":
            self._buffer = ""
            self._last_printed_len = 0
            self._line_buffer = ""
            self._is_thinking = False
            self._started = True
            # 不打印开始消息，直接开始流式输出

        elif event.type == "message_update":
            if not self._started:
                return

            message = event.message
            if not message or not message.content:
                return

            # 提取文本内容
            for content in message.content:
                if isinstance(content, TextContent) and content.text:
                    full_text = content.text

                    # 获取新增内容
                    new_text = full_text[self._last_printed_len:]
                    self._last_printed_len = len(full_text)
                    self._buffer = full_text

                    # 逐字符打印新增内容
                    for char in new_text:
                        if char == "\n":
                            # 换行
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            self._line_buffer = ""
                        elif char == "\r":
                            # 忽略回车
                            pass
                        else:
                            # 直接打印字符
                            sys.stdout.write(char)
                            sys.stdout.flush()
                            self._line_buffer += char

                elif isinstance(content, ThinkingContent) and content.thinking:
                    thinking_text = content.thinking
                    # Thinking 内容用灰色显示
                    sys.stdout.write(f"\n🤔 {thinking_text}")
                    sys.stdout.flush()

        elif event.type == "message_end":
            if self._started and self._line_buffer:
                # 确保最后一行换行
                sys.stdout.write("\n")
                sys.stdout.flush()
            self._started = False


def setup_streaming(agent: Agent, agent_name: str, color: str = "cyan") -> None:
    """为 Agent 设置流式打印"""
    printer = StreamPrinter(agent_name, color)
    agent.subscribe(printer.on_event)
log = get_logger("AgentFactory")


class ToolContext:
    """
    工具上下文，提供数据访问
    """

    def __init__(
        self,
        symbol: str,
        interval: str,
        storage=None,
        executor=None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.storage = storage
        self.executor = executor


async def create_trading_agent(
    config: AgentConfig,
    tool_context: ToolContext,
    additional_tools: Optional[List] = None,
    enable_streaming: bool = False,
    agent_name: Optional[str] = None,
) -> Agent:
    """
    创建交易 Agent

    Args:
        config: Agent 配置
        tool_context: 工具上下文
        additional_tools: 额外的工具列表
        enable_streaming: 是否启用流式打印
        agent_name: Agent 名称（用于流式打印）

    Returns:
        配置好的 Agent 实例
    """
    settings = get_settings()

    # ========== 改进: 使用模型路由器，工具调用时使用iflow模型 ==========
    from pi_ai.model_router import create_model_router_from_config

    model_router = create_model_router_from_config()
    model = get_model_from_config(settings.llm_config_name)

    # 获取 System Prompt
    system_prompt = get_agent_prompt(config.role)

    # ========== 改进: 添加AgentTools支持 ==========
    from pi_agent_core import AgentTool

    # 获取预定义的tools - 根据角色分配专门工具
    agent_tools: List[AgentTool] = []
    try:
        from vibe_trading.agents.agent_tools import get_tools_for_agent

        # 使用角色的值获取对应工具（config.role.value 或直接用 config.role）
        role_value = config.role.value if hasattr(config.role, 'value') else config.role
        agent_tools = get_tools_for_agent(role_value)
        logger.info(f"Loaded {len(agent_tools)} tools for {config.name} (role: {role_value})")
    except Exception as e:
        logger.warning(f"Could not load agent tools: {e}")

    # 添加额外的tools
    if additional_tools:
        agent_tools.extend(additional_tools)

    # 创建 Agent（使用模型路由器）
    agent = Agent(
        AgentOptions(
            initial_state={
                "system_prompt": system_prompt,
                "model": model,
                "model_router": model_router,  # ========== 设置模型路由器 ==========
                "tools": agent_tools,  # ========== 设置tools ==========
            }
        )
    )

    # 设置流式打印
    if enable_streaming and agent_name:
        setup_streaming(agent, agent_name)

    logger.info(f"Created {config.name} with {len(agent_tools)} tools")

    return agent


def format_market_data_for_agent(data: dict) -> str:
    """格式化市场数据供 Agent 使用"""
    if "error" in data:
        return f"Error: {data['error']}"

    result = []
    result.append(f"Symbol: {data.get('symbol', 'N/A')}")
    result.append(f"Interval: {data.get('interval', 'N/A')}")

    if "latest" in data:
        latest = data["latest"]
        result.append(f"\nLatest Candle:")
        result.append(f"  Open: {latest['open']}")
        result.append(f"  High: {latest['high']}")
        result.append(f"  Low: {latest['low']}")
        result.append(f"  Close: {latest['close']}")
        result.append(f"  Volume: {latest['volume']}")

    if "indicators" in data:
        ind = data["indicators"]
        result.append(f"\nTechnical Indicators:")
        if ind.get("rsi"):
            result.append(f"  RSI: {ind['rsi']:.2f}")
        if ind.get("macd"):
            result.append(f"  MACD: {ind['macd']:.4f}")
        if ind.get("bollinger_upper"):
            result.append(f"  Bollinger Bands: [{ind['bollinger_lower']:.2f}, {ind['bollinger_upper']:.2f}]")

    return "\n".join(result)


def create_analysis_prompt(
    symbol: str,
    market_data: dict,
    additional_context: Optional[str] = None,
) -> str:
    """创建分析用的提示词"""

    prompt = f"""Please analyze the following market data for {symbol}:

{format_market_data_for_agent(market_data)}

"""

    if additional_context:
        prompt += f"\nAdditional Context:\n{additional_context}\n"

    prompt += """
Please provide your analysis following your role's guidelines. Include:
1. Your assessment of current conditions
2. Key signals or factors you identify
3. Any risks or opportunities you see
4. Your recommendation (if applicable)
"""

    return prompt
