"""
Prime Agent - 中央决策和监控系统

采用事件驱动的Hub-and-Spoke架构，监控所有Subagent并做出最终决策。

基于pi_agent_core.Agent框架构建，复用其状态管理、事件系统和消息处理能力。
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pi_agent_core import Agent, AgentOptions, AgentMessage as CoreAgentMessage
from pi_ai import UserMessage, TextContent
from pi_logger import get_logger, info, success, warning, error

from vibe_trading.agents.messaging import AgentMessage, MessageType
from vibe_trading.prime.message_channel import MessageChannel
from vibe_trading.prime.harness_manager import HarnessManager
from vibe_trading.prime.models import (
    Decision,
    DecisionPriority,
    EmergencyType,
    HarnessConfig,
    PrimeConfig,
    PrimeAgentConfig,
    SystemState,
    TradingAction,
)
# SubagentHandle不再需要，因为Prime Agent现在只是监控系统
# from vibe_trading.prime.subagent_handle import SubagentHandle
# SubagentFactory不再需要，因为Prime Agent现在只是监控系统
# from vibe_trading.prime.subagent_factory import SubagentFactory
# DecisionAggregator暂时不再使用，因为Prime Agent现在只是监控系统
# from vibe_trading.prime.decision_aggregator import DecisionAggregator

logger = get_logger(__name__)


class PrimeAgentStatus(str, Enum):
    """Prime Agent状态"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class PrimeAgent(Agent):
    """
    Prime Agent - 中央决策和监控

    基于pi_agent_core.Agent构建，扩展以下能力：
    1. 监控所有Subagent的消息（通过MessageChannel）
    2. 多层次约束检查（Harness Engineering）
    3. 做出最终交易决策
    4. 紧急情况下的覆盖决策
    5. 系统状态管理和监控

    架构设计：
    - 继承Agent：复用状态管理、事件系统、prompt/steer/follow_up机制
    - MessageChannel：作为Subagent消息的输入源
    - 监控循环：持续从Channel读取消息并通过prompt()处理
    - Harness：多层次约束检查
    """

    def __init__(self, config: PrimeAgentConfig):
        """
        初始化Prime Agent

        Args:
            config: Prime Agent配置
        """
        # 创建AgentOptions
        agent_options = AgentOptions(
            initial_state={
                "system_prompt": config.system_prompt,
                "model": None,  # 使用默认模型
            },
            enable_credit_tracking=config.enable_credit_tracking,
        )

        # 初始化基类Agent
        super().__init__(agent_options)

        self.config = config  # 保存完整配置
        self.prime_config = config.prime_config
        self.harness_config = config.harness_config
        self.status = PrimeAgentStatus.INITIALIZING

        # 核心组件
        self.message_channel = MessageChannel(
            maxsize=config.prime_config.max_queue_size,
            enable_dedup=True,
            enable_stats=True,
        )
        self.harness = HarnessManager(config=config.harness_config)

        # 决策聚合器（暂时不使用）
        # self.decision_aggregator = DecisionAggregator(min_signals=3)

        # 系统状态
        self.system_state = SystemState()

        # 紧急Agent（用于紧急情况下的直接调用）
        self.emergency_agents: Dict[str, Any] = {}

        # 决策历史
        self.decision_history: List[Decision] = []

        # 控制标志
        self._monitoring_running = False
        self._monitoring_paused = False

        # 统计
        self.stats = {
            "messages_processed": 0,
            "decisions_made": 0,
            "emergency_decisions": 0,
            "constraint_violations": 0,
            "start_time": None,
        }

        # 订阅自己的事件来处理决策
        self.subscribe(self._handle_agent_event)

        logger.info(
            f"Prime Agent initialized: "
            f"queue_size={config.prime_config.max_queue_size}, "
            f"enabled_subagents={len(config.prime_config.enabled_subagents)}"
        )

    async def start(self) -> None:
        """启动Prime Agent（监控模式）"""
        logger.info("Starting Prime Agent (Monitoring Mode)...", tag="PRIME")

        self.stats["start_time"] = datetime.now()
        self.status = PrimeAgentStatus.RUNNING
        self._monitoring_running = True

        # 启动三线程交易系统
        await self._start_trading_system()

        # 初始化Subagent监控（不直接运行，只是监控）
        await self._initialize_subagent_monitors()

        # 启动监控循环
        await self._start_monitoring_loop()

    async def _start_trading_system(self) -> None:
        """启动三线程交易系统"""
        from vibe_trading.main.multi_thread_main import MultiThreadedTradingSystem

        info("Starting Multi-threaded Trading System...", tag="PRIME")

        # 创建三线程系统
        self.trading_system = MultiThreadedTradingSystem(
            symbol=self.prime_config.symbol,
            interval=self.prime_config.interval,
        )

        # 初始化系统
        await self.trading_system.initialize()

        # 启动系统
        await self.trading_system.start()

        success("Multi-threaded Trading System started", tag="PRIME")

    async def stop(self) -> None:
        """停止Prime Agent和三线程系统"""
        logger.info("Stopping Prime Agent and Trading System...", tag="PRIME")

        self.status = PrimeAgentStatus.STOPPING
        self._monitoring_running = False

        # 停止三线程系统
        if hasattr(self, 'trading_system') and self.trading_system:
            info("Stopping Trading System...", tag="PRIME")
            await self.trading_system.stop()
            success("Trading System stopped", tag="PRIME")

        # 取消当前运行的prompt
        self.abort()

        # 等待Agent完成当前操作
        await self.wait_for_idle()

        self.status = PrimeAgentStatus.STOPPED
        success("Prime Agent stopped", tag="PRIME")

    async def pause(self) -> None:
        """暂停Prime Agent"""
        logger.info("Pausing Prime Agent...", tag="PRIME")
        self._monitoring_paused = True
        self.status = PrimeAgentStatus.PAUSED

    async def resume(self) -> None:
        """恢复Prime Agent"""
        logger.info("Resuming Prime Agent...", tag="PRIME")
        self._monitoring_paused = False
        self.status = PrimeAgentStatus.RUNNING

    async def _initialize_subagent_monitors(self) -> None:
        """
        初始化Subagent监控（不直接运行，只是监控）

        Subagents在三线程系统中按5阶段流程工作，
        Prime Agent只监控它们的状态。
        """
        logger.info("Initializing Subagent monitors...", tag="PRIME")

        # 创建Subagent监控映射（用于紧急情况下的直接调用）
        # 注意：Subagents实际在三线程系统中运行，这里只是建立连接
        from vibe_trading.agents.agent_factory import ToolContext

        tool_context = ToolContext(
            symbol=self.prime_config.symbol,
            interval=self.prime_config.interval,
        )

        # 为紧急调用准备一些关键Agent
        # 这些Agent只在Prime Agent需要时才会被调用
        self.emergency_agents = {}

        # 准备技术分析师（用于紧急技术分析）
        from vibe_trading.agents.analysts.technical_analyst import TechnicalAnalystAgent

        tech_agent = TechnicalAnalystAgent()
        await tech_agent.initialize(tool_context, enable_streaming=False)
        self.emergency_agents["technical_analyst"] = tech_agent

        # 准备宏观分析师（用于紧急宏观分析）
        from vibe_trading.agents.macro_agent import MacroAnalysisAgent

        macro_agent = MacroAnalysisAgent()
        await macro_agent.initialize(tool_context)
        self.emergency_agents["macro_analyst"] = macro_agent

        info(f"Initialized {len(self.emergency_agents)} emergency agents", tag="PRIME")
        logger.info("Emergency agents ready: " + ", ".join(self.emergency_agents.keys()), tag="PRIME")

    async def _start_monitoring_loop(self) -> None:
        """
        启动监控循环

        Prime Agent作为监控者：
        1. 监控系统健康状态
        2. 监控资金、仓位、风险指标
        3. 检查紧急情况（价格暴跌、风险超标）
        4. 紧急情况下介入
        """
        logger.info("Starting monitoring loop...", tag="PRIME")

        try:
            while self._monitoring_running:
                if self._monitoring_paused:
                    await asyncio.sleep(1)
                    continue

                try:
                    # 执行定期监控检查
                    await self._monitoring_check()

                    # 等待下一次检查
                    await asyncio.sleep(self.prime_config.monitoring_interval)

                except asyncio.CancelledError:
                    logger.info("Monitoring loop cancelled")
                    break

        except Exception as e:
            logger.error(f"Monitoring loop error: {e}", exc_info=True, tag="PRIME")
            self.status = PrimeAgentStatus.ERROR
            raise

    async def _monitoring_check(self) -> None:
        """
        监控检查

        每个监控周期执行：
        1. 检查价格变动（检测暴跌/暴涨）
        2. 检查系统健康状态
        3. 检查资金和仓位
        4. 检查风险指标
        """
        try:
            # 获取当前价格
            current_price = await self._get_current_price()

            if current_price:
                # 检查价格变动
                await self._check_price_movement(current_price)

            # 检查系统健康
            await self._health_check()

            # 检查资金状态
            await self._check_financial_status()

            # 检查风险指标
            await self._check_risk_metrics()
        except Exception as e:
            logger.error(f"Error in monitoring check: {e}", exc_info=True, tag="PRIME")
            raise

    async def _get_current_price(self) -> Optional[float]:
        """获取当前价格"""
        try:
            from vibe_trading.tools.market_data_tools import get_current_price
            price_data = await get_current_price(self.prime_config.symbol)

            # get_current_price返回dict，需要提取price字段
            if isinstance(price_data, dict):
                return float(price_data.get('price', 0.0))
            return float(price_data) if price_data else None
        except Exception as e:
            logger.warning(f"Failed to get current price: {e}", tag="PRIME")
            return None

    async def _check_price_movement(self, current_price: float) -> None:
        """检查价格变动（检测紧急情况）"""
        # 确保current_price是float类型
        if isinstance(current_price, dict):
            # 如果返回的是dict，尝试提取价格
            current_price = current_price.get('price', current_price.get('value', 0.0))
        if not isinstance(current_price, (int, float)):
            logger.warning(f"Invalid current_price type: {type(current_price)}, value={current_price}", tag="PRIME")
            return

        current_price = float(current_price)

        if not hasattr(self, '_last_price') or self._last_price is None:
            self._last_price = current_price
            self._last_price_time = datetime.now()
            return

        # 确保last_price也是float类型
        if isinstance(self._last_price, dict):
            self._last_price = float(self._last_price.get('price', self._last_price.get('value', 0.0)))

        # 计算价格变化
        change_pct = (current_price - self._last_price) / self._last_price

        # 检查暴跌
        if change_pct < self.prime_config.crash_threshold:
            warning(
                f"Price crash detected: {change_pct:.2%} "
                f"({self._last_price:.2f} → {current_price:.2f})",
                tag="PRIME|EMERGENCY",
            )
            await self._handle_price_crash(current_price, change_pct)

        # 检查暴涨
        elif change_pct > self.prime_config.pump_threshold:
            warning(
                f"Price spike detected: {change_pct:.2%} "
                f"({self._last_price:.2f} → {current_price:.2f})",
                tag="PRIME|EMERGENCY",
            )
            await self._handle_price_spike(current_price, change_pct)

        # 更新最后价格
        self._last_price = current_price
        self._last_price_time = datetime.now()

    async def _handle_price_crash(self, current_price: float, change_pct: float) -> None:
        """处理价格暴跌"""
        logger.error(
            f"EMERGENCY: Price crash {change_pct:.2%}, taking protective action",
            tag="PRIME|EMERGENCY",
        )

        # 创建紧急决策
        decision = Decision(
            action=TradingAction.CLOSE_ALL,
            reason=f"Price crash detected: {change_pct:.2%}, closing all positions to protect capital",
            symbol=self.prime_config.symbol,
            confidence=1.0,
            override=True,
            priority=DecisionPriority.CRITICAL,
            timestamp=datetime.now(),
        )

        # 执行紧急决策
        await self._execute_emergency_decision(decision)

    async def _handle_price_spike(self, current_price: float, change_pct: float) -> None:
        """处理价格暴涨"""
        logger.warning(
            f"Price spike {change_pct:.2%}, recommending HOLD (don't chase)",
            tag="PRIME|EMERGENCY",
        )

        # 创建建议（不自动执行）
        decision = Decision(
            action=TradingAction.HOLD,
            reason=f"Price spike detected: {change_pct:.2%}, recommend HOLD - don't chase the pump",
            symbol=self.prime_config.symbol,
            confidence=0.8,
            override=True,
            priority=DecisionPriority.HIGH,
            timestamp=datetime.now(),
        )

        logger.info(f"Emergency recommendation: {decision.action.value} - {decision.reason}", tag="PRIME")

    async def _check_financial_status(self) -> None:
        """检查资金状态"""
        # 从共享状态获取资金信息
        from vibe_trading.coordinator.shared_state import get_shared_state_manager

        shared_state = get_shared_state_manager()

        # 检查账户余额（需要await，因为get是async方法）
        account_balance = await shared_state.get("account_balance", 10000.0)
        current_position = await shared_state.get("current_position", 0.0)

        # 更新系统状态
        self.system_state.account_balance = account_balance
        self.system_state.current_position = current_position

        # 只在状态变化时打印（避免重复日志）
        if not hasattr(self, '_last_logged_balance'):
            self._last_logged_balance = None
            self._last_logged_position = None

        balance_changed = self._last_logged_balance != account_balance
        position_changed = self._last_logged_position != current_position

        if balance_changed or position_changed:
            logger.info(
                f"Financial status: balance=${account_balance:.2f}, position={current_position:.4f}",
                tag="PRIME",
            )
            self._last_logged_balance = account_balance
            self._last_logged_position = current_position

    async def _check_risk_metrics(self) -> None:
        """检查风险指标"""
        # 从共享状态获取风险信息
        from vibe_trading.coordinator.shared_state import get_shared_state_manager

        shared_state = get_shared_state_manager()

        # 检查保证金使用率（需要await）
        margin_ratio = await shared_state.get("margin_ratio", 0.0)

        if margin_ratio > self.prime_config.margin_threshold:
            warning(
                f"Margin ratio high: {margin_ratio:.2%} > {self.prime_config.margin_threshold:.2%}",
                tag="PRIME|RISK",
            )

            # 创建减仓决策
            decision = Decision(
                action=TradingAction.REDUCE_POSITION,
                reason=f"Margin ratio too high: {margin_ratio:.2%}, reducing position",
                symbol=self.prime_config.symbol,
                confidence=0.9,
                override=True,
                priority=DecisionPriority.CRITICAL,
            )

            await self._execute_emergency_decision(decision)

    async def _process_subagent_message(self, message: AgentMessage) -> None:
        """
        处理Subagent消息

        流程：
        1. 记录消息统计
        2. 约束检查
        3. 检查紧急情况
        4. 添加信号到聚合器
        5. 尝试聚合决策

        Args:
            message: Subagent发送的消息
        """
        start_time = datetime.now()

        try:
            # 记录消息
            self.stats["messages_processed"] += 1
            self.system_state.messages_processed += 1

            logger.info(
                f"Processing: {message.message_type.value} from {message.sender}",
                tag="PRIME",
            )

            # 多层次约束检查
            if not await self.harness.check_all_constraints(message):
                self.stats["constraint_violations"] += 1
                await self._handle_constraint_violation(message)
                return

            # 检查是否需要紧急覆盖
            if await self._is_emergency_situation(message):
                decision = await self._emergency_decision(message)
                self.stats["emergency_decisions"] += 1
                await self._execute_decision(decision)
                return

            # 添加信号到聚合器
            signal = self.decision_aggregator.add_signal(message)
            if signal:
                logger.info(
                    f"Signal: {signal.agent_id} -> {signal.signal_type.value} (conf={signal.confidence:.2f})",
                    tag="PRIME|AGGREGATOR",
                )

                # 尝试聚合决策
                decision = self.decision_aggregator.aggregate()
                if decision:
                    await self._execute_decision(decision)
                    self.decision_history.append(decision)
                    self.stats["decisions_made"] += 1
                    await self.system_state.update(decision)
            else:
                # 如果无法提取信号，使用原有的Agent处理流程
                await self._prompt_agent_for_decision(message)

            # 记录处理时间
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.debug(
                f"Message processed in {processing_time:.3f}s",
                tag="PRIME",
            )

        except Exception as e:
            error(f"Error processing message: {e}", tag="PRIME")

    async def _prompt_agent_for_decision(self, message: AgentMessage) -> None:
        """
        通过Agent的prompt机制处理消息并做出决策

        这里利用pi_agent_core的完整能力：
        - prompt()：发送消息给Agent
        - agent_loop：处理消息流
        - 事件监听：通过_handle_agent_event捕获响应

        Args:
            message: Subagent消息
        """
        # 构建prompt文本
        prompt_text = self._format_message_as_prompt(message)

        try:
            # 等待Agent完成当前操作
            await self.wait_for_idle()

            # 通过prompt()发送消息，触发Agent处理
            await self.prompt(prompt_text)

            # Agent的处理结果通过事件系统异步返回
            # 实际的决策在_handle_agent_event中处理

        except RuntimeError as e:
            # Agent正在处理，使用steer发送消息
            if "already processing" in str(e):
                self._send_as_steering_message(message)
            else:
                raise

    def _format_message_as_prompt(self, message: AgentMessage) -> str:
        """
        将Subagent消息格式化为prompt文本

        Args:
            message: Subagent消息

        Returns:
            格式化的prompt文本
        """
        content = message.content

        prompt = f"""收到来自 {message.sender} 的消息 ({message.message_type.value}):

内容摘要:
{self._summarize_content(content)}

请根据此信息做出决策。考虑以下因素：
1. 此消息对当前交易策略的影响
2. 是否需要调整仓位
3. 风险评估
4. 执行时机

请返回你的决策建议（买入/卖出/持有）和理由。
"""
        return prompt

    def _summarize_content(self, content: Dict) -> str:
        """总结消息内容"""
        summary_lines = []
        for key, value in content.items():
            if isinstance(value, (int, float, str, bool)):
                summary_lines.append(f"  - {key}: {value}")
            elif isinstance(value, dict):
                summary_lines.append(f"  - {key}: [复杂数据]")
            elif isinstance(value, list):
                summary_lines.append(f"  - {key}: [列表，长度{len(value)}]")
        return "\n".join(summary_lines)

    def _send_as_steering_message(self, message: AgentMessage) -> None:
        """
        发送为steering消息（当Agent正在处理时）

        Steering消息会中断当前处理并优先处理此消息

        Args:
            message: Subagent消息
        """
        steering_msg = CoreAgentMessage(
            role="steering",
            content=[TextContent(text=self._format_message_as_prompt(message))]
        )
        self.steer(steering_msg)

    async def _handle_agent_event(self, event) -> None:
        """
        处理Agent事件

        监听Agent的输出事件，提取决策信息

        Args:
            event: Agent事件
        """
        # 处理消息完成事件
        if event.type == "message_end":
            await self._process_agent_response(event.message)

        # 处理Agent结束事件
        elif event.type == "agent_end":
            for msg in event.messages:
                await self._process_agent_response(msg)

    async def _process_agent_response(self, message: CoreAgentMessage) -> None:
        """
        处理Agent响应，提取决策

        Args:
            message: Agent响应消息
        """
        if getattr(message, "role", None) != "assistant":
            return

        # 提取文本内容
        text_content = ""
        for content in getattr(message, "content", []):
            if hasattr(content, "text"):
                text_content += content.text

        # 简化版本：从文本中提取决策
        # TODO: 实现更精确的决策提取逻辑
        decision = self._parse_decision_from_text(text_content)

        if decision:
            await self._execute_decision(decision)
            self.decision_history.append(decision)
            self.stats["decisions_made"] += 1
            await self.system_state.update(decision)

    def _parse_decision_from_text(self, text: str) -> Optional[Decision]:
        """
        从Agent响应文本中解析决策

        简化版本：基于关键词匹配

        Args:
            text: Agent响应文本

        Returns:
            解析出的决策或None
        """
        text_lower = text.lower()

        if "买入" in text or "buy" in text_lower or "做多" in text:
            return Decision(
                action=TradingAction.BUY,
                reason=f"基于Agent分析: {text[:100]}",
                confidence=0.7,
            )
        elif "卖出" in text or "sell" in text_lower or "做空" in text:
            return Decision(
                action=TradingAction.SELL,
                reason=f"基于Agent分析: {text[:100]}",
                confidence=0.7,
            )
        elif "持有" in text or "hold" in text_lower:
            return Decision(
                action=TradingAction.HOLD,
                reason=f"基于Agent分析: {text[:100]}",
                confidence=0.7,
            )

        return None

    async def _is_emergency_situation(self, message: AgentMessage) -> bool:
        """
        检查是否是紧急情况

        Args:
            message: 消息

        Returns:
            是否是紧急情况
        """
        content = message.content

        # 检查价格暴跌/暴涨
        if "price_change" in content:
            change = content["price_change"]
            if change < self.prime_config.crash_threshold:
                self.system_state.last_emergency_time = datetime.now()
                return True
            elif change > self.prime_config.pump_threshold:
                self.system_state.last_emergency_time = datetime.now()
                return True

        # 检查风险超标
        if "var_value" in content:
            var = content["var_value"]
            if var > self.prime_config.var_threshold:
                self.system_state.last_emergency_time = datetime.now()
                return True

        # 检查保证金
        if "margin_ratio" in content:
            ratio = content["margin_ratio"]
            if ratio > self.prime_config.margin_threshold:
                self.system_state.last_emergency_time = datetime.now()
                return True

        # 检查系统异常
        if message.message_type == MessageType.ERROR:
            self.system_state.last_emergency_time = datetime.now()
            return True

        return False

    async def _emergency_decision(self, message: AgentMessage) -> Decision:
        """
        紧急决策 - 覆盖Subagent建议

        紧急决策不通过Agent处理，直接执行

        Args:
            message: 触发紧急情况的消息

        Returns:
            紧急决策
        """
        emergency_type = self._classify_emergency(message)

        logger.warning(
            f"Emergency decision triggered: {emergency_type.value}",
            tag="PRIME|EMERGENCY",
        )

        if emergency_type == EmergencyType.CRASH:
            return Decision(
                action=TradingAction.CLOSE_ALL,
                reason=f"紧急情况：价格暴跌 - {message.content}",
                override=True,
                priority=DecisionPriority.CRITICAL,
                metadata={
                    "emergency_type": emergency_type.value,
                    "trigger_message": message.message_id,
                },
            )

        elif emergency_type == EmergencyType.PUMP:
            return Decision(
                action=TradingAction.HOLD,
                reason=f"紧急情况：价格暴涨 - {message.content}",
                override=True,
                priority=DecisionPriority.HIGH,
                metadata={
                    "emergency_type": emergency_type.value,
                    "trigger_message": message.message_id,
                },
            )

        elif emergency_type == EmergencyType.RISK_LIMIT:
            return Decision(
                action=TradingAction.REDUCE_POSITION,
                reason=f"紧急情况：风险超标 - {message.content}",
                override=True,
                priority=DecisionPriority.CRITICAL,
                metadata={
                    "emergency_type": emergency_type.value,
                    "trigger_message": message.message_id,
                },
            )

        elif emergency_type == EmergencyType.MARGIN_CALL:
            return Decision(
                action=TradingAction.CLOSE_ALL,
                reason=f"紧急情况：保证金不足 - {message.content}",
                override=True,
                priority=DecisionPriority.CRITICAL,
                metadata={
                    "emergency_type": emergency_type.value,
                    "trigger_message": message.message_id,
                },
            )

        else:
            return Decision(
                action=TradingAction.HOLD,
                reason=f"紧急情况：{emergency_type.value} - {message.content}",
                override=True,
                priority=DecisionPriority.HIGH,
            )

    def _classify_emergency(self, message: AgentMessage) -> EmergencyType:
        """分类紧急情况"""
        content = message.content

        if "price_change" in content:
            change = content["price_change"]
            if change < self.prime_config.crash_threshold:
                return EmergencyType.CRASH
            elif change > self.prime_config.pump_threshold:
                return EmergencyType.PUMP

        if "var_value" in content:
            return EmergencyType.RISK_LIMIT

        if "margin_ratio" in content:
            return EmergencyType.MARGIN_CALL

        if message.message_type == MessageType.ERROR:
            error_type = content.get("error_type", "unknown")
            if error_type == "network":
                return EmergencyType.NETWORK_ERROR
            elif error_type == "data":
                return EmergencyType.DATA_ANOMALY
            else:
                return EmergencyType.SYSTEM_ERROR

        return EmergencyType.SYSTEM_ERROR

    async def _execute_decision(self, decision: Decision) -> None:
        """执行决策"""
        logger.info(
            f"Executing decision: {decision.action.value} - {decision.reason}",
            tag="PRIME|DECISION",
        )

        # TODO: 实际执行决策（调用交易API等）

        if decision.action == TradingAction.BUY:
            logger.info(f"Buy order: {decision.symbol}", tag="PRIME|TRADE")
        elif decision.action == TradingAction.SELL:
            logger.info(f"Sell order: {decision.symbol}", tag="PRIME|TRADE")
        elif decision.action == TradingAction.CLOSE_ALL:
            warning("Closing all positions (emergency)", tag="PRIME|TRADE")
        elif decision.action == TradingAction.HOLD:
            logger.debug("Hold - no action", tag="PRIME|TRADE")

    async def _handle_constraint_violation(self, message: AgentMessage) -> None:
        """
        处理约束违规

        使用steer机制通知Agent当前消息被约束阻止

        Args:
            message: 违规的消息
        """
        warning(
            f"Constraint violation: {message.message_type.value} from {message.sender}",
            tag="PRIME|HARNESS",
        )

        # 通过steer通知Agent
        steering_msg = CoreAgentMessage(
            role="steering",
            content=[TextContent(
                text=f"约束违规警告: {message.message_type.value} from {message.sender} 被约束系统阻止"
            )]
        )
        self.steer(steering_msg)

    async def _periodic_check(self) -> None:
        """定期检查"""
        # 检查系统健康状态
        await self._health_check()

        # 重置每日统计（午夜）
        if datetime.now().hour == 0 and datetime.now().minute == 0:
            self.harness.reset_daily_stats()
            await self.message_channel.reset_stats()

    async def _execute_emergency_decision(self, decision: Decision) -> None:
        """
        执行紧急决策

        紧急决策可以覆盖正常流程，直接执行保护性操作。

        Args:
            decision: 紧急决策
        """
        logger.error(
            f"EXECUTING EMERGENCY DECISION: {decision.action.value} - {decision.reason}",
            tag="PRIME|EMERGENCY",
        )

        # 记录紧急决策
        self.decision_history.append(decision)
        self.stats["emergency_decisions"] = self.stats.get("emergency_decisions", 0) + 1
        self.system_state.last_emergency_time = datetime.now()

        # 根据决策类型执行操作
        if decision.action == TradingAction.CLOSE_ALL:
            # 发送平仓指令到交易系统
            await self._send_close_all_signal(decision)

        elif decision.action == TradingAction.REDUCE_POSITION:
            # 发送减仓指令
            await self._send_reduce_position_signal(decision)

        elif decision.action == TradingAction.HOLD:
            # 发送HOLD建议
            await self._send_hold_signal(decision)

        # 更新系统状态
        await self.system_state.update(decision)

    async def _send_close_all_signal(self, decision: Decision) -> None:
        """发送平仓信号到交易系统"""
        # 通过共享状态发送紧急信号
        from vibe_trading.coordinator.shared_state import get_shared_state_manager

        shared_state = get_shared_state_manager()
        await shared_state.set("emergency_signal", {
            "action": "CLOSE_ALL",
            "reason": decision.reason,
            "timestamp": datetime.now().isoformat(),
        })

        logger.error("Emergency signal sent: CLOSE ALL positions", tag="PRIME|EMERGENCY")

    async def _send_reduce_position_signal(self, decision: Decision) -> None:
        """发送减仓信号"""
        from vibe_trading.coordinator.shared_state import get_shared_state_manager

        shared_state = get_shared_state_manager()
        await shared_state.set("emergency_signal", {
            "action": "REDUCE_POSITION",
            "reason": decision.reason,
            "timestamp": datetime.now().isoformat(),
        })

        logger.error("Emergency signal sent: REDUCE POSITION", tag="PRIME|EMERGENCY")

    async def _send_hold_signal(self, decision: Decision) -> None:
        """发送HOLD建议"""
        from vibe_trading.coordinator.shared_state import get_shared_state_manager

        shared_state = get_shared_state_manager()
        shared_state.set("prime_recommendation", {
            "action": "HOLD",
            "reason": decision.reason,
            "timestamp": datetime.now().isoformat(),
        })

        logger.info("Prime recommendation sent: HOLD", tag="PRIME")

    async def _health_check(self) -> None:
        """健康检查"""
        # 检查消息队列
        queue_size = await self.message_channel.size()
        if queue_size > self.prime_config.max_queue_size * 0.9:
            warning(
                f"Message queue nearly full: {queue_size}/{self.prime_config.max_queue_size}",
                tag="PRIME|HEALTH",
            )

        # 检查约束违规率
        violation_summary = await self.harness.get_violation_summary()
        total_violations = sum(violation_summary.values())
        if total_violations > 100:
            warning(
                f"High constraint violation count: {total_violations}",
                tag="PRIME|HEALTH",
            )

    async def get_status(self) -> Dict[str, Any]:
        """获取Prime Agent状态"""
        base_status = {
            "status": self.status.value,
            "monitoring_running": self._monitoring_running,
            "monitoring_paused": self._monitoring_paused,
            "state": self.system_state.to_dict(),
            "stats": self.stats,
            "emergency_agents": list(self.emergency_agents.keys()),
            "constraint_statuses": await self.harness.get_all_constraint_statuses(),
        }

        # 添加Agent状态
        base_status["agent_state"] = {
            "is_streaming": self.state.is_streaming,
            "has_error": self.state.error is not None,
            "error": self.state.error,
            "message_count": len(self.state.messages),
        }

        return base_status

    async def get_message_stats(self) -> Optional[Dict]:
        """获取消息统计"""
        return await self.message_channel.get_stats()
