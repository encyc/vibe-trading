"""
Agent 工厂基类

提供创建交易 Agent 的基础类。
"""
import logging
import sys
from typing import List, Optional
from zenagent.events import AgentEvent
from zenagent.types import TextContent, ThinkingContent
from pi_logger import get_logger

from vibe_trading.config.agent_config import AgentConfig
from vibe_trading.config.prompts import get_agent_prompt
from vibe_trading.runtime import TradingAgent

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
        #: 已打印的 thinking 字符数（增量打印，避免每次 update 重打全文）
        self._printed_thinking_len = 0

    def on_event(self, event: AgentEvent, cancel_event=None):
        """处理 Agent 事件"""
        if event.type == "message_start":
            self._buffer = ""
            self._last_printed_len = 0
            self._line_buffer = ""
            self._is_thinking = False
            self._started = True
            self._printed_thinking_len = 0
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
                    # 只打印新增部分：message_update 每次送的是完整快照
                    new_thinking = thinking_text[self._printed_thinking_len:]
                    if new_thinking:
                        self._printed_thinking_len = len(thinking_text)
                        prefix = "\n🤔 " if self._printed_thinking_len == len(new_thinking) else ""
                        sys.stdout.write(f"{prefix}{new_thinking}")
                    sys.stdout.flush()

        elif event.type == "message_end":
            if self._started and self._line_buffer:
                # 确保最后一行换行
                sys.stdout.write("\n")
                sys.stdout.flush()
            self._started = False


def setup_streaming(agent: TradingAgent, agent_name: str, color: str = "cyan") -> None:
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
        self.risk_gate = None
        self.exchange_filter_validator = None
        self.order_audit = None
        self.current_bar_open_time_ms = None


async def create_trading_agent(
    config: AgentConfig,
    tool_context: ToolContext,
    additional_tools: Optional[List] = None,
    enable_streaming: bool = False,
    agent_name: Optional[str] = None,
) -> TradingAgent:
    """
    创建交易 Agent

    Args:
        config: Agent 配置
        tool_context: 工具上下文
        additional_tools: 额外的工具列表
        enable_streaming: 是否启用流式打印
        agent_name: Agent 名称（用于流式打印）

    Returns:
        配置好的 TradingAgent 实例
    """
    # 获取 System Prompt
    system_prompt = get_agent_prompt(config.role)

    # role 可能是枚举，也可能是裸字符串（历史调用点两种都有）；归一化后
    # 既用于工具分配，也用于 runtime 的角色标识。
    role_value = config.role.value if hasattr(config.role, "value") else str(config.role)

    # 获取预定义的tools - 根据角色分配专门工具
    agent_tools: List = []
    try:
        from vibe_trading.agents.agent_tools import get_tools_for_agent

        agent_tools = get_tools_for_agent(role_value)
        logger.info(f"Loaded {len(agent_tools)} tools for {config.name} (role: {role_value})")
    except Exception as e:
        logger.warning(f"Could not load agent tools: {e}")

    # 添加额外的tools
    if additional_tools:
        agent_tools.extend(additional_tools)

    agent = TradingAgent(
        role=role_value,
        system_prompt=system_prompt,
        tools=agent_tools,
        # 温度来自 AgentConfig；迁移前这个字段从未被读取，现在是真正生效的
        temperature=config.temperature,
        max_tokens=config.max_tokens,
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
        result.append("\nLatest Candle:")
        result.append(f"  Open: {latest['open']}")
        result.append(f"  High: {latest['high']}")
        result.append(f"  Low: {latest['low']}")
        result.append(f"  Close: {latest['close']}")
        result.append(f"  Volume: {latest['volume']}")

    if "indicators" in data:
        ind = data["indicators"]
        result.append("\nTechnical Indicators:")
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
