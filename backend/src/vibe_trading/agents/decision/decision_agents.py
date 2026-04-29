"""
决策层 Agent

包括交易员和投资组合经理。
"""
import asyncio
from typing import Any, Dict, List, Optional

from pi_agent_core import Agent, AgentOptions
from pi_ai.config import get_model_from_config
from pi_logger import get_logger

from vibe_trading.config.agent_config import AgentConfig, AgentRole
from vibe_trading.config.prompts import PORTFOLIO_MANAGER_PROMPT
from vibe_trading.config.settings import get_settings
from vibe_trading.agents.agent_factory import ToolContext, setup_streaming
from vibe_trading.agents.decision.trading_tools import (
    PositionSizeCalculator,
    StopLossTakeProfitCalculator,
    ExecutionStrategyCalculator,
    DecisionFramework,
    TradingPlan,
    DecisionScorecard,
    PositionSide,
)

logger = get_logger(__name__)


class TraderAgent:
    """交易员 Agent (增强版)

    职责：基于已确定的交易方向，制定具体的执行计划。
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Trader",
            role=AgentRole.TRADER,
            temperature=0.6,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None

        # 交易工具
        self._position_size_calculator = PositionSizeCalculator()
        self._stop_loss_calculator = StopLossTakeProfitCalculator()
        self._execution_strategy_calculator = ExecutionStrategyCalculator()

    async def initialize(self, tool_context: ToolContext, enable_streaming: bool = True) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context

        # ========== 改进: 使用create_trading_agent以获得tools支持 ==========
        from vibe_trading.agents.agent_factory import create_trading_agent
        from vibe_trading.config.agent_config import AgentConfig

        config = AgentConfig(
            name="Trader",
            role="trader",
            temperature=0.3,
        )

        self._agent = await create_trading_agent(
            config=config,
            tool_context=tool_context,
            enable_streaming=enable_streaming,
            agent_name="Trader",
        )

        logger.info(f"Trader Agent initialized for {tool_context.symbol}")

    async def create_trading_plan(
        self,
        direction: str,  # LONG/SHORT (由前面阶段确定)
        investment_recommendation: str,
        risk_assessment: Dict[str, str],
        current_price: float,
        account_balance: float,
        atr: Optional[float] = None,
        kelly_fraction: Optional[float] = None,
        urgency_level: str = "normal",  # 由研究团队建议
        volatility: Optional[float] = None,
        spread_pct: Optional[float] = None,
        volume_24h: Optional[float] = None,
    ) -> TradingPlan:
        """
        创建交易执行计划

        基于已确定的交易方向，制定具体的执行方案。

        Args:
            direction: 交易方向 (由分析师团队和研究员团队确定)
            investment_recommendation: 研究经理的投资建议
            risk_assessment: 风控团队的风险评估
            current_price: 当前价格
            account_balance: 账户余额
            atr: ATR波动率
            kelly_fraction: 凯利公式仓位建议
            urgency_level: 紧急程度 (由研究团队建议)
            volatility: 波动率
            spread_pct: 买卖价差
            volume_24h: 24小时成交量
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 1. 确定仓位方向
        position_side = PositionSide.LONG if direction == "LONG" else PositionSide.SHORT

        # 2. 计算止损止盈
        sltp_levels = self._stop_loss_calculator.calculate_levels(
            entry_price=current_price,
            position_side=position_side,
            atr=atr,
            risk_reward_ratio=2.0,
            volatility_adjusted=True,
        )

        # 3. 计算仓位大小
        risk_preference = self._determine_risk_preference(risk_assessment)
        position_calc = self._position_size_calculator.calculate_position_size(
            account_balance=account_balance,
            entry_price=current_price,
            stop_loss_price=sltp_levels["stop_loss_price"],
            risk_preference=risk_preference,
            kelly_fraction=kelly_fraction,
            current_atr=atr,
        )

        # 4. 确定执行策略 (如何进场)
        execution_strategy = self._execution_strategy_calculator.determine_execution_style(
            direction=direction,
            current_price=current_price,
            volatility=volatility,
            spread_pct=spread_pct,
            volume_24h=volume_24h,
            urgency_level=urgency_level,
        )

        # 5. 构建具体入场订单
        entry_orders = self._execution_strategy_calculator.build_entry_orders(
            direction=direction,
            current_price=current_price,
            total_size_coin=position_calc["position_size_coin"],
            entry_plan=execution_strategy["entry_orders"],
        )

        # 6. 构建止损订单
        stop_loss_orders = [{
            "order_type": "stop_market",
            "trigger_price": sltp_levels["stop_loss_price"],
            "size_coin": position_calc["position_size_coin"],
            "note": "止损单",
        }]

        # 7. 构建止盈订单
        take_profit_orders = []
        for tp in sltp_levels["partial_take_profits"]:
            take_profit_orders.append({
                "order_type": "limit",
                "price": tp["price"],
                "size_coin": position_calc["position_size_coin"] * tp["size_pct"] / 100,
                "pct": tp["size_pct"],
                "note": f"第{tp['level']}批止盈({tp['size_pct']}%)",
            })

        # 8. 构建交易计划
        trading_plan = TradingPlan(
            symbol=self._tool_context.symbol,
            position_side=position_side,
            direction=direction,
            execution_style=execution_strategy["execution_style"],
            entry_orders=entry_orders,
            total_position_usdt=position_calc["position_size_usdt"],
            total_position_coin=position_calc["position_size_coin"],
            leverage=position_calc["leverage"],
            stop_loss_orders=stop_loss_orders,
            take_profit_orders=take_profit_orders,
            trailing_stop_config=sltp_levels["trailing_stop_config"],
            max_loss_usdt=position_calc["risk_amount_usdt"],
            max_loss_pct=position_calc["stop_distance_pct"],
            risk_reward_ratio=sltp_levels["risk_reward_ratio"],
            execution_notes=[
                f"执行风格: {execution_strategy['execution_style'].value}",
                f"风险偏好: {risk_preference}",
                f"止损距离: {position_calc['stop_distance_pct']}%",
                f"执行理由: {execution_strategy['reasoning']}",
            ],
        )

        # 9. 使用LLM生成详细分析
        prompt = self._build_trading_plan_prompt(
            trading_plan=trading_plan,
            investment_recommendation=investment_recommendation,
            risk_assessment=risk_assessment,
        )

        await self._agent.prompt(prompt)

        # 获取LLM响应并添加到执行说明
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    llm_response = "".join(getattr(c, "text", str(c)) for c in content)
                else:
                    llm_response = str(content)
                trading_plan.execution_notes.append(f"\nLLM分析:\n{llm_response}")
        
        # 记录交易计划到日志
        plan_summary = f"Trader Plan: {trading_plan.direction} {trading_plan.total_position_usdt} USDT @ {current_price:.2f}, " \
                     f"SL: {trading_plan.stop_loss_orders[0]['trigger_price']:.2f}, " \
                     f"TP: {[tp['price'] for tp in trading_plan.take_profit_orders]}"
        logger.info(f"{plan_summary}\nExecution Notes: {trading_plan.execution_notes}", tag="Trader")

        return trading_plan

    def _determine_risk_preference(self, risk_assessment: Dict[str, str]) -> str:
        """从风险评估中确定风险偏好"""
        risk_scores = []
        for role, assessment in risk_assessment.items():
            if "conservative" in role.lower() or "保守" in assessment:
                risk_scores.append(0)
            elif "aggressive" in role.lower() or "激进" in assessment:
                risk_scores.append(2)
            else:
                risk_scores.append(1)

        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 1

        if avg_risk <= 0.5:
            return "conservative"
        elif avg_risk >= 1.5:
            return "aggressive"
        else:
            return "moderate"

    def _build_trading_plan_prompt(
        self,
        trading_plan: TradingPlan,
        investment_recommendation: str,
        risk_assessment: Dict[str, str],
    ) -> str:
        """构建交易计划提示"""
        prompt = f"""请基于以下量化分析，为{self._tool_context.symbol}提供你的定性评估。

量化交易执行计划:
方向: {trading_plan.direction}
执行风格: {trading_plan.execution_style.value}

入场计划:
"""
        for order in trading_plan.entry_orders:
            prompt += f"  - {order['order_type']} @ {order['price']} ({order['pct']}%) {order['note']}\n"

        prompt += f"""
仓位: {trading_plan.total_position_usdt} USDT ({trading_plan.total_position_coin:.6f} coins)
杠杆: {trading_plan.leverage}x

止损: {trading_plan.stop_loss_orders[0]['trigger_price']} ({trading_plan.max_loss_pct:.2f}%)
止盈:
"""
        for tp in trading_plan.take_profit_orders:
            prompt += f"  - {tp['price']} ({tp['pct']}%) {tp['note']}\n"

        prompt += f"""
盈亏比: {trading_plan.risk_reward_ratio}:1

投资建议 (研究经理):
{investment_recommendation[:500]}...

风险评估:
"""
        for role, assessment in risk_assessment.items():
            prompt += f"\n{role.upper()}:\n{assessment[:200]}...\n"

        prompt += """
请提供你的分析:
1. 这个量化执行计划是否合理? 如有调整请说明理由
2. 对执行时机的建议
3. 任何额外的风险提示

**重要: 请使用中文输出所有分析.**
"""

        return prompt


class PortfolioManagerAgent:
    """投资组合经理 Agent

    最终决策者，负责审批交易计划并做出最终决策。
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig(
            name="Portfolio Manager",
            role=AgentRole.PORTFOLIO_MANAGER,
            temperature=0.4,
        )
        self._agent: Optional[Agent] = None
        self._tool_context: Optional[ToolContext] = None
        self._memory: Optional[object] = None
        self._execution_tool_args: Dict[str, Any] = {}

        # 决策框架
        self._decision_framework = DecisionFramework()

    async def initialize(
        self,
        tool_context: ToolContext,
        memory: Optional[object] = None,
    ) -> None:
        """初始化 Agent"""
        self._tool_context = tool_context
        self._memory = memory

        # ========== 改进: 使用模型路由器和工具 ==========
        settings = get_settings()
        model = get_model_from_config(settings.llm_config_name)

        # 获取模型路由器
        from pi_ai.model_router import create_model_router_from_config
        model_router = create_model_router_from_config()

        # 获取tools - 使用角色特定的工具集合
        agent_tools = []
        try:
            from vibe_trading.agents.agent_tools import get_execution_tools, get_tools_for_agent
            agent_tools = get_tools_for_agent("portfolio_manager")
            if getattr(tool_context, "executor", None):
                agent_tools.extend(get_execution_tools(tool_context))
            logger.info(f"Loaded {len(agent_tools)} tools for Portfolio Manager")
        except Exception as e:
            logger.warning(f"Could not load agent tools: {e}")

        # 如果有记忆系统，可以在这里检索相关经验
        memory_context = ""
        if memory and hasattr(memory, "retrieve_relevant"):
            relevant_memories = memory.retrieve_relevant(
                f"{tool_context.symbol} {tool_context.interval}",
                top_k=3,
            )
            if relevant_memories:
                memory_context = "\nRELEVANT HISTORICAL EXPERIENCES:\n" + "\n".join(relevant_memories)

        system_prompt = PORTFOLIO_MANAGER_PROMPT
        if getattr(tool_context, "executor", None):
            system_prompt += (
                "\n\nEXECUTION TOOL POLICY:\n"
                "- You are the only regular agent authorized to submit orders.\n"
                "- Call submit_trade_order only after your final decision explicitly approves a trade.\n"
                "- Do not call submit_trade_order for HOLD, WEAK_BUY, or WEAK_SELL decisions.\n"
                "- The tool is bound to the configured execution mode; Paper/Dry-run modes are safe for validation.\n"
            )
        if memory_context:
            system_prompt += "\n\n" + memory_context

        # 创建Agent并设置tools和model_router
        self._agent = Agent(
            AgentOptions(
                initial_state={
                    "system_prompt": system_prompt,
                    "model": model,
                    "model_router": model_router,  # ========== 添加模型路由器 ==========
                    "tools": agent_tools,
                }
            )
        )

        # 设置流式打印
        setup_streaming(self._agent, "Portfolio Manager", "blue")
        self._agent.subscribe(self._track_execution_tool_event)

        logger.info(f"Portfolio Manager Agent initialized for {tool_context.symbol}")

    def _track_execution_tool_event(self, event: Any) -> None:
        """Persist PM execution tool calls for per-bar web tracing."""
        event_type = getattr(event, "type", None)
        if getattr(event, "tool_name", None) == "submit_trade_order" and event_type == "tool_execution_start":
            self._execution_tool_args[event.tool_call_id] = self._to_jsonable(getattr(event, "args", {}))
            return

        if event_type != "tool_execution_end":
            return
        if getattr(event, "tool_name", None) != "submit_trade_order":
            return
        if not self._tool_context:
            return

        result = getattr(event, "result", None)
        result_details = getattr(result, "details", None) or {}

        payload = {
            "agent": "Portfolio Manager",
            "tool_name": event.tool_name,
            "tool_call_id": event.tool_call_id,
            "args": self._execution_tool_args.pop(event.tool_call_id, {}),
            "result": self._to_jsonable(result_details),
            "is_error": bool(getattr(event, "is_error", False)),
            "open_time_ms": getattr(self._tool_context, "current_bar_open_time_ms", None),
            "symbol": self._tool_context.symbol,
            "interval": self._tool_context.interval,
        }

        try:
            from vibe_trading.web.server import send_execution
            loop = asyncio.get_running_loop()
            loop.create_task(send_execution(**payload))
        except RuntimeError:
            return
        except Exception:
            return

    def _to_jsonable(self, value: Any) -> Any:
        """Convert pydantic/enums/dataclasses to web-safe JSON values."""
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._to_jsonable(item) for item in value]
        if hasattr(value, "value"):
            return value.value
        return value

    async def make_final_decision(
        self,
        analyst_reports: Dict[str, str],
        investment_plan: str,
        trading_plan: TradingPlan,
        risk_debate: Dict[str, str],
        current_positions: List[Dict],
        account_balance: float,
        current_price: float,
    ) -> Dict:
        """
        做出最终交易决策 (增强版)

        Returns:
            {
                "scorecard": DecisionScorecard,
                "decision_text": str,
                "execution_plan": Optional[TradingPlan],
            }
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # 1. 使用决策框架计算评分卡
        scorecard = self._decision_framework.calculate_decision_scorecard(
            analyst_reports=analyst_reports,
            research_recommendation={"action": trading_plan.direction, "confidence": 0.7},
            risk_assessment=risk_debate,
            current_market_data={"price": current_price, "balance": account_balance},
        )

        # 2. 如果决策是HOLD或信号较弱，直接返回
        if scorecard.recommended_action in ["HOLD", "WEAK_BUY", "WEAK_SELL"]:
            return {
                "scorecard": scorecard,
                "decision_text": f"Decision: {scorecard.recommended_action}\nRationale: {scorecard.rationale}",
                "execution_plan": None,
            }

        # 3. 如果决策是执行交易，使用LLM生成详细决策文本
        prompt = self._build_decision_prompt(
            scorecard=scorecard,
            analyst_reports=analyst_reports,
            investment_plan=investment_plan,
            trading_plan=trading_plan,
            risk_debate=risk_debate,
            current_positions=current_positions,
            account_balance=account_balance,
            current_price=current_price,
        )

        await self._agent.prompt(prompt)

        # 获取LLM响应
        decision_text = ""
        messages = self._agent.state.messages
        if messages:
            last_assistant = [m for m in messages if getattr(m, "role", None) == "assistant"]
            if last_assistant:
                content = last_assistant[-1].content
                if isinstance(content, list):
                    decision_text = "".join(getattr(c, "text", str(c)) for c in content)
                else:
                    decision_text = str(content)
                
                # 记录投资组合经理决策到日志
                logger.info(f"Portfolio Manager Decision: {decision_text}", tag="Decision")

        # 4. 记录决策历史
        self._decision_framework.record_decision(
            decision=scorecard.to_dict(),
            actual_execution=trading_plan.to_dict() if trading_plan else None,
        )

        return {
            "scorecard": scorecard,
            "decision_text": decision_text,
            "execution_plan": trading_plan if trading_plan.total_position_usdt > 0 else None,
        }

    def _build_decision_prompt(
        self,
        scorecard: DecisionScorecard,
        analyst_reports: Dict[str, str],
        investment_plan: str,
        trading_plan: TradingPlan,
        risk_debate: Dict[str, str],
        current_positions: List[Dict],
        account_balance: float,
        current_price: float,
    ) -> str:
        """构建决策提示"""
        # TradingPlan currently stores execution details in order lists.
        first_entry = trading_plan.entry_orders[0] if trading_plan.entry_orders else {}
        first_stop = trading_plan.stop_loss_orders[0] if trading_plan.stop_loss_orders else {}
        first_tp = trading_plan.take_profit_orders[0] if trading_plan.take_profit_orders else {}

        entry_type = first_entry.get("order_type", "N/A")
        entry_price = first_entry.get("price", current_price)
        stop_loss_price = first_stop.get("trigger_price", "N/A")
        take_profit_price = first_tp.get("price", "N/A")

        prompt = f"""As the Portfolio Manager, please make the final trading decision for {self._tool_context.symbol}.

QUANTITATIVE DECISION SCORECARD:
Overall Score: {scorecard.overall_score}/100
Recommended Action: {scorecard.recommended_action}
Confidence: {scorecard.confidence:.1%}

Dimension Scores:
- Technical: {scorecard.technical_score}/100
- Fundamental: {scorecard.fundamental_score}/100
- Sentiment: {scorecard.sentiment_score}/100
- Risk: {scorecard.risk_score}/100

Rationale: {scorecard.rationale}

Supporting Factors:
"""
        for factor in scorecard.supporting_factors:
            prompt += f"  + {factor}\n"

        if scorecard.risk_factors:
            prompt += "\nRisk Factors:\n"
            for risk in scorecard.risk_factors:
                prompt += f"  - {risk}\n"

        prompt += f"""
PROPOSED TRADING PLAN:
Direction: {trading_plan.direction}
Entry: {entry_type} @ {entry_price}
Position: {trading_plan.total_position_usdt} USDT ({trading_plan.total_position_coin:.6f} coins)
Stop Loss: {stop_loss_price}
Take Profit: {take_profit_price}
Leverage: {trading_plan.leverage}x
R:R Ratio: {trading_plan.risk_reward_ratio}:1

ANALYST REPORTS:
"""
        for role, report in analyst_reports.items():
            prompt += f"\n{role.upper()}:\n{report[:300]}...\n"

        prompt += f"""
INVESTMENT PLAN (Research Manager):
{investment_plan[:500]}...

RISK ASSESSMENT:
"""
        for role, assessment in risk_debate.items():
            prompt += f"\n{role.upper()}:\n{assessment[:200]}...\n"

        prompt += f"""
CURRENT STATUS:
Account Balance: {account_balance} USDT
Current Price: {current_price}
Current Positions: {len(current_positions)}
"""

        for pos in current_positions:
            prompt += f"  - {pos.get('symbol', 'N/A')}: {pos.get('position_amount', 'N/A')} @ {pos.get('entry_price', 'N/A')} (PnL: {pos.get('unrealized_profit', 'N/A')})\n"

        prompt += """
Please provide your FINAL DECISION including:
1. Confirm or modify the quantitative recommendation
2. Your qualitative assessment and rationale
3. Specific execution instructions (if approving the trade)
4. Any additional risk warnings or considerations

This decision will be executed, so be specific and careful.
"""

        return prompt


async def create_trader(tool_context: ToolContext) -> TraderAgent:
    """创建并初始化交易员"""
    trader = TraderAgent()
    await trader.initialize(tool_context)
    return trader


async def create_portfolio_manager(
    tool_context: ToolContext,
    memory: Optional[object] = None,
) -> PortfolioManagerAgent:
    """创建并初始化投资组合经理"""
    pm = PortfolioManagerAgent()
    await pm.initialize(tool_context, memory)
    return pm
