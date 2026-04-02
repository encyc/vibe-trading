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

        logger.info(f"TradingCoordinator initialized for {symbol} {interval}")

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
        log.step(f"开始分析 {self.symbol} @ ${current_price:.2f}")

        # 准备上下文
        context = await self._prepare_context(current_price)
        current_positions = current_positions or []

        # 存储所有 Agent 输出
        agent_outputs = {}

        # Phase 1: 分析师生成报告
        info("Phase 1: 分析师生成报告...", tag="Analysts")
        analyst_reports = await self._run_analysts(context)
        agent_outputs["analysts"] = analyst_reports

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
        investment_plan = await self._run_research_debate(context, analyst_reports)
        agent_outputs["investment_plan"] = investment_plan

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
        risk_assessment = await self._run_risk_assessment(
            investment_plan, current_positions, account_balance
        )
        agent_outputs["risk_assessment"] = risk_assessment

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
        trading_plan = await self._run_trader(
            investment_plan, risk_assessment, context, account_balance
        )
        agent_outputs["trading_plan"] = trading_plan

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
        final_decision = await self._run_portfolio_manager(
            analyst_reports,
            investment_plan,
            trading_plan,
            risk_assessment,
            current_positions,
            account_balance,
            context,
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

        return decision

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
                "rsi": indicators_data.rsi,
                "macd": indicators_data.macd,
                "bollinger_upper": indicators_data.bollinger_upper,
                "bollinger_lower": indicators_data.bollinger_lower,
                "sma_20": indicators_data.sma_20,
                "sma_50": indicators_data.sma_50,
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
        """运行分析师团队"""
        reports = {}

        # 技术分析师
        if "technical" in self._analysts:
            market_data = {
                "symbol": context.symbol,
                "interval": context.interval,
                "current_price": context.current_price,
                "indicators": context.indicators,
            }
            reports["technical"] = await self._analysts["technical"].analyze_with_indicators(market_data)

        # 其他分析师
        for role, analyst in self._analysts.items():
            if role == "technical":
                continue

            try:
                # 根据角色获取相应的数据
                data = await self._get_analyst_data(role, context)
                reports[role] = await analyst.analyze(data)
            except Exception as e:
                logger.warning(f"Error running {role} analyst: {e}")
                reports[role] = f"{role} analysis unavailable: {str(e)}"

        return reports

    async def _get_analyst_data(self, role: str, context: TradingContext) -> dict:
        """获取分析师所需的数据"""
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

        if role == "fundamental":
            # 基本面数据
            funding = await get_funding_rates(context.symbol)
            long_short = await get_long_short_ratio(context.symbol)
            open_interest = await get_open_interest(context.symbol)

            data["funding_rate"] = funding
            data["long_short_ratio"] = long_short
            data["open_interest"] = open_interest

        elif role == "news":
            # 新闻数据
            news_data = await get_news_sentiment(context.symbol, limit=15)
            data["news"] = news_data

        elif role == "sentiment":
            # 情绪数据
            fear_greed = await get_fear_and_greed_index()
            social = await get_social_sentiment(context.symbol)
            funding = await get_funding_rates(context.symbol)

            data["fear_greed"] = fear_greed
            data["social_sentiment"] = social
            data["funding_rate"] = funding

        return data

    async def _run_research_debate(
        self, context: TradingContext, analyst_reports: Dict[str, str]
    ) -> str:
        """运行研究员辩论"""
        if "manager" not in self._researchers:
            return "No investment plan (research manager not enabled)"

        # 准备上下文
        context_str = f"Symbol: {context.symbol}\nPrice: {context.current_price}\n"
        for role, report in analyst_reports.items():
            context_str += f"\n{role.upper()} Report:\n{report}\n"

        # 运行辩论
        bull_history = ""
        bear_history = ""

        settings = get_settings()
        for round_num in range(settings.debate_rounds):
            logger.info(f"Research debate round {round_num + 1}")
            bull_resp, bear_resp = await run_debate_round(
                self._researchers.get("bull"),
                self._researchers.get("bear"),
                context_str,
                bull_history,
                bear_history,
            )
            bull_history += f"\n{bull_resp}"
            bear_history += f"\n{bear_resp}"

        # 研究经理裁决
        investment_plan = await self._researchers["manager"].make_decision(
            context=context_str,
            bull_history=bull_history,
            bear_history=bear_history,
            analyst_reports=analyst_reports,
        )

        return investment_plan

    async def _run_risk_assessment(
        self, investment_plan: str, current_positions: List[Dict], account_balance: float
    ) -> Dict[str, str]:
        """运行风控评估"""
        if not self._risk_analysts:
            return {"error": "No risk analysts enabled"}

        return await run_risk_debate(
            self._risk_analysts.get("aggressive"),
            self._risk_analysts.get("neutral"),
            self._risk_analysts.get("conservative"),
            investment_plan,
            current_positions,
            account_balance,
            rounds=1,
        )

    async def _run_trader(
        self, investment_plan: str, risk_assessment: Dict, context: TradingContext, account_balance: float
    ) -> str:
        """运行交易员"""
        if not self._trader:
            return "No trading plan (trader not enabled)"

        return await self._trader.create_trading_plan(
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
