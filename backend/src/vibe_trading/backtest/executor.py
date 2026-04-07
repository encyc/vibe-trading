"""
回测执行器

处理单根K线的决策和交易执行逻辑。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pi_logger import get_logger

from vibe_trading.backtest.models import (
    BacktestConfig,
    BacktestDecision,
    Trade,
)
from vibe_trading.coordinator.signal_processor import TradingSignal
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.coordinator.quality_tracker import get_quality_tracker
from vibe_trading.execution.order_executor import (
    OrderExecutor,
    PaperOrderExecutor,
    OrderSide,
    OrderType,
    PaperPosition,
)

logger = get_logger(__name__)


@dataclass
class ExecutionState:
    """执行状态"""
    current_balance: float
    current_positions: Dict[str, PaperPosition]  # symbol -> position
    open_trades: Dict[str, Trade]  # trade_id -> trade
    decision_history: List[BacktestDecision] = field(default_factory=list)
    trade_history: List[Trade] = field(default_factory=list)

    # 统计
    total_decisions: int = 0
    llm_calls: int = 0
    llm_cache_hits: int = 0

    # 性能追踪
    equity_curve: List[float] = field(default_factory=list)
    timestamps: List[datetime] = field(default_factory=list)


class BacktestExecutor:
    """
    回测执行器

    处理单根K线的完整流程：
    1. 调用TradingCoordinator获取决策
    2. 执行交易（如果有信号）
    3. 更新持仓盈亏
    4. 记录决策和交易
    """

    def __init__(
        self,
        config: BacktestConfig,
        coordinator: TradingCoordinator,
        order_executor: Optional[OrderExecutor] = None,
    ):
        """
        初始化执行器

        Args:
            config: 回测配置
            coordinator: 交易协调器
            order_executor: 订单执行器（如果为None则创建PaperOrderExecutor）
        """
        self.config = config
        self.coordinator = coordinator
        self.order_executor = order_executor or PaperOrderExecutor(
            initial_balance=config.initial_balance
        )
        self.quality_tracker = get_quality_tracker()

        # 初始化执行状态
        self.state = ExecutionState(
            current_balance=config.initial_balance,
            current_positions={},
            open_trades={},
        )

    async def process_kline(self, kline) -> Optional[BacktestDecision]:
        """
        处理单根K线

        Args:
            kline: K线数据

        Returns:
            BacktestDecision: 决策结果（如果做出决策）
        """
        try:
            # 1. 更新持仓盈亏
            await self._update_positions_pnl(kline.close)

            # 2. 获取当前持仓信息
            current_positions = self._get_current_positions_list()

            # 3. 调用TradingCoordinator获取决策
            logger.debug(f"处理K线: {kline.symbol} @ {kline.close}")

            trading_decision = await self.coordinator.analyze_and_decide(
                current_price=kline.close,
                account_balance=self.state.current_balance,
                current_positions=current_positions,
            )

            self.state.total_decisions += 1
            self.state.llm_calls += 1  # TODO: 从LLM优化器获取真实调用数

            # 4. 提取信号
            processed_signal = getattr(self.coordinator, '_last_processed_signal', None)
            agent_contributions = getattr(self.coordinator, '_last_agent_contributions', {})
            market_condition = self._determine_market_condition(kline)

            # 5. 创建决策记录
            decision = BacktestDecision(
                decision_id=f"{self.config.symbol}_{int(kline.open_time)}",
                timestamp=datetime.fromtimestamp(kline.open_time / 1000),
                current_price=kline.close,
                trading_decision=trading_decision,
                processed_signal=processed_signal,
                agent_contributions=agent_contributions,
                market_condition=market_condition,
                signal=processed_signal.signal if processed_signal else TradingSignal.HOLD,
                confidence=processed_signal.confidence if processed_signal else 0.0,
                strength=processed_signal.strength.value if processed_signal else "unknown",
            )

            # 6. 记录决策到质量追踪器
            await self.quality_tracker.record_decision(
                decision_id=decision.decision_id,
                symbol=self.config.symbol,
                signal=processed_signal,
                agent_contributions=agent_contributions,
                market_condition=market_condition,
            )

            # 7. 执行交易（如果有信号）
            if decision.signal != TradingSignal.HOLD:
                await self._execute_trade(decision, kline)

            # 8. 添加到历史
            self.state.decision_history.append(decision)

            # 9. 更新权益曲线
            total_equity = self._calculate_total_equity(kline.close)
            self.state.equity_curve.append(total_equity)
            self.state.timestamps.append(decision.timestamp)

            return decision

        except Exception as e:
            logger.error(f"处理K线失败: {e}", exc_info=True)
            return None

    async def _execute_trade(self, decision: BacktestDecision, kline) -> None:
        """执行交易"""
        try:
            # 确定交易方向
            if decision.signal == TradingSignal.BUY:
                side = OrderSide.BUY
                position_side = "LONG"
            elif decision.signal == TradingSignal.SELL:
                side = OrderSide.SELL
                position_side = "SHORT"
            else:
                return

            # 计算交易数量（基于风险管理和账户余额）
            quantity = await self._calculate_position_size(
                decision, kline.close, position_side
            )

            if quantity <= 0:
                logger.warning("计算的交易数量为0，跳过执行")
                return

            # 执行订单
            order_result = await self.order_executor.place_order(
                symbol=self.config.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=quantity,
            )

            if order_result.status == "FILLED":
                # 创建交易记录
                trade = Trade(
                    trade_id=str(uuid.uuid4()),
                    symbol=self.config.symbol,
                    entry_time=decision.timestamp,
                    exit_time=None,
                    entry_price=order_result.filled_price or kline.close,
                    exit_price=None,
                    quantity=order_result.filled_quantity,
                    side=position_side,
                    pnl=None,
                    pnl_percentage=None,
                    decision_id=decision.decision_id,
                    signal=decision.signal,
                    confidence=decision.confidence,
                    market_condition=decision.market_condition,
                    agent_contributions=decision.agent_contributions,
                )

                self.state.open_trades[trade.trade_id] = trade
                decision.executed = True
                decision.trade_id = trade.trade_id

                logger.info(
                    f"执行交易: {side.value} {quantity:.4f} @ {trade.entry_price:.2f} "
                    f"(信心: {decision.confidence:.2f})"
                )

        except Exception as e:
            logger.error(f"执行交易失败: {e}", exc_info=True)

    async def _calculate_position_size(
        self,
        decision: BacktestDecision,
        current_price: float,
        position_side: str,
    ) -> float:
        """
        计算仓位大小

        基于风险管理规则和信号强度确定交易数量。
        """
        # 基础仓位：账户余额的10%
        base_position_value = self.state.current_balance * 0.1

        # 根据信号强度调整
        strength_multiplier = {
            "strong": 1.5,
            "moderate": 1.0,
            "weak": 0.5,
            "uncertain": 0.0,
        }
        multiplier = strength_multiplier.get(decision.strength, 1.0)

        # 根据置信度调整
        confidence_multiplier = decision.confidence

        # 计算最终仓位价值
        position_value = base_position_value * multiplier * confidence_multiplier

        # 转换为数量
        quantity = position_value / current_price

        return quantity

    async def _update_positions_pnl(self, current_price: float) -> None:
        """更新所有持仓的盈亏"""
        for trade in self.state.open_trades.values():
            if trade.exit_price is None:  # 仍持仓
                # 计算未实现盈亏
                if trade.side == "LONG":
                    unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
                else:  # SHORT
                    unrealized_pnl = (trade.entry_price - current_price) * trade.quantity

                trade.pnl = unrealized_pnl
                trade.pnl_percentage = (unrealized_pnl / (trade.entry_price * trade.quantity)) * 100

    def _get_current_positions_list(self) -> List[Dict]:
        """获取当前持仓列表（传递给TradingCoordinator）"""
        positions = []
        for trade in self.state.open_trades.values():
            if trade.exit_price is None:  # 仍持仓
                positions.append({
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "entry_price": trade.entry_price,
                    "unrealized_pnl": trade.pnl or 0.0,
                })
        return positions

    def _determine_market_condition(self, kline) -> str:
        """判断市场状态"""
        # 简化版判断逻辑
        # TODO: 可以集成更复杂的技术指标分析
        return "ranging"  # 默认震荡

    def _calculate_total_equity(self, current_price: float) -> float:
        """计算总权益（现金 + 持仓盈亏）"""
        total_equity = self.state.current_balance

        for trade in self.state.open_trades.values():
            if trade.exit_price is None and trade.pnl is not None:
                total_equity += trade.pnl

        return total_equity

    async def close_position(
        self,
        trade_id: str,
        exit_price: float,
        exit_time: datetime,
    ) -> Optional[Trade]:
        """平仓"""
        if trade_id not in self.state.open_trades:
            logger.warning(f"交易不存在: {trade_id}")
            return None

        trade = self.state.open_trades[trade_id]
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.hold_duration_hours = (exit_time - trade.entry_time).total_seconds() / 3600

        # 计算最终盈亏
        if trade.side == "LONG":
            trade.pnl = (exit_price - trade.entry_price) * trade.quantity
        else:  # SHORT
            trade.pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.pnl_percentage = (trade.pnl / (trade.entry_price * trade.quantity)) * 100

        # 更新账户余额
        self.state.current_balance += trade.pnl

        # 记录到质量追踪器
        await self.quality_tracker.record_outcome(
            decision_id=trade.decision_id,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            position_size=trade.quantity,
            hold_duration_hours=trade.hold_duration_hours,
        )

        # 移出开放交易
        del self.state.open_trades[trade_id]
        self.state.trade_history.append(trade)

        logger.info(
            f"平仓: {trade.side} {trade.quantity:.4f} "
            f"盈亏: {trade.pnl:.2f} ({trade.pnl_percentage:.2f}%)"
        )

        return trade

    async def close_all_positions(self, exit_price: float, exit_time: datetime) -> List[Trade]:
        """平掉所有持仓"""
        closed_trades = []
        trade_ids = list(self.state.open_trades.keys())

        for trade_id in trade_ids:
            trade = await self.close_position(trade_id, exit_price, exit_time)
            if trade:
                closed_trades.append(trade)

        return closed_trades

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "total_decisions": self.state.total_decisions,
            "total_trades": len(self.state.trade_history) + len(self.state.open_trades),
            "open_trades": len(self.state.open_trades),
            "closed_trades": len(self.state.trade_history),
            "current_balance": self.state.current_balance,
            "total_equity": self.state.equity_curve[-1] if self.state.equity_curve else self.config.initial_balance,
            "llm_calls": self.state.llm_calls,
            "llm_cache_hits": self.state.llm_cache_hits,
        }
