"""
回测指标计算器

计算交易指标、Agent性能和Prompt效果指标。
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pi_logger import get_logger

from vibe_trading.backtest.executor import BacktestExecutor, ExecutionState
from vibe_trading.backtest.models import (
    BacktestConfig,
    BacktestMetrics,
    PromptMetrics,
    Trade,
)
from vibe_trading.coordinator.quality_tracker import (
    DecisionQualityTracker,
    get_quality_tracker,
)

logger = get_logger(__name__)


class BacktestMetricsCalculator:
    """
    回测指标计算器

    计算完整的回测指标，包括：
    - 基础交易指标（收益率、夏普比率、最大回撤等）
    - Agent性能指标（准确率、贡献度等）
    - Prompt效果指标（稳定性、一致性等）
    """

    def __init__(self, quality_tracker: Optional[DecisionQualityTracker] = None):
        """
        初始化指标计算器

        Args:
            quality_tracker: 质量追踪器（如果为None则获取全局实例）
        """
        self.quality_tracker = quality_tracker or get_quality_tracker()

    async def calculate(
        self,
        executor: BacktestExecutor,
        config: BacktestConfig,
    ) -> BacktestMetrics:
        """
        计算完整指标

        Args:
            executor: 回测执行器
            config: 回测配置

        Returns:
            BacktestMetrics
        """
        state = executor.state
        trades = state.trade_history

        # 1. 基础交易指标
        trading_metrics = self._calculate_trading_metrics(trades, config)

        # 2. 风险指标
        risk_metrics = self._calculate_risk_metrics(trades, state.equity_curve)

        # 3. Agent性能指标
        agent_metrics = await self._calculate_agent_metrics()

        # 4. Prompt效果指标
        prompt_metrics = self._calculate_prompt_metrics(config)

        # 5. 时间序列数据
        equity_curve = state.equity_curve
        drawdown_curve = self._calculate_drawdown_curve(equity_curve)
        timestamps = state.timestamps

        return BacktestMetrics(
            # 基础指标
            total_return=trading_metrics["total_return"],
            win_rate=trading_metrics["win_rate"],
            sharpe_ratio=risk_metrics["sharpe_ratio"],
            sortino_ratio=risk_metrics["sortino_ratio"],
            max_drawdown=risk_metrics["max_drawdown"],
            profit_factor=trading_metrics["profit_factor"],
            avg_trade_pnl=trading_metrics["avg_trade_pnl"],
            avg_win_pnl=trading_metrics["avg_win_pnl"],
            avg_loss_pnl=trading_metrics["avg_loss_pnl"],
            total_trades=trading_metrics["total_trades"],
            profitable_trades=trading_metrics["profitable_trades"],
            losing_trades=trading_metrics["losing_trades"],

            # 风险指标
            var_95=risk_metrics["var_95"],
            var_99=risk_metrics["var_99"],
            expected_shortfall_95=risk_metrics["expected_shortfall_95"],
            max_consecutive_losses=risk_metrics["max_consecutive_losses"],
            avg_hold_duration_hours=trading_metrics["avg_hold_duration_hours"],

            # Agent指标
            agent_performances=agent_metrics["performances"],
            agent_rankings=agent_metrics["rankings"],

            # Prompt指标
            prompt_metrics=prompt_metrics,

            # 时间序列
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            timestamps=timestamps,
        )

    def _calculate_trading_metrics(
        self,
        trades: List[Trade],
        config: BacktestConfig,
    ) -> Dict[str, float]:
        """计算基础交易指标"""
        if not trades:
            return {
                "total_return": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_trade_pnl": 0.0,
                "avg_win_pnl": 0.0,
                "avg_loss_pnl": 0.0,
                "total_trades": 0,
                "profitable_trades": 0,
                "losing_trades": 0,
                "avg_hold_duration_hours": 0.0,
            }

        # 总盈亏
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)
        total_return = total_pnl / config.initial_balance

        # 胜率
        profitable_trades = [t for t in trades if (t.pnl or 0) > 0]
        losing_trades = [t for t in trades if (t.pnl or 0) <= 0]
        win_rate = len(profitable_trades) / len(trades) if trades else 0.0

        # 盈亏比
        total_win = sum(t.pnl for t in profitable_trades if t.pnl)
        total_loss = abs(sum(t.pnl for t in losing_trades if t.pnl))
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')

        # 平均盈亏
        avg_trade_pnl = statistics.mean([t.pnl for t in trades if t.pnl is not None]) if trades else 0.0
        avg_win_pnl = statistics.mean([t.pnl for t in profitable_trades if t.pnl]) if profitable_trades else 0.0
        avg_loss_pnl = statistics.mean([t.pnl for t in losing_trades if t.pnl]) if losing_trades else 0.0

        # 平均持仓时长
        hold_durations = [t.hold_duration_hours for t in trades if t.hold_duration_hours > 0]
        avg_hold_duration_hours = statistics.mean(hold_durations) if hold_durations else 0.0

        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_trade_pnl": avg_trade_pnl,
            "avg_win_pnl": avg_win_pnl,
            "avg_loss_pnl": avg_loss_pnl,
            "total_trades": len(trades),
            "profitable_trades": len(profitable_trades),
            "losing_trades": len(losing_trades),
            "avg_hold_duration_hours": avg_hold_duration_hours,
        }

    def _calculate_risk_metrics(
        self,
        trades: List[Trade],
        equity_curve: List[float],
    ) -> Dict[str, float]:
        """计算风险指标"""
        if not trades or not equity_curve:
            return {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown": 0.0,
                "var_95": 0.0,
                "var_99": 0.0,
                "expected_shortfall_95": 0.0,
                "max_consecutive_losses": 0,
            }

        # 计算收益率序列
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(ret)

        if not returns:
            return {
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown": 0.0,
                "var_95": 0.0,
                "var_99": 0.0,
                "expected_shortfall_95": 0.0,
                "max_consecutive_losses": 0,
            }

        # 夏普比率（假设无风险利率为0）
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
        sharpe_ratio = (avg_return * 252) / (std_return * (252 ** 0.5)) if std_return > 0 else 0.0  # 年化

        # Sortino比率
        negative_returns = [r for r in returns if r < 0]
        if negative_returns:
            downside_std = statistics.stdev(negative_returns) if len(negative_returns) > 1 else 0.0
            sortino_ratio = (avg_return * 252) / (downside_std * (252 ** 0.5)) if downside_std > 0 else 0.0
        else:
            sortino_ratio = sharpe_ratio  # 没有负收益时，Sortino等于Sharpe

        # 最大回撤
        max_drawdown = self._calculate_max_drawdown(equity_curve)

        # VaR和ES
        pnls = [t.pnl for t in trades if t.pnl is not None]
        var_95, es_95 = self._calculate_var_es(pnls, 0.95)
        var_99, _ = self._calculate_var_es(pnls, 0.99)

        # 最大连续亏损
        max_consecutive_losses = self._calculate_max_consecutive_losses(trades)

        return {
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "var_99": var_99,
            "expected_shortfall_95": es_95,
            "max_consecutive_losses": max_consecutive_losses,
        }

    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """计算最大回撤"""
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_drawdown = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak if peak > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown

    def _calculate_var_es(
        self,
        pnls: List[float],
        confidence: float,
    ) -> Tuple[float, float]:
        """计算VaR和Expected Shortfall"""
        if not pnls:
            return 0.0, 0.0

        sorted_pnls = sorted(pnls)
        n = len(sorted_pnls)

        # VaR
        var_index = int((1 - confidence) * n)
        var = sorted_pnls[var_index] if var_index < n else sorted_pnls[-1]

        # ES (VaR以下的平均值)
        es_index = int((1 - confidence) * n)
        if es_index > 0:
            es = statistics.mean(sorted_pnls[:es_index])
        else:
            es = var

        return var, es

    def _calculate_max_consecutive_losses(self, trades: List[Trade]) -> int:
        """计算最大连续亏损次数"""
        max_consecutive = 0
        current_consecutive = 0

        for trade in trades:
            if trade.pnl is not None and trade.pnl < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        return max_consecutive

    def _calculate_drawdown_curve(self, equity_curve: List[float]) -> List[float]:
        """计算回撤曲线"""
        if not equity_curve:
            return []

        drawdowns = []
        peak = equity_curve[0]

        for value in equity_curve:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak if peak > 0 else 0.0
            drawdowns.append(drawdown)

        return drawdowns

    async def _calculate_agent_metrics(self) -> Dict[str, any]:
        """计算Agent性能指标"""
        try:
            # 从质量追踪器获取指标
            quality_metrics = await self.quality_tracker.get_quality_metrics()

            performances = quality_metrics.agent_performances
            rankings = self.quality_tracker.get_agent_ranking(min_decisions=1)

            return {
                "performances": performances,
                "rankings": rankings,
            }
        except Exception as e:
            logger.warning(f"获取Agent指标失败: {e}")
            return {
                "performances": {},
                "rankings": [],
            }

    def _calculate_prompt_metrics(self, config: BacktestConfig) -> Optional[PromptMetrics]:
        """计算Prompt效果指标"""
        # TODO: 实现Prompt效果计算
        # 需要对比相同prompt_id的多次回测结果
        return None


# ============================================================================
# 便捷函数
# ============================================================================

async def calculate_backtest_metrics(
    trades: List[Trade],
    equity_curve: List[float],
    initial_balance: float,
) -> Dict[str, float]:
    """
    便捷函数：计算基础回测指标

    Args:
        trades: 交易列表
        equity_curve: 权益曲线
        initial_balance: 初始余额

    Returns:
        指标字典
    """
    calculator = BacktestMetricsCalculator()

    # 创建临时config
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval="30m",
        start_time=datetime.now(),
        end_time=datetime.now(),
        initial_balance=initial_balance,
    )

    # 创建临时executor state
    state = ExecutionState(
        current_balance=initial_balance,
        current_positions={},
    )
    state.trade_history = trades
    state.equity_curve = equity_curve

    # 创建临时executor
    from vibe_trading.backtest.executor import BacktestExecutor
    from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
    coordinator = TradingCoordinator(symbol="BTCUSDT", interval="30m")
    executor = BacktestExecutor(config=config, coordinator=coordinator)
    executor.state = state

    metrics = await calculator.calculate(executor, config)

    return {
        "total_return": metrics.total_return,
        "win_rate": metrics.win_rate,
        "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown": metrics.max_drawdown,
        "profit_factor": metrics.profit_factor,
        "total_trades": metrics.total_trades,
    }
