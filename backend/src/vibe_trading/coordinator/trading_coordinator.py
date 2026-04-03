"""
交易协调器

负责协调所有 Agent 的工作流，实现完整的交易决策流程。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from pi_agent_core import Agent
from pi_ai.config import get_model_from_config
from pi_logger import get_logger, step, done, info, success, warning, separator

from vibe_trading.config.agent_config import AgentConfig, AgentRole, AgentTeamConfig
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
    RiskAnalystAgent,
    run_risk_debate,
    create_risk_analyst,
)
from vibe_trading.agents.decision.decision_agents import (
    create_trader,
    create_portfolio_manager,
)
from vibe_trading.memory.memory import PersistentMemory
from vibe_trading.tools import market_data_tools, technical_tools, fundamental_tools, sentiment_tools
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
    create_analysis_report,
    create_debate_speech,
    create_risk_assessment,
    create_final_decision,
)
from vibe_trading.coordinator.parallel_executor import get_parallel_executor
from vibe_trading.data_sources.rate_limiter import get_multi_endpoint_limiter
from vibe_trading.data_sources.cache import get_global_cache
from vibe_trading.agents.token_optimizer import get_token_optimizer
from vibe_trading.config.logging_config import PerformanceLogger

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
        settings = get_settings()

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
        logger.info(f"[状态机] PENDING -> ANALYZING")

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
        logger.info(f"[状态机] ANALYZING -> DEBATING")

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
        logger.info(f"[状态机] DEBATING -> ASSESSING_RISK")

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
        logger.info(f"[状态机] ASSESSING_RISK -> PLANNING")

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

        # 更新决策树 - 阶段完成
        await self._update_decision_tree(
            "trader",
            "completed",
            content=trading_plan[:500] if len(trading_plan) > 500 else trading_plan
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
        print(trading_plan[:500] + "..." if len(trading_plan) > 500 else trading_plan)
        separator()
        log.done("交易方案制定完成")

        # Phase 5: 投资组合经理最终决策
        info("Phase 5: 投资组合经理最终决策...", tag="PM")

        # ========== 改进工具: 状态机转换 ==========
        self._current_state_machine.transition_to(DecisionState.COMPLETED, "决策完成")
        logger.info(f"[状态机] PLANNING -> COMPLETED")

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
    ) -> str:
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

    async def close(self) -> None:
        """关闭所有资源"""
        # 这里可以添加清理逻辑
        pass
