"""
高级风控工具模块

提供VaR计算、凯利公式、风险指标等高级风控功能。
"""
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """VaR计算结果"""
    var_95: float  # 95%置信度的VaR
    var_99: float  # 99%置信度的VaR
    expected_shortfall: float  # 预期亏损（ES）
    volatility: float  # 波动率
    confidence_interval: Tuple[float, float]  # 置信区间


@dataclass
class KellyResult:
    """凯利公式计算结果"""
    kelly_fraction: float  # 凯利公式建议的仓位比例
    half_kelly_fraction: float  # 半凯利（更保守）
    optimal_position_size: float  # 最优仓位大小（USDT）
    win_rate: float  # 胜率
    avg_win: float  # 平均盈利
    avg_loss: float  # 平均亏损
    profit_factor: float  # 盈亏比


@dataclass
class RiskMetrics:
    """综合风险指标"""
    # 基础指标
    account_balance: float
    total_equity: float
    unrealized_pnl: float
    realized_pnl: float
    margin_used: float
    margin_free: float
    margin_ratio: float

    # 风险指标
    max_drawdown: float  # 最大回撤
    current_drawdown: float  # 当前回撤
    var_95: float  # VaR 95%
    var_99: float  # VaR 99%
    sharpe_ratio: float  # 夏普比率
    sortino_ratio: float  # 索提诺比率

    # 交易统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # 连续统计
    current_streak: int  # 当前连续盈亏次数（正=盈利，负=亏损）
    max_winning_streak: int
    max_losing_streak: int
    consecutive_losses: int  # 当前连续亏损次数

    # 风险等级
    risk_level: str  # low/medium/high/critical
    warnings: List[str] = field(default_factory=list)


class VaRCalculator:
    """VaR（风险价值）计算器"""

    def __init__(self, confidence_levels: List[float] = None):
        self.confidence_levels = confidence_levels or [0.95, 0.99]
        self._returns_history: deque = deque(maxlen=100)

    def add_return(self, ret: float) -> None:
        """添加收益率"""
        self._returns_history.append(ret)

    def add_price_change(self, old_price: float, new_price: float) -> None:
        """添加价格变化"""
        ret = (new_price - old_price) / old_price
        self._returns_history.append(ret)

    def calculate_var(
        self,
        position_value: float,
        method: str = "historical"
    ) -> VaRResult:
        """
        计算VaR

        Args:
            position_value: 仓位价值
            method: 计算方法 (historical/parametric/monte_carlo)

        Returns:
            VaR计算结果
        """
        if len(self._returns_history) < 10:
            # 数据不足，使用默认值
            return VaRResult(
                var_95=position_value * 0.02,
                var_99=position_value * 0.03,
                expected_shortfall=position_value * 0.025,
                volatility=0.02,
                confidence_interval=(position_value * 0.01, position_value * 0.04)
            )

        returns = np.array(list(self._returns_history))

        if method == "historical":
            return self._historical_var(returns, position_value)
        elif method == "parametric":
            return self._parametric_var(returns, position_value)
        else:
            return self._historical_var(returns, position_value)

    def _historical_var(self, returns: np.ndarray, position_value: float) -> VaRResult:
        """历史模拟法计算VaR"""
        # 计算波动率
        volatility = np.std(returns)

        # 计算VaR
        var_95_pct = np.percentile(returns, 5)  # 5%最坏情况
        var_99_pct = np.percentile(returns, 1)  # 1%最坏情况

        # 预期亏损（ES）：超过VaR的平均损失
        es_returns = returns[returns <= var_95_pct]
        expected_shortfall_pct = np.mean(es_returns) if len(es_returns) > 0 else var_95_pct

        return VaRResult(
            var_95=abs(var_95_pct * position_value),
            var_99=abs(var_99_pct * position_value),
            expected_shortfall=abs(expected_shortfall_pct * position_value),
            volatility=volatility,
            confidence_interval=(abs(var_95_pct * position_value) * 0.8, abs(var_95_pct * position_value) * 1.2)
        )

    def _parametric_var(self, returns: np.ndarray, position_value: float) -> VaRResult:
        """参数法计算VaR（假设正态分布）"""
        mean = np.mean(returns)
        std = np.std(returns)

        from scipy import stats
        var_95_pct = stats.norm.ppf(0.05, mean, std)  # 5%分位数
        var_99_pct = stats.norm.ppf(0.01, mean, std)  # 1%分位数

        # 预期亏损
        expected_shortfall_pct = mean - std * stats.norm.pdf(stats.norm.ppf(0.05)) / 0.05

        return VaRResult(
            var_95=abs(var_95_pct * position_value),
            var_99=abs(var_99_pct * position_value),
            expected_shortfall=abs(expected_shortfall_pct * position_value),
            volatility=std,
            confidence_interval=(abs(var_95_pct * position_value) * 0.8, abs(var_95_pct * position_value) * 1.2)
        )


class KellyCalculator:
    """凯利公式计算器"""

    def __init__(self):
        self._trade_history: List[Dict] = []

    def add_trade(
        self,
        pnl: float,
        entry_price: float,
        exit_price: float,
        position_size: float
    ) -> None:
        """添加交易记录"""
        self._trade_history.append({
            "pnl": pnl,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "position_size": position_size,
            "return": pnl / (entry_price * position_size) if entry_price > 0 else 0
        })

    def calculate_kelly(
        self,
        account_balance: float,
        min_trades: int = 10
    ) -> KellyResult:
        """
        计算凯利公式仓位

        公式: f* = (bp - q) / b
        其中:
        - f* = 建议仓位比例
        - b = 盈亏比 (平均盈利 / 平均亏损)
        - p = 胜率
        - q = 败率 (1 - p)
        """
        if len(self._trade_history) < min_trades:
            # 数据不足，返回保守值
            return KellyResult(
                kelly_fraction=0.02,
                half_kelly_fraction=0.01,
                optimal_position_size=account_balance * 0.02,
                win_rate=0.5,
                avg_win=0,
                avg_loss=0,
                profit_factor=1.0
            )

        wins = [t for t in self._trade_history if t["pnl"] > 0]
        losses = [t for t in self._trade_history if t["pnl"] < 0]

        win_rate = len(wins) / len(self._trade_history)
        avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t["pnl"] for t in losses])) if losses else 1

        # 盈亏比
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 1

        # 凯利公式
        b = profit_factor
        p = win_rate
        q = 1 - p

        if b > 0:
            kelly_fraction = (b * p - q) / b
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # 限制在0-25%之间
        else:
            kelly_fraction = 0.01

        # 半凯利（更保守，推荐实际使用）
        half_kelly = kelly_fraction / 2

        return KellyResult(
            kelly_fraction=kelly_fraction,
            half_kelly_fraction=half_kelly,
            optimal_position_size=account_balance * half_kelly,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor
        )


class RiskMetricsCalculator:
    """风险指标计算器"""

    def __init__(self):
        self._balance_history: deque = deque(maxlen=1000)
        self._equity_history: deque = deque(maxlen=1000)
        self._trade_history: List[Dict] = []
        self._peak_equity: float = 0
        self._current_streak: int = 0
        self._current_consecutive_losses: int = 0

    def update_balance(self, balance: float, equity: float = None) -> None:
        """更新余额历史"""
        equity = equity or balance
        self._balance_history.append(balance)
        self._equity_history.append(equity)

        # 更新峰值
        if equity > self._peak_equity:
            self._peak_equity = equity

    def add_trade(
        self,
        pnl: float,
        entry_price: float,
        exit_price: float,
        position_size: float,
        symbol: str,
        entry_time: datetime,
        exit_time: datetime
    ) -> None:
        """添加交易记录"""
        self._trade_history.append({
            "pnl": pnl,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "position_size": position_size,
            "symbol": symbol,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "return_pct": pnl / (entry_price * position_size) if entry_price > 0 else 0
        })

        # 更新连续统计
        if pnl > 0:
            self._current_streak = abs(self._current_streak) + 1 if self._current_streak >= 0 else 1
            self._current_consecutive_losses = 0
        else:
            self._current_streak = -(abs(self._current_streak) + 1) if self._current_streak <= 0 else -1
            self._current_consecutive_losses += 1

    def calculate_metrics(
        self,
        account_balance: float,
        total_equity: float,
        unrealized_pnl: float,
        margin_used: float,
        margin_free: float
    ) -> RiskMetrics:
        """计算综合风险指标"""
        # 基础指标
        margin_ratio = margin_used / (margin_used + margin_free) if (margin_used + margin_free) > 0 else 0

        # 当前回撤
        if self._peak_equity > 0:
            current_drawdown = (self._peak_equity - total_equity) / self._peak_equity
        else:
            current_drawdown = 0

        # 最大回撤
        max_drawdown = self._calculate_max_drawdown()

        # VaR
        var_95, var_99 = self._calculate_var(total_equity)

        # 夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio()

        # 索提诺比率
        sortino_ratio = self._calculate_sortino_ratio()

        # 交易统计
        trades_stats = self._calculate_trade_stats()

        # 连续统计
        streak_stats = self._calculate_streak_stats()

        # 风险等级
        risk_level, warnings = self._assess_risk_level(
            current_drawdown=current_drawdown,
            max_drawdown=max_drawdown,
            margin_ratio=margin_ratio,
            consecutive_losses=streak_stats["consecutive_losses"]
        )

        return RiskMetrics(
            account_balance=account_balance,
            total_equity=total_equity,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=sum(t["pnl"] for t in self._trade_history),
            margin_used=margin_used,
            margin_free=margin_free,
            margin_ratio=margin_ratio,
            max_drawdown=max_drawdown,
            current_drawdown=current_drawdown,
            var_95=var_95,
            var_99=var_99,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            total_trades=len(self._trade_history),
            winning_trades=trades_stats["winning_trades"],
            losing_trades=trades_stats["losing_trades"],
            win_rate=trades_stats["win_rate"],
            avg_win=trades_stats["avg_win"],
            avg_loss=trades_stats["avg_loss"],
            profit_factor=trades_stats["profit_factor"],
            current_streak=self._current_streak,
            max_winning_streak=streak_stats["max_winning_streak"],
            max_losing_streak=streak_stats["max_losing_streak"],
            consecutive_losses=streak_stats["consecutive_losses"],
            risk_level=risk_level,
            warnings=warnings
        )

    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if len(self._equity_history) < 2:
            return 0

        equity_array = np.array(list(self._equity_history))
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        return np.max(drawdown)

    def _calculate_var(self, equity: float) -> Tuple[float, float]:
        """计算VaR"""
        if len(self._equity_history) < 10:
            return equity * 0.02, equity * 0.03

        returns = []
        equity_list = list(self._equity_history)
        for i in range(1, len(equity_list)):
            ret = (equity_list[i] - equity_list[i-1]) / equity_list[i-1]
            returns.append(ret)

        returns_array = np.array(returns)
        var_95_pct = np.percentile(returns_array, 5)
        var_99_pct = np.percentile(returns_array, 1)

        return abs(var_95_pct * equity), abs(var_99_pct * equity)

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        if len(self._equity_history) < 10:
            return 0

        returns = []
        equity_list = list(self._equity_history)
        for i in range(1, len(equity_list)):
            ret = (equity_list[i] - equity_list[i-1]) / equity_list[i-1]
            returns.append(ret)

        if not returns:
            return 0

        avg_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0

        # 年化（假设每日数据）
        sharpe = (avg_return * 365 - risk_free_rate) / (std_return * np.sqrt(365))
        return sharpe

    def _calculate_sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """计算索提诺比率（只考虑下行风险）"""
        if len(self._equity_history) < 10:
            return 0

        returns = []
        equity_list = list(self._equity_history)
        for i in range(1, len(equity_list)):
            ret = (equity_list[i] - equity_list[i-1]) / equity_list[i-1]
            returns.append(ret)

        if not returns:
            return 0

        avg_return = np.mean(returns)
        downside_returns = [r for r in returns if r < 0]

        if not downside_returns:
            return 0

        downside_std = np.std(downside_returns)

        if downside_std == 0:
            return 0

        sortino = (avg_return * 365 - risk_free_rate) / (downside_std * np.sqrt(365))
        return sortino

    def _calculate_trade_stats(self) -> Dict:
        """计算交易统计"""
        if not self._trade_history:
            return {
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0
            }

        wins = [t["pnl"] for t in self._trade_history if t["pnl"] > 0]
        losses = [abs(t["pnl"]) for t in self._trade_history if t["pnl"] < 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        total_trades = len(self._trade_history)

        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0

        total_wins = sum(wins)
        total_losses = sum(losses)
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        return {
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor
        }

    def _calculate_streak_stats(self) -> Dict:
        """计算连续统计"""
        if not self._trade_history:
            return {
                "max_winning_streak": 0,
                "max_losing_streak": 0,
                "consecutive_losses": 0
            }

        max_winning = 0
        max_losing = 0
        current_winning = 0
        current_losing = 0

        for trade in self._trade_history:
            if trade["pnl"] > 0:
                current_winning += 1
                max_winning = max(max_winning, current_winning)
                current_losing = 0
            else:
                current_losing += 1
                max_losing = max(max_losing, current_losing)
                current_winning = 0

        return {
            "max_winning_streak": max_winning,
            "max_losing_streak": max_losing,
            "consecutive_losses": self._current_consecutive_losses
        }

    def _assess_risk_level(
        self,
        current_drawdown: float,
        max_drawdown: float,
        margin_ratio: float,
        consecutive_losses: int
    ) -> Tuple[str, List[str]]:
        """评估风险等级"""
        warnings = []
        risk_level = "low"

        # 回撤风险评估
        if current_drawdown > 0.20:
            risk_level = "critical"
            warnings.append(f"当前回撤{current_drawdown*100:.1f}%超过20%，处于危险水平！")
        elif current_drawdown > 0.15:
            risk_level = "high"
            warnings.append(f"当前回撤{current_drawdown*100:.1f}%超过15%，需要谨慎！")
        elif current_drawdown > 0.10:
            risk_level = "medium"
            warnings.append(f"当前回撤{current_drawdown*100:.1f}%超过10%，注意风险。")

        # 保证金风险评估
        if margin_ratio > 0.8:
            risk_level = max(risk_level, "critical")
            warnings.append(f"保证金使用率{margin_ratio*100:.1f}%超过80%，接近爆仓！")
        elif margin_ratio > 0.6:
            risk_level = max(risk_level, "high")
            warnings.append(f"保证金使用率{margin_ratio*100:.1f}%超过60%，风险较高。")
        elif margin_ratio > 0.4:
            risk_level = max(risk_level, "medium")
            warnings.append(f"保证金使用率{margin_ratio*100:.1f}%超过40%，注意控制。")

        # 连续亏损预警
        if consecutive_losses >= 5:
            risk_level = max(risk_level, "critical")
            warnings.append(f"连续{consecutive_losses}次亏损！建议暂停交易，检查策略。")
        elif consecutive_losses >= 3:
            risk_level = max(risk_level, "high")
            warnings.append(f"连续{consecutive_losses}次亏损，建议降低仓位或暂停交易。")

        return risk_level, warnings


class VolatilityAdjustedPositionSizer:
    """波动率调整仓位计算器"""

    def __init__(self, base_risk_per_trade: float = 0.02):
        self.base_risk_per_trade = base_risk_per_trade
        self._atr_history: deque = deque(maxlen=20)

    def update_atr(self, atr: float, price: float) -> None:
        """更新ATR历史"""
        atr_pct = atr / price if price > 0 else 0
        self._atr_history.append(atr_pct)

    def calculate_adjusted_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        current_atr: Optional[float] = None
    ) -> float:
        """
        计算波动率调整后的仓位大小

        根据市场波动率动态调整仓位：
        - 高波动率 -> 减少仓位
        - 低波动率 -> 增加仓位
        """
        # 基础仓位（基于风险）
        risk_amount = account_balance * self.base_risk_per_trade
        stop_distance = abs(entry_price - stop_loss_price) / entry_price

        if stop_distance == 0:
            return account_balance * 0.01

        base_position_value = risk_amount / stop_distance

        # 波动率调整
        if current_atr and len(self._atr_history) >= 10:
            avg_atr = np.mean(list(self._atr_history))
            current_atr_pct = current_atr / entry_price

            # 波动率比率
            volatility_ratio = current_atr_pct / avg_atr if avg_atr > 0 else 1

            # 调整因子：高波动率时减少仓位
            if volatility_ratio > 1.5:
                # 波动率很高，减半仓位
                adjustment_factor = 0.5
            elif volatility_ratio > 1.2:
                # 波动率较高，减少30%
                adjustment_factor = 0.7
            elif volatility_ratio < 0.8:
                # 波动率较低，可以增加20%
                adjustment_factor = 1.2
            else:
                # 波动率正常
                adjustment_factor = 1.0

            adjusted_position = base_position_value * adjustment_factor
        else:
            adjusted_position = base_position_value

        # 限制最大仓位
        max_position = account_balance * 0.3
        return min(adjusted_position, max_position)


class CorrelationRiskChecker:
    """相关性风险检查器"""

    def __init__(self):
        self._price_history: Dict[str, deque] = {}

    def update_price(self, symbol: str, price: float) -> None:
        """更新价格历史"""
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=100)
        self._price_history[symbol].append(price)

    def calculate_correlation(self, symbol1: str, symbol2: str) -> float:
        """计算两个交易对的相关性"""
        if symbol1 not in self._price_history or symbol2 not in self._price_history:
            return 0

        if len(self._price_history[symbol1]) < 10 or len(self._price_history[symbol2]) < 10:
            return 0

        # 计算收益率
        returns1 = []
        returns2 = []

        prices1 = list(self._price_history[symbol1])
        prices2 = list(self._price_history[symbol2])

        for i in range(1, min(len(prices1), len(prices2))):
            ret1 = (prices1[i] - prices1[i-1]) / prices1[i-1]
            ret2 = (prices2[i] - prices2[i-1]) / prices2[i-1]
            returns1.append(ret1)
            returns2.append(ret2)

        if not returns1:
            return 0

        # 计算相关系数
        correlation = np.corrcoef(returns1, returns2)[0, 1]
        return correlation if not np.isnan(correlation) else 0

    def check_portfolio_correlation(
        self,
        symbols: List[str],
        threshold: float = 0.7
    ) -> Dict[str, List[str]]:
        """
        检查投资组合相关性

        Returns:
            高相关性对的字典 {symbol: [correlated_symbols]}
        """
        high_correlations = {}

        for i, symbol1 in enumerate(symbols):
            correlated = []
            for symbol2 in symbols[i+1:]:
                corr = self.calculate_correlation(symbol1, symbol2)
                if abs(corr) >= threshold:
                    correlated.append(f"{symbol2} ({corr:.2f})")

            if correlated:
                high_correlations[symbol1] = correlated

        return high_correlations


class TrailingStopLossManager:
    """移动止损管理器"""

    def __init__(
        self,
        activation_profit_pct: float = 0.01,  # 激活移动止损的盈利百分比
        trail_distance_pct: float = 0.02  # 移动止损距离
    ):
        self.activation_profit_pct = activation_profit_pct
        self.trail_distance_pct = trail_distance_pct
        self._positions: Dict[str, Dict] = {}

    def add_position(
        self,
        symbol: str,
        entry_price: float,
        position_side: str,
        initial_stop: float
    ) -> None:
        """添加仓位"""
        self._positions[symbol] = {
            "entry_price": entry_price,
            "position_side": position_side,
            "initial_stop": initial_stop,
            "current_stop": initial_stop,
            "highest_price": entry_price,
            "lowest_price": entry_price,
            "activated": False
        }

    def update_stop_loss(self, symbol: str, current_price: float) -> Optional[float]:
        """
        更新移动止损

        Returns:
            新的止损价格，如果没有更新则返回None
        """
        if symbol not in self._positions:
            return None

        pos = self._positions[symbol]
        new_stop = None

        if pos["position_side"] == "LONG":
            # 多头仓位
            pos["highest_price"] = max(pos["highest_price"], current_price)

            # 计算当前盈利百分比
            profit_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

            if profit_pct >= self.activation_profit_pct:
                pos["activated"] = True

                # 计算新的移动止损
                trailing_stop = pos["highest_price"] * (1 - self.trail_distance_pct)

                # 只向上移动止损，不向下移动
                if trailing_stop > pos["current_stop"]:
                    pos["current_stop"] = trailing_stop
                    new_stop = trailing_stop

        else:  # SHORT
            pos["lowest_price"] = min(pos["lowest_price"], current_price)

            profit_pct = (pos["entry_price"] - current_price) / pos["entry_price"]

            if profit_pct >= self.activation_profit_pct:
                pos["activated"] = True

                trailing_stop = pos["lowest_price"] * (1 + self.trail_distance_pct)

                if trailing_stop < pos["current_stop"]:
                    pos["current_stop"] = trailing_stop
                    new_stop = trailing_stop

        return new_stop

    def get_stop_loss(self, symbol: str) -> Optional[float]:
        """获取当前止损价格"""
        if symbol not in self._positions:
            return None
        return self._positions[symbol]["current_stop"]

    def remove_position(self, symbol: str) -> None:
        """移除仓位"""
        self._positions.pop(symbol, None)
