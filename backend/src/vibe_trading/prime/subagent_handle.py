"""
Subagent Handle - Subagent接口

统一的Subagent接口，每个Subagent通过Handle与Prime Agent通信。
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from pi_agent_core import Agent
from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage, MessageType
from vibe_trading.prime.message_channel import MessageChannel, MessagePriority
from vibe_trading.prime.models import SubagentConfig

logger = get_logger(__name__)


class SubagentHandle:
    """
    Subagent Handle - 统一的Subagent接口

    每个Subagent通过Handle与Prime Agent通信：
    - 发送分析结果到Prime Agent
    - 接收Prime Agent的指令
    - 处理错误和异常
    """

    def __init__(
        self,
        agent_id: str,
        agent: Agent,
        channel: MessageChannel,
        config: SubagentConfig,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
    ):
        """
        初始化Subagent Handle

        Args:
            agent_id: Agent ID
            agent: Agent实例
            channel: 消息通道
            config: Subagent配置
            symbol: 交易对符号
            interval: K线间隔
        """
        self.agent_id = agent_id
        self.agent = agent
        self.channel = channel
        self.config = config
        self.symbol = symbol
        self.interval = interval

        self.running = False
        self.task: Optional[asyncio.Task] = None
        self._initialized = False

        # 统计
        self.messages_sent = 0
        self.errors_count = 0

        logger.info(f"SubagentHandle initialized: {agent_id}")

    async def start(self) -> None:
        """启动Subagent"""
        if self.running:
            logger.warning(f"Subagent {self.agent_id} already running")
            return

        # 初始化Agent（如果尚未初始化）
        if not self._initialized:
            await self._initialize_agent()

        self.running = True
        self.task = asyncio.create_task(self._run())

        logger.info(f"Subagent started: {self.agent_id}", tag="SUBAGENT")

    async def _initialize_agent(self) -> None:
        """初始化Agent"""
        from vibe_trading.agents.agent_factory import ToolContext

        # 创建ToolContext
        tool_context = ToolContext(
            symbol=self.symbol,
            interval=self.interval,
        )

        # 调用Agent的initialize方法
        if hasattr(self.agent, 'initialize'):
            await self.agent.initialize(tool_context, enable_streaming=False)
            logger.info(f"Agent initialized: {self.agent_id}", tag="SUBAGENT")
            self._initialized = True
        else:
            logger.warning(f"Agent {self.agent_id} does not have initialize method")

    async def stop(self) -> None:
        """停止Subagent"""
        if not self.running:
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info(f"Subagent stopped: {self.agent_id}", tag="SUBAGENT")

    async def _run(self) -> None:
        """Subagent主循环"""
        logger.info(f"Subagent {self.agent_id} running loop started", tag="SUBAGENT")

        while self.running:
            try:
                # 执行agent逻辑
                result = await self._execute_agent()

                # 发送结果到Prime Agent
                await self.send_result(result)

                # 等待下一次触发
                await self._wait_for_next_trigger()

            except asyncio.CancelledError:
                logger.info(f"Subagent {self.agent_id} cancelled")
                break

            except Exception as e:
                self.errors_count += 1
                logger.error(
                    f"Subagent {self.agent_id} error: {e}",
                    exc_info=True,
                    tag="SUBAGENT",
                )

                # 发送错误消息
                await self.send_error(str(e))

                # 错误后等待一段时间
                await asyncio.sleep(5)

    async def _execute_agent(self) -> Dict[str, Any]:
        """
        执行Agent逻辑

        Returns:
            执行结果
        """
        try:
            # 如果Agent有analyze方法，调用它
            if hasattr(self.agent, 'analyze'):
                # 准备市场数据
                from vibe_trading.tools.market_data_tools import get_current_price
                import asyncio

                # 获取当前价格
                try:
                    current_price = await asyncio.wait_for(
                        get_current_price(self.symbol),
                        timeout=5.0
                    )
                except Exception as e:
                    logger.warning(f"Failed to get current price: {e}", tag="SUBAGENT")
                    current_price = None

                # 准备市场数据
                market_data = {
                    "symbol": self.symbol,
                    "interval": self.interval,
                    "current_price": current_price,
                }

                # 调用analyze方法
                result = await self.agent.analyze(market_data)

                return {
                    "agent_id": self.agent_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "success",
                    "data": {
                        "analysis": result,
                        "current_price": current_price,
                    },
                }

            else:
                # 如果没有analyze方法，返回状态消息
                return {
                    "agent_id": self.agent_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "success",
                    "data": {
                        "message": f"{self.agent_id} is running",
                        "health": "ok",
                    },
                }

        except Exception as e:
            logger.error(
                f"Error executing agent {self.agent_id}: {e}",
                exc_info=True,
                tag="SUBAGENT",
            )
            return {
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e),
            }

    async def send_result(
        self,
        result: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> None:
        """
        发送结果到Prime Agent

        Args:
            result: 执行结果
            priority: 消息优先级
        """
        message = AgentMessage(
            message_id=f"{self.agent_id}_{datetime.now().timestamp()}",
            correlation_id=f"{self.agent_id}_corr",
            sender=self.agent_id,
            receiver="prime_agent",
            message_type=self._get_message_type(),
            content=result,
            timestamp=datetime.now(),
            metadata={"priority": priority.value},
        )

        success = await self.channel.put(message, priority)

        if success:
            self.messages_sent += 1
            logger.info(
                f"Subagent {self.agent_id} sent: {message.message_type.value}",
                tag="SUBAGENT",
            )
        else:
            logger.warning(
                f"Subagent {self.agent_id} failed to send message",
                tag="SUBAGENT",
            )

    async def send_error(
        self,
        error_message: str,
    ) -> None:
        """
        发送错误到Prime Agent

        Args:
            error_message: 错误消息
        """
        message = AgentMessage(
            message_id=f"{self.agent_id}_error_{datetime.now().timestamp()}",
            correlation_id=f"{self.agent_id}_error_corr",
            sender=self.agent_id,
            receiver="prime_agent",
            message_type=MessageType.ERROR,
            content={
                "error": error_message,
                "agent_id": self.agent_id,
                "timestamp": datetime.now().isoformat(),
            },
            timestamp=datetime.now(),
            metadata={"priority": MessagePriority.HIGH.value},
        )

        await self.channel.put(message, MessagePriority.HIGH)

    async def send_message(
        self,
        message_type: MessageType,
        content: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> None:
        """
        发送消息到Prime Agent

        Args:
            message_type: 消息类型
            content: 消息内容
            priority: 优先级
        """
        message = AgentMessage(
            message_id=f"{self.agent_id}_{datetime.now().timestamp()}",
            correlation_id=f"{self.agent_id}_corr",
            sender=self.agent_id,
            receiver="prime_agent",
            message_type=message_type,
            content=content,
            timestamp=datetime.now(),
            metadata={"priority": priority.value},
        )

        await self.channel.put(message, priority)

    def _get_message_type(self) -> MessageType:
        """获取Agent对应的消息类型"""
        # 根据agent_id映射到消息类型
        mapping = {
            "technical_analyst": MessageType.TECHNICAL_ANALYSIS,
            "fundamental_analyst": MessageType.FUNDAMENTAL_ANALYSIS,
            "news_analyst": MessageType.NEWS_ANALYSIS,
            "sentiment_analyst": MessageType.SENTIMENT_ANALYSIS,
            "bull_researcher": MessageType.BULL_ARGUMENT,
            "bear_researcher": MessageType.BEAR_ARGUMENT,
            "research_manager": MessageType.RESEARCH_RECOMMENDATION,
            "aggressive_risk_analyst": MessageType.RISK_ASSESSMENT,
            "neutral_risk_analyst": MessageType.RISK_ASSESSMENT,
            "conservative_risk_analyst": MessageType.RISK_ASSESSMENT,
            "trader": MessageType.TRADING_PLAN,
            "portfolio_manager": MessageType.PORTFOLIO_DECISION,
            "macro_analyst": MessageType.MACRO_ANALYSIS,
        }

        return mapping.get(self.agent_id, MessageType.ANALYSIS_REPORT)

    async def _wait_for_next_trigger(self) -> None:
        """等待下一次触发"""
        # 根据agent类型决定触发条件
        # 例如：宏观分析师每小时触发一次，技术分析师每K线触发一次

        # 简化版本：根据agent类型设置不同间隔
        intervals = {
            "macro_analyst": 300,  # 5分钟
            "technical_analyst": 15,  # 15秒
            "bull_researcher": 20,
            "bear_researcher": 20,
            "research_manager": 30,
            "aggressive_risk_analyst": 25,
            "neutral_risk_analyst": 25,
            "conservative_risk_analyst": 25,
            "trader": 10,  # 10秒
            "portfolio_manager": 30,
        }

        interval = intervals.get(self.agent_id, 30)  # 默认30秒
        await asyncio.sleep(interval)

    async def get_stats(self) -> Dict[str, Any]:
        """获取Subagent统计"""
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "messages_sent": self.messages_sent,
            "errors_count": self.errors_count,
            "config": {
                "enabled": self.config.enabled,
                "priority": self.config.priority.value,
                "can_direct_trade": self.config.can_direct_trade,
            },
        }
