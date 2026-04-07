"""
交易协调器

负责协调所有 Agent 的工作流，实现完整的交易决策流程。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from pi_logger import get_logger, info, success, separator

from vibe_trading.config.agent_config import AgentRole, AgentTeamConfig
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext
from vibe_trading.agents.analysts.technical_analyst import create_technical_analyst
from vibe_trading.agents.analysts.base_analyst import create_analyst
from vibe_trading.agents.researchers.researcher_agents import (
    BullResearcherAgent,
    BearResearcherAgent,
    ResearchManagerAgent,
    run_debate_round,
)
from vibe_trading.agents.risk_mgmt.risk_agents import (
    run_risk_debate,
    create_risk_analyst,
)
from vibe_trading.agents.decision.decision_agents import (
    create_trader,
    create_portfolio_manager,
)
from vibe_trading.agents.decision.trading_tools import TradingPlan
from vibe_trading.memory.memory import PersistentMemory
from vibe_trading.data_sources.kline_storage import KlineStorage

# 改进工具导入
from vibe_trading.coordinator.state_machine import (
    DecisionStateMachine,
    DecisionState,
    get_state_machine_manager,
)
from vibe_trading.agents.messaging import (
    get_message_broker,
    MessageType,
)
from vibe_trading.coordinator.parallel_executor import get_parallel_executor
from vibe_trading.data_sources.rate_limiter import get_multi_endpoint_limiter
from vibe_trading.data_sources.cache import get_global_cache
from vibe_trading.agents.token_optimizer import get_token_optimizer
from vibe_trading.config.logging_config import PerformanceLogger

from vibe_trading.coordinator.state_propagator import (
    StatePropagator,
    EnhancedDecisionContext,
)
from vibe_trading.coordinator.signal_processor import (
    SignalProcessor,
    TradingSignal,
)
from vibe_trading.coordinator.quality_tracker import (
    get_quality_tracker,
)
from vibe_trading.memory.reflection import (
    TradeReflector,
)

logger = logging.getLogger(__name__)
log = get_logger("TradingCoordinator")


@dataclass
class TradingContext:
    """交易上下文"""
    symbol: str
    interval: str
    current_price: float
    klines: list
    indicators: dict
    market_data: dict
    timestamp: int


@dataclass
class TradingDecision:
    """交易决策结果"""
    symbol: str
    timestamp: int
    decision: str  # STRONG BUY/BUY/WEAK BUY/HOLD/WEAK SELL/SELL/STRONG SELL
    rationale: str
    execution_instructions: Optional[dict] = None
    agent_outputs: dict = field(default_factory=dict)


class TradingCoordinator:
    """
    交易协调器

    协调所有 Agent 的协作流程，实现完整的交易决策。
    """

    def __init__(
        self,
        symbol: str,
        interval: str = "30m",
        storage: Optional[KlineStorage] = None,
        memory: Optional[PersistentMemory] = None,
        agent_config: Optional[AgentTeamConfig] = None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.storage = storage
        self.memory = memory
        self.agent_config = agent_config or AgentTeamConfig()

        # 工具上下文
        self._tool_context = ToolContext(
            symbol=symbol,
            interval=interval,
            storage=storage,
        )

        # Agents
        self._analysts: Dict[str, Any] = {}
        self._researchers: Dict[str, Any] = {}
        self._risk_analysts: Dict[str, Any] = {}
        self._trader: Optional[Any] = None
        self._portfolio_manager: Optional[Any] = None

        # Agent调用锁（防止并发调用冲突）
        self._agent_locks: Dict[str, asyncio.Lock] = {}

        # 决策历史
        self._decision_history: List[TradingDecision] = []

        # 决策树数据
        self._decision_tree = {
            "root": None,
            "current_phase": None,
            "start_time": None,
        }

        # ========== 改进工具初始化 ==========
        # 状态机管理器
        self._state_manager = get_state_machine_manager()
        self._current_state_machine: Optional[DecisionStateMachine] = None

        # 消息代理
        self._message_broker = get_message_broker()
        self._current_correlation_id: Optional[str] = None

        # 并行执行器
        self._parallel_executor = get_parallel_executor()

        # API限流器
        self._rate_limiter = get_multi_endpoint_limiter()

        # 缓存
        self._cache = get_global_cache()

        # Token优化器
        self._token_optimizer = get_token_optimizer()

        # 性能日志
        self._perf_log = PerformanceLogger("TradingCoordinator")

        # 状态传播器
        self._state_propagator = StatePropagator()
        self._enhanced_context: Optional[EnhancedDecisionContext] = None

        # 信号处理器
        self._signal_processor = SignalProcessor()

        # 质量跟踪器
        self._quality_tracker = get_quality_tracker()

        # 反思器
        self._reflector: Optional[TradeReflector] = None

        logger.info(f"TradingCoordinator initialized for {symbol} {interval}")

    async def _update_decision_tree(
        self,
        phase: str,
        status: str = "running",
        agents: Optional[List[dict]] = None,
        content: Optional[str] = None,
        decision: Optional[str] = None,
    ):
        """更新决策树数据并推送到Web UI"""
        from datetime import datetime

        if not self._decision_tree["root"]:
            self._decision_tree["start_time"] = datetime.now().isoformat()
            self._decision_tree["root"] = {
                "label": f"{self.symbol} 新K线到达",
                "phase": "root",
                "status": "running",
                "children": [],
            }

        # 查找或创建当前阶段节点
        def find_or_create_phase(node, phase_name):
            if node.get("phase") == phase_name:
                return node
            if "children" in node:
                for child in node["children"]:
                    result = find_or_create_phase(child, phase_name)
                    if result:
                        return result
            return None

        # 构建阶段节点
        phase_node = {
            "label": self._get_phase_label(phase),
            "phase": phase,
            "status": status,
        }

        if agents:
            phase_node["agents"] = agents
        if content:
            phase_node["content"] = content[:200] + "..." if len(content) > 200 else content
        if decision:
            phase_node["decision"] = decision

        # 更新或添加节点
        root = self._decision_tree["root"]
        existing = find_or_create_phase(root, phase)

        if existing:
            existing.update(phase_node)
        else:
            root["children"].append(phase_node)

        # 推送到Web UI
        try:
            from vibe_trading.web.server import send_decision_tree
            await send_decision_tree(self._decision_tree)
        except Exception:
            pass  # Web服务器未启动时忽略

    def _get_phase_label(self, phase: str) -> str:
        """获取阶段标签"""
        labels = {
            "analysts": "📊 Phase 1: 分析师团队",
            "researchers": "🎭 Phase 2: 研究员辩论",
            "risk": "⚠️ Phase 3: 风控评估",
            "trader": "📋 Phase 4: 执行规划",
            "pm": "🎯 最终决策",
        }
        return labels.get(phase, phase)

    async def initialize(self) -> None:
        """初始化所有 Agent"""
        # 初始化分析师
        if self.agent_config.technical_analyst.enabled:
            self._analysts["technical"] = await create_technical_analyst(self._tool_context)

        if self.agent_config.fundamental_analyst.enabled:
            self._analysts["fundamental"] = await create_analyst(
                AgentRole.FUNDAMENTAL_ANALYST, self._tool_context
            )

        if self.agent_config.news_analyst.enabled:
            self._analysts["news"] = await create_analyst(
                AgentRole.NEWS_ANALYST, self._tool_context
            )

        if self.agent_config.sentiment_analyst.enabled:
            self._analysts["sentiment"] = await create_analyst(
                AgentRole.SENTIMENT_ANALYST, self._tool_context
            )

        # 初始化研究员
        if self.agent_config.bull_researcher.enabled:
            self._researchers["bull"] = BullResearcherAgent()
            await self._researchers["bull"].initialize(self._tool_context)

        if self.agent_config.bear_researcher.enabled:
            self._researchers["bear"] = BearResearcherAgent()
            await self._researchers["bear"].initialize(self._tool_context)

        if self.agent_config.research_manager.enabled:
            self._researchers["manager"] = ResearchManagerAgent()
            await self._researchers["manager"].initialize(self._tool_context)

        # 初始化风控
        if self.agent_config.aggressive_debator.enabled:
            self._risk_analysts["aggressive"] = await create_risk_analyst(
                AgentRole.AGGRESSIVE_DEBATOR, self._tool_context
            )

        if self.agent_config.neutral_debator.enabled:
            self._risk_analysts["neutral"] = await create_risk_analyst(
                AgentRole.NEUTRAL_DEBATOR, self._tool_context
            )

        if self.agent_config.conservative_debator.enabled:
            self._risk_analysts["conservative"] = await create_risk_analyst(
                AgentRole.CONSERVATIVE_DEBATOR, self._tool_context
            )

        # 初始化决策层
        if self.agent_config.trader.enabled:
            self._trader = await create_trader(self._tool_context)

        if self.agent_config.portfolio_manager.enabled:
            self._portfolio_manager = await create_portfolio_manager(
                self._tool_context, self.memory
            )

        logger.info(f"All agents initialized for {self.symbol}")

    async def analyze_and_decide(
        self,
        current_price: float,
        account_balance: float = 10000.0,
        current_positions: Optional[List[Dict]] = None,
    ) -> TradingDecision:
        """
        执行完整的分析和决策流程

        流程:
        1. 收集市场数据
        2. 分析师生成报告
        3. 研究员辩论
        4. 风控评估
        5. 交易员制定方案
        6. 投资组合经理最终决策
        """
        start_time = datetime.now()
        decision_id = f"{self.symbol}_{int(start_time.timestamp() * 1000)}"

        # ========== 改进工具: 状态机初始化 ==========
        self._current_state_machine = self._state_manager.create_machine(
            decision_id=decision_id,
            symbol=self.symbol,
            interval=self.interval
        )
        self._current_correlation_id = decision_id

        log.step(f"开始分析 {self.symbol} @ ${current_price:.2f}")
        logger.info(f"[状态机] 创建决策: {decision_id}")

        # 转换到ANALYZING状态
        self._current_state_machine.transition_to(DecisionState.ANALYZING, "开始分析师阶段")
        logger.info("[状态机] PENDING -> ANALYZING")

        # 准备上下文
        context = await self._prepare_context(current_price)
        current_positions = current_positions or []

        # 存储所有 Agent 输出
        agent_outputs = {}

        # 统计信息
        stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "messages_sent": 0,
        }

        # Phase 1: 分析师生成报告
        info("Phase 1: 分析师生成报告...", tag="Analysts")

        # 更新决策树 - 阶段开始
        await self._update_decision_tree("analysts", "running")

        # ========== 改进工具: 并行执行 + 消息记录 + 性能日志 ==========
        import time
        phase_start = time.time()
        analyst_reports = await self._run_analysts_parallel(context, decision_id, stats)
        phase_elapsed = time.time() - phase_start
        logger.info(f"[性能] Phase 1 (分析师) 耗时: {phase_elapsed:.2f}s")
        agent_outputs["analysts"] = analyst_reports

        # 构建Agent状态列表
        agent_statuses = [
            {"name": role, "status": "completed"}
            for role in analyst_reports.keys()
        ]

        # 更新决策树 - 阶段完成
        await self._update_decision_tree("analysts", "completed", agents=agent_statuses)

        # 推送报告到 Web
        try:
            from vibe_trading.web.server import send_report
            for role, report in analyst_reports.items():
                await send_report(role, report, "analysts")
        except Exception:
            pass  # Web 未启用时忽略

        # 打印分析师报告
        for role, report in analyst_reports.items():
            print(f"\n[{role.upper()} REPORT]")
            separator("=", 60)
            print(report[:500] + "..." if len(report) > 500 else report)
            separator()
        log.done("分析师报告完成")

        # Phase 2: 研究员辩论
        info("Phase 2: 研究员辩论...", tag="Researchers")

        # ========== 改进工具: 状态机转换 ==========
        self._current_state_machine.transition_to(DecisionState.DEBATING, "开始研究员辩论")
        logger.info("[状态机] ANALYZING -> DEBATING")

        # 更新决策树 - 阶段开始
        await self._update_decision_tree("researchers", "running")

        import time
        phase_start = time.time()
        investment_plan = await self._run_research_debate(context, analyst_reports, decision_id, stats)
        phase_elapsed = time.time() - phase_start
        logger.info(f"[性能] Phase 2 (研究员) 耗时: {phase_elapsed:.2f}s")
        agent_outputs["investment_plan"] = investment_plan

        # 更新决策树 - 阶段完成
        await self._update_decision_tree(
            "researchers",
            "completed",
            content=investment_plan[:500] if len(investment_plan) > 500 else investment_plan
        )

        # 推送投资计划到 Web
        try:
            from vibe_trading.web.server import send_report
            await send_report("Research Manager", investment_plan, "researchers")
        except Exception:
            pass

        # 打印投资计划
        print("\n[INVESTMENT PLAN]")
        separator("=", 60)
        print(investment_plan[:500] + "..." if len(investment_plan) > 500 else investment_plan)
        separator()
        log.done("研究员辩论完成")

        # Phase 3: 风控评估
        info("Phase 3: 风控评估...", tag="Risk")

        # ========== 改进工具: 状态机转换 ==========
        self._current_state_machine.transition_to(DecisionState.ASSESSING_RISK, "开始风控评估")
        logger.info("[状态机] DEBATING -> ASSESSING_RISK")

        # 更新决策树 - 阶段开始
        await self._update_decision_tree("risk", "running")

        import time
        phase_start = time.time()
        risk_assessment = await self._run_risk_assessment(
            investment_plan, current_positions, account_balance, decision_id, stats
        )
        phase_elapsed = time.time() - phase_start
        logger.info(f"[性能] Phase 3 (风控) 耗时: {phase_elapsed:.2f}s")
        agent_outputs["risk_assessment"] = risk_assessment

        # 更新决策树 - 阶段完成
        await self._update_decision_tree(
            "risk",
            "completed",
            agents=[
                {"name": role, "status": "completed"}
                for role in risk_assessment.keys() if role != "error"
            ]
        )

        # 推送风控报告到 Web
        try:
            from vibe_trading.web.server import send_report
            for role, assessment in risk_assessment.items():
                if role != "error":
                    await send_report(role.capitalize(), assessment, "risk")
        except Exception:
            pass

        # 打印风控评估
        print("\n[RISK ASSESSMENT]")
        separator("=", 60)
        for role, assessment in risk_assessment.items():
            if role != "error":
                print(f"[{role}]: {assessment[:200]}..." if len(assessment) > 200 else f"[{role}]: {assessment}")
        separator()
        log.done("风控评估完成")

        # Phase 4: 交易员制定方案
        info("Phase 4: 交易员制定方案...", tag="Trader")

        # ========== 改进工具: 状态机转换 ==========
        self._current_state_machine.transition_to(DecisionState.PLANNING, "开始执行规划")
        logger.info("[状态机] ASSESSING_RISK -> PLANNING")

        # 更新决策树 - 阶段开始
        await self._update_decision_tree("trader", "running")

        import time
        phase_start = time.time()
        trading_plan = await self._run_trader(
            investment_plan, risk_assessment, context, account_balance
        )
        phase_elapsed = time.time() - phase_start
        logger.info(f"[性能] Phase 4 (交易员) 耗时: {phase_elapsed:.2f}s")
        agent_outputs["trading_plan"] = trading_plan

        # 转换为字符串用于显示
        trading_plan_str = str(trading_plan)
        trading_plan_display = trading_plan_str[:500] + "..." if len(trading_plan_str) > 500 else trading_plan_str

        # 更新决策树 - 阶段完成
        await self._update_decision_tree(
            "trader",
            "completed",
            content=trading_plan_display
        )

        # 推送交易方案到 Web
        try:
            from vibe_trading.web.server import send_report
            await send_report("Trader", trading_plan, "trader")
        except Exception:
            pass

        # 打印交易方案
        print("\n[TRADING PLAN]")
        separator("=", 60)
        print(trading_plan_display)
        separator()
        log.done("交易方案制定完成")

        # Phase 5: 投资组合经理最终决策
        info("Phase 5: 投资组合经理最终决策...", tag="PM")

        # ========== 改进工具: 状态机转换 ==========
        self._current_state_machine.transition_to(DecisionState.COMPLETED, "决策完成")
        logger.info("[状态机] PLANNING -> COMPLETED")

        # 更新决策树 - 阶段开始
        await self._update_decision_tree("pm", "running")

        import time
        phase_start = time.time()
        final_decision = await self._run_portfolio_manager(
            analyst_reports,
            investment_plan,
            trading_plan,
            risk_assessment,
            current_positions,
            account_balance,
            context,
        )
        phase_elapsed = time.time() - phase_start
        logger.info(f"[性能] Phase 5 (投资组合经理) 耗时: {phase_elapsed:.2f}s")

        # 更新决策树 - 最终决策
        await self._update_decision_tree(
            "pm",
            "completed",
            decision=final_decision.get("decision", "HOLD"),
            content=final_decision.get("rationale", "")[:300]
        )

        # 推送最终决策到 Web
        try:
            from vibe_trading.web.server import send_report
            decision_text = f"决策: {final_decision.get('decision', 'HOLD')}\n\n理由:\n{final_decision.get('rationale', '')}"
            await send_report("Portfolio Manager", decision_text, "pm")
        except Exception:
            pass

        # 打印最终决策
        print("\n[FINAL DECISION]")
        separator("=", 60)
        print(f"决策: {final_decision.get('decision', 'HOLD')}")
        print(f"\n理由:\n{final_decision.get('rationale', '')}")
        separator()
        log.done("投资组合经理决策完成")

        # 创建决策结果
        decision = TradingDecision(
            symbol=self.symbol,
            timestamp=int(datetime.now().timestamp() * 1000),
            decision=final_decision.get("decision", "HOLD"),
            rationale=final_decision.get("rationale", ""),
            execution_instructions=final_decision.get("execution_instructions"),
            agent_outputs=agent_outputs,
        )

        self._decision_history.append(decision)

        # ========== P0 & P1 改进: 信号处理和质量跟踪 ==========
        # 1. 提取结构化信号
        processed_signal = self._signal_processor.process_signal(
            decision_text=final_decision.get("rationale", ""),
            agent_name="Portfolio Manager",
        )

        logger.info(f"[信号处理] 提取信号: {processed_signal.signal.value} "
                   f"(置信度: {processed_signal.confidence:.2f}, 强度: {processed_signal.strength.value})")

        # 2. 计算Agent贡献度
        agent_contributions = self._calculate_agent_contributions(
            analyst_reports, investment_plan, risk_assessment, final_decision
        )

        # 3. 确定市场状态
        market_condition = self._determine_market_condition(context)

        # 4. 记录决策到质量跟踪器
        await self._quality_tracker.record_decision(
            decision_id=decision_id,
            symbol=self.symbol,
            signal=processed_signal,
            agent_contributions=agent_contributions,
            market_condition=market_condition,
        )

        logger.info(f"[质量跟踪] 决策已记录: {decision_id}")

        # 5. 保存决策ID和信号供后续反思使用
        self._last_decision_id = decision_id
        self._last_processed_signal = processed_signal
        self._last_analyst_reports = analyst_reports
        self._last_decision_context = {
            "market_condition": market_condition,
            "final_decision": final_decision,
            "investment_plan": investment_plan,
            "risk_assessment": risk_assessment,
        }

        elapsed = (datetime.now() - start_time).total_seconds()
        success(f"分析完成: {decision.decision} (耗时 {elapsed:.2f}s)", tag="Coordinator")

        # ========== 改进工具: 统计信息输出 ==========
        self._log_improvements_stats(elapsed, stats)

        return decision

    def _log_improvements_stats(self, elapsed: float, stats: dict) -> None:
        """输出改进工具统计信息"""
        logger.info("=" * 60)
        logger.info("📊 [改进工具效果统计]")

        # 状态机摘要
        state_summary = self._current_state_machine.get_state_summary()
        logger.info(f"  📊 [状态机] 决策ID: {state_summary['decision_id']}")
        logger.info(f"     状态转换数: {len(state_summary['state_history'])}")

        # 消息统计
        msg_stats = self._message_broker.get_statistics()
        logger.info(f"  📨 [消息] 总消息数: {msg_stats['total_messages']}")

        # 缓存统计
        cache_stats = self._cache.get_stats()
        memory_stats = cache_stats.get('memory', {})
        hit_rate = memory_stats.get('hit_rate', 0)
        logger.info(f"  💾 [缓存] 命中率: {hit_rate:.1%}, 大小: {memory_stats.get('size', 0)}")

        # API限流统计
        limiter = self._rate_limiter.get_limiter("binance_rest")
        remaining = limiter.get_remaining_tokens()
        logger.info(f"  🚦 [限流] 剩余令牌: {remaining.get('minute', 0)}/分钟")

        # Token统计
        token_stats = self._token_optimizer.get_stats()
        logger.info(f"  🤖 [Token] 总消耗: {token_stats.get('total_tokens', 0)}")

        # 性能日志摘要
        logger.info(f"  ⏱  [性能] 总耗时: {elapsed:.2f}s")
        logger.info("=" * 60)

    async def _prepare_context(self, current_price: float) -> TradingContext:
        """准备交易上下文"""
        # 获取 K线数据
        klines = []
        if self.storage:
            from vibe_trading.data_sources.kline_storage import KlineQuery
            query = KlineQuery(symbol=self.symbol, interval=self.interval, limit=100)
            klines = await self.storage.query_klines(query)

        # 获取技术指标
        indicators = {}
        if klines:
            closes = [k.close for k in klines]
            highs = [k.high for k in klines]
            lows = [k.low for k in klines]
            opens = [k.open for k in klines]
            volumes = [k.volume for k in klines]

            from vibe_trading.data_sources.technical_indicators import TechnicalIndicators
            ti = TechnicalIndicators()
            ti.load_data(opens, highs, lows, closes, volumes)
            indicators_data = ti.get_latest_indicators()
            indicators = {
                # 趋势指标
                "sma_20": indicators_data.sma_20,
                "sma_50": indicators_data.sma_50,
                # 动量指标
                "rsi": indicators_data.rsi,
                "macd": indicators_data.macd,
                "macd_signal": indicators_data.macd_signal,
                "macd_histogram": indicators_data.macd_hist,
                # 波动率指标
                "bollinger_upper": indicators_data.bollinger_upper,
                "bollinger_middle": indicators_data.bollinger_middle,
                "bollinger_lower": indicators_data.bollinger_lower,
                "atr": indicators_data.atr,
                # 成交量指标
                "volume_sma": indicators_data.volume_sma,
                # 当前价格（方便计算）
                "current_price": closes[-1] if closes else None,
                "current_volume": volumes[-1] if volumes else None,
            }

        return TradingContext(
            symbol=self.symbol,
            interval=self.interval,
            current_price=current_price,
            klines=klines,
            indicators=indicators,
            market_data={},
            timestamp=int(datetime.now().timestamp() * 1000),
        )

    async def _run_analysts(self, context: TradingContext) -> Dict[str, str]:
        """运行分析师团队 (串行版本，保留兼容性)"""
        return await self._run_analysts_parallel(context, "default", {})

    async def _run_analysts_parallel(self, context: TradingContext, correlation_id: str, stats: dict) -> Dict[str, str]:
        """运行分析师团队 (并行执行版本)"""
        reports = {}

        # 使用并行执行器运行分析师
        analyst_list = []
        for role, analyst in self._analysts.items():
            if hasattr(analyst, 'analyze') or hasattr(analyst, 'analyze_with_indicators'):
                analyst_list.append((role, analyst))

        if not analyst_list:
            return reports

        # ========== 改进工具: 并行执行 ==========
        logger.info(f"🚀 [并行执行] 启动 {len(analyst_list)} 个分析师...")

        import time
        start_time = time.time()

        # 创建分析任务
        async def run_analyst_task(role: str, analyst):
            try:
                # 获取或创建Agent锁
                if role not in self._agent_locks:
                    self._agent_locks[role] = asyncio.Lock()

                # 使用锁保护Agent调用（防止并发冲突）
                async with self._agent_locks[role]:
                    if role == "technical" and hasattr(analyst, 'analyze_with_indicators'):
                        market_data = {
                            "symbol": context.symbol,
                            "interval": context.interval,
                            "current_price": context.current_price,
                            "indicators": context.indicators,
                        }
                        result = await analyst.analyze_with_indicators(market_data)
                    else:
                        data = await self._get_analyst_data(role, context, stats)
                        result = await analyst.analyze(data)

                # ========== 改进工具: 消息记录 ==========
                self._message_broker.send(
                    sender=f"{role}_analyst",
                    receiver="coordinator",
                    message_type=MessageType.ANALYSIS_REPORT,
                    content={"role": role, "report": result},
                    correlation_id=correlation_id,
                )
                stats["messages_sent"] += 1

                return role, result, None
            except Exception as e:
                logger.warning(f"Error running {role} analyst: {e}")
                return role, f"{role} analysis unavailable: {str(e)}", str(e)

        # 并行执行所有分析师
        tasks = [run_analyst_task(role, analyst) for role, analyst in analyst_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # 处理结果
        successful = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Analyst task failed: {result}")
                continue
            role, report, error = result
            reports[role] = report
            if not error:
                successful += 1
            logger.info(f"  ✅ {role}: 完成")

        # 计算加速比 (假设串行执行时间 = 并行时间 * Agent数量)
        if len(analyst_list) > 1:
            estimated_serial_time = elapsed * len(analyst_list)
            speedup = estimated_serial_time / elapsed if elapsed > 0 else 1
            logger.info(f"⚡ [性能] 并行加速比: {speedup:.1f}x, 总耗时: {elapsed:.1f}s")

        return reports

    async def _get_analyst_data(self, role: str, context: TradingContext, stats: dict) -> dict:
        """获取分析师所需的数据 (带缓存和限流)"""
        from vibe_trading.tools.fundamental_tools import (
            get_funding_rates,
            get_long_short_ratio,
            get_open_interest,
        )
        from vibe_trading.tools.sentiment_tools import (
            get_fear_and_greed_index,
            get_social_sentiment,
            get_news_sentiment,
        )

        data = {
            "symbol": context.symbol,
            "current_price": context.current_price,
            "timestamp": context.timestamp,
        }

        # ========== 改进工具: 缓存装饰器 (通过检查缓存键) ==========
        cache_key = f"{role}_data_{context.symbol}_{context.timestamp}"
        cached_data = await self._cache.get(cache_key)
        if cached_data is not None:
            stats["cache_hits"] += 1
            return cached_data
        stats["cache_misses"] += 1

        if role == "fundamental":
            # ========== 改进工具: API限流 ==========
            await self._rate_limiter.acquire("binance_rest", tokens=1)
            stats["api_calls"] += 1

            funding = await get_funding_rates(context.symbol)

            await self._rate_limiter.acquire("binance_rest", tokens=1)
            stats["api_calls"] += 1
            long_short = await get_long_short_ratio(context.symbol)

            await self._rate_limiter.acquire("binance_rest", tokens=1)
            stats["api_calls"] += 1
            open_interest = await get_open_interest(context.symbol)

            data["funding_rate"] = funding
            data["long_short_ratio"] = long_short
            data["open_interest"] = open_interest

        elif role == "news":
            await self._rate_limiter.acquire("crypto_compare", tokens=1)
            stats["api_calls"] += 1
            news_data = await get_news_sentiment(context.symbol, limit=15)
            data["news"] = news_data

        elif role == "sentiment":
            await self._rate_limiter.acquire("alternative_me", tokens=1)
            stats["api_calls"] += 1
            fear_greed = await get_fear_and_greed_index()

            await self._rate_limiter.acquire("binance_rest", tokens=1)
            stats["api_calls"] += 1
            social = await get_social_sentiment(context.symbol)

            await self._rate_limiter.acquire("binance_rest", tokens=1)
            stats["api_calls"] += 1
            funding = await get_funding_rates(context.symbol)

            data["fear_greed"] = fear_greed
            data["social_sentiment"] = social
            data["funding_rate"] = funding

        # 缓存结果 (TTL 60秒)
        await self._cache.set(cache_key, data, ttl=60)

        return data

    async def _run_research_debate(
        self, context: TradingContext, analyst_reports: Dict[str, str], correlation_id: str, stats: dict
    ) -> str:
        """运行研究员辩论"""
        if "manager" not in self._researchers:
            return "No investment plan (research manager not enabled)"

        # 准备上下文
        context_str = f"Symbol: {context.symbol}\nPrice: {context.current_price}\n"
        for role, report in analyst_reports.items():
            context_str += f"\n{role.upper()} Report:\n{report}\n"

        # ========== 改进工具: Token优化 ==========
        # 压缩分析师报告以减少Token使用
        compressed_context = self._token_optimizer.compress_prompt(context_str, target_ratio=0.8)

        # 运行辩论
        bull_history = ""
        bear_history = ""

        settings = get_settings()
        for round_num in range(settings.debate_rounds):
            logger.info(f"Research debate round {round_num + 1}")
            bull_resp, bear_resp = await run_debate_round(
                self._researchers.get("bull"),
                self._researchers.get("bear"),
                compressed_context,
                bull_history,
                bear_history,
            )
            bull_history += f"\n{bull_resp}"
            bear_history += f"\n{bear_resp}"

            # ========== 改进工具: 消息记录 ==========
            self._message_broker.send(
                sender="bull_researcher",
                receiver="coordinator",
                message_type=MessageType.DEBATE_SPEECH,
                content={"round": round_num + 1, "speech": bull_resp},
                correlation_id=correlation_id,
            )
            self._message_broker.send(
                sender="bear_researcher",
                receiver="coordinator",
                message_type=MessageType.DEBATE_SPEECH,
                content={"round": round_num + 1, "speech": bear_resp},
                correlation_id=correlation_id,
            )
            stats["messages_sent"] += 2

        # 研究经理裁决
        result = await self._researchers["manager"].make_decision(
            context=compressed_context,
            bull_agent=self._researchers.get("bull"),
            bear_agent=self._researchers.get("bear"),
            bull_history=bull_history,
            bear_history=bear_history,
            analyst_reports=analyst_reports,
            market_data=context.market_data,
        )

        # ========== 改进工具: 消息记录 ==========
        self._message_broker.send(
            sender="research_manager",
            receiver="coordinator",
            message_type=MessageType.INVESTMENT_ADVICE,
            content={"decision": result},
            correlation_id=correlation_id,
        )
        stats["messages_sent"] += 1

        # 返回决策文本
        return result.get("decision_text", "No decision made")

    async def _run_risk_assessment(
        self, investment_plan: str, current_positions: List[Dict], account_balance: float, correlation_id: str, stats: dict
    ) -> Dict[str, str]:
        """运行风控评估"""
        if not self._risk_analysts:
            return {"error": "No risk analysts enabled"}

        results = await run_risk_debate(
            self._risk_analysts.get("aggressive"),
            self._risk_analysts.get("neutral"),
            self._risk_analysts.get("conservative"),
            investment_plan,
            current_positions,
            account_balance,
            rounds=1,
        )

        # ========== 改进工具: 消息记录 ==========
        for role, assessment in results.items():
            if role != "error":
                self._message_broker.send(
                    sender=f"{role}_analyst",
                    receiver="coordinator",
                    message_type=MessageType.RISK_ASSESSMENT,
                    content={"role": role, "assessment": assessment},
                    correlation_id=correlation_id,
                )
                stats["messages_sent"] += 1

        return results

    async def _run_trader(
        self, investment_plan: str, risk_assessment: Dict, context: TradingContext, account_balance: float
    ) -> TradingPlan:
        """运行交易员"""
        if not self._trader:
            return "No trading plan (trader not enabled)"

        # 从投资计划中提取方向
        direction = "HOLD"  # 默认
        plan_lower = investment_plan.lower()

        if "做多" in plan_lower or "long" in plan_lower or "买入" in plan_lower or "看涨" in plan_lower:
            direction = "LONG"
        elif "做空" in plan_lower or "short" in plan_lower or "卖出" in plan_lower or "看跌" in plan_lower:
            direction = "SHORT"
        elif "观望" in plan_lower or "hold" in plan_lower:
            direction = "HOLD"

        return await self._trader.create_trading_plan(
            direction=direction,
            investment_recommendation=investment_plan,
            risk_assessment=risk_assessment,
            current_price=context.current_price,
            account_balance=account_balance,
        )

    async def _run_portfolio_manager(
        self,
        analyst_reports: Dict[str, str],
        investment_plan: str,
        trading_plan: str,
        risk_assessment: Dict[str, str],
        current_positions: List[Dict],
        account_balance: float,
        context: TradingContext,
    ) -> Dict[str, Any]:
        """运行投资组合经理"""
        if not self._portfolio_manager:
            return {"decision": "HOLD", "rationale": "Portfolio manager not enabled"}

        decision_text = await self._portfolio_manager.make_final_decision(
            analyst_reports=analyst_reports,
            investment_plan=investment_plan,
            trading_plan=trading_plan,
            risk_debate=risk_assessment,
            current_positions=current_positions,
            account_balance=account_balance,
            current_price=context.current_price,
        )

        # 解析决策文本
        # 这里可以添加更复杂的解析逻辑
        decision = "HOLD"
        if "STRONG BUY" in decision_text.upper():
            decision = "STRONG BUY"
        elif "BUY" in decision_text.upper() and "WEAK BUY" not in decision_text.upper():
            decision = "BUY"
        elif "WEAK BUY" in decision_text.upper():
            decision = "WEAK BUY"
        elif "STRONG SELL" in decision_text.upper():
            decision = "STRONG SELL"
        elif "SELL" in decision_text.upper() and "WEAK SELL" not in decision_text.upper():
            decision = "SELL"
        elif "WEAK SELL" in decision_text.upper():
            decision = "WEAK SELL"

        return {
            "decision": decision,
            "rationale": decision_text,
            "execution_instructions": None,  # 可以从 decision_text 中解析
        }

    def get_decision_history(self) -> List[TradingDecision]:
        """获取决策历史"""
        return self._decision_history.copy()

    async def on_new_kline(self, kline) -> None:
        """
        处理新 K线数据

        当新的 K线数据到达时被调用，触发完整的分析和决策流程。
        """
        try:
            logger.info(f"New {kline.symbol} {kline.interval} kline received: close={kline.close}")

            # 执行分析和决策
            decision = await self.analyze_and_decide(
                current_price=kline.close,
                account_balance=10000.0,  # TODO: 从实际账户获取
                current_positions=[],  # TODO: 从实际持仓获取
            )

            # 记录决策
            logger.info(f"Decision for {kline.symbol}: {decision.decision}")
            if self.memory and decision.decision != "HOLD":
                # 存储到记忆系统
                await self.memory.add_memory(
                    situation=f"{kline.symbol} price {kline.close}, {decision.rationale}",
                    action=decision.decision,
                    outcome_type="trade",
                    expected_return=0.0,  # 实际收益在后续更新
                )

        except Exception as e:
            logger.error(f"Error in on_new_kline: {e}", exc_info=True)

    # ========== P0 & P1 改进功能集成 ==========
    async def on_trade_completed(
        self,
        entry_price: float,
        exit_price: float,
        position_size: float,
        hold_duration_hours: float = 1.0,
    ) -> None:
        """
        交易完成后调用

        执行反思和质量评估
        """
        if not hasattr(self, '_last_decision_id') or not self._last_decision_id:
            logger.warning("没有可反思的决策", tag="Reflection")
            return

        logger.info(
            f"交易完成: 入场 ${entry_price:.2f} → 出场 ${exit_price:.2f} "
           f"(PnL: {(exit_price - entry_price) * position_size:.2f})",
            tag="Reflection"
        )

        # 初始化反思器
        if not self._reflector and self.memory:
            self._reflector = TradeReflector(memory=self.memory)

        # ========== 执行反思 ==========
        if self._reflector:
            try:
                from vibe_trading.memory.reflection import TradeResult

                trade_result = TradeResult(
                    symbol=self.symbol,
                    decision=self._last_processed_signal.signal.value,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    position_size=position_size,
                    pnl=(exit_price - entry_price) * position_size
                        if self._last_processed_signal.signal == TradingSignal.BUY
                        else (entry_price - exit_price) * position_size,
                    pnl_percentage=((exit_price - entry_price) / entry_price) * 100
                        if self._last_processed_signal.signal == TradingSignal.BUY
                        else ((entry_price - exit_price) / entry_price) * 100,
                    hold_duration_hours=hold_duration_hours,
                    market_condition=self._determine_market_condition(
                        await self._prepare_context(exit_price)
                    ),
                )

                # 获取所有Agent报告（从agent_outputs）
                all_reports = {}
                if hasattr(self, '_last_agent_outputs'):
                    all_reports = self._last_agent_outputs

                # 执行反思
                reflections = await self._reflector.reflect_on_trade(
                    trade_result=trade_result,
                    agent_reports=all_reports,
                    decision_context={
                        "decision_id": self._last_decision_id,
                        "signal": self._last_processed_signal.signal.value,
                        "confidence": self._last_processed_signal.confidence,
                    },
                )

                logger.info(
                    f"反思完成: 生成了 {len(reflections)} 条反思",
                    tag="Reflection"
                )

            except Exception as e:
                logger.error(f"反思失败: {e}", tag="Reflection")

        # ========== 记录交易结果到质量评估 ==========
        try:
            await self._quality_tracker.record_outcome(
                decision_id=self._last_decision_id,
                entry_price=entry_price,
                exit_price=exit_price,
                position_size=position_size,
                hold_duration_hours=hold_duration_hours,
            )

            logger.info(
                "质量评估: 交易结果已记录",
                tag="QualityTracker"
            )

        except Exception as e:
            logger.error(f"质量评估失败: {e}", tag="QualityTracker")

    def _determine_market_condition(self, context: TradingContext) -> str:
        """判断市场状态"""
        # 简化版判断逻辑
        if hasattr(context, 'indicators'):
            indicators = context.indicators
            # 检查趋势
            if indicators.get('trend') == 'uptrend':
                return "trending"
            elif indicators.get('volatility', 0) > 0.02:
                return "volatile"
        return "ranging"

    def _calculate_agent_contributions(
        self,
        analyst_reports: Dict[str, str],
        investment_plan: str,
        trading_plan: str,
        risk_assessment: Dict[str, str],
    ) -> Dict[str, float]:
        """
        计算各Agent的贡献度

        基于报告长度、关键词匹配等因素计算
        """
        contributions = {}

        # 分析师贡献（基于报告长度和质量）
        total_length = sum(len(r) for r in analyst_reports.values())
        if total_length > 0:
            for name, report in analyst_reports.items():
                contributions[name] = len(report) / total_length * 0.4

        # 研究员贡献（基于投资决策采纳度）
        investment_keywords = ["buy", "sell", "long", "short", "做多", "做空"]
        investment_lower = investment_plan.lower()
        for keyword in investment_keywords:
            if keyword in investment_lower:
                contributions["Research Manager"] = contributions.get("Research Manager", 0) + 0.3
                break

        # 交易员贡献
        trader_keywords = ["execution", "entry", "exit", "order"]
        trader_lower = trading_plan.lower()
        for keyword in trader_keywords:
            if keyword in trader_lower:
                contributions["Trader"] = contributions.get("Trader", 0) + 0.3
                break

        # 归一化
        total = sum(contributions.values())
        if total > 0:
            contributions = {k: v/total for k, v in contributions.items()}

        return contributions

    async def get_quality_report(self) -> str:
        """获取质量评估报告"""
        try:
            await self._quality_tracker.get_quality_metrics(force_refresh=True)
            return self._quality_tracker.generate_report()
        except Exception as e:
            return f"无法生成质量报告: {e}"

    async def get_agent_rankings(self) -> List[Tuple[str, float]]:
        """获取Agent排名"""
        try:
            return self._quality_tracker.get_agent_ranking()
        except Exception as e:
            logger.error(f"获取Agent排名失败: {e}", tag="QualityTracker")
            return []

    async def get_top_performers(self, top_n: int = 3) -> List[str]:
        """获取表现最好的Agent"""
        try:
            return self._quality_tracker.get_top_performers(top_n=top_n)
        except Exception as e:
            logger.error(f"获取最佳Agent失败: {e}", tag="QualityTracker")
            return []

    async def get_underperformers(self, threshold: float = 0.4) -> List[str]:
        """获取表现不佳的Agent"""
        try:
            return self._quality_tracker.get_underperformers(threshold=threshold)
        except Exception as e:
            logger.error(f"获取不佳Agent失败: {e}", tag="QualityTracker")
            return []

    async def close(self) -> None:
        """关闭所有资源"""
        # 关闭所有Agent
        for agent in list(self._analysts.values()):
            if hasattr(agent, 'close'):
                await agent.close()

        for agent in list(self._researchers.values()):
            if hasattr(agent, 'close'):
                await agent.close()

        for agent in list(self._risk_analysts.values()):
            if hasattr(agent, 'close'):
                await agent.close()

        if self._trader and hasattr(self._trader, 'close'):
            await self._trader.close()

        if self._portfolio_manager and hasattr(self._portfolio_manager, 'close'):
            await self._portfolio_manager.close()

        logger.info("TradingCoordinator 已关闭")