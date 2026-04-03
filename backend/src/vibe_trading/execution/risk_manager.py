"""
风险管理模块

提供基础风控规则和风险检查，集成高级风控工具。
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime

from vibe_trading.config.settings import get_settings
from vibe_trading.data_sources.binance_client import OrderSide, OrderType, PositionSide
from vibe_trading.execution.advanced_risk_tools import (
    VaRCalculator,
    KellyCalculator,
    RiskMetricsCalculator,
    VolatilityAdjustedPositionSizer,
    CorrelationRiskChecker,
    TrailingStopLossManager,
    RiskMetrics,
)

logger = logging.getLogger(__name__)


class RiskCheckResult(str, Enum):
    """风控检查结果"""
    APPROVED = "approved"  # 通过
    REJECTED = "rejected"  # 拒绝
    WARNING = "warning"    # 警告但允许


@dataclass
class RiskCheck:
    """风控检查结果"""
    result: RiskCheckResult
    reason: str
    warnings: List[str] = None
    var_analysis: Optional[Dict] = None
    kelly_analysis: Optional[Dict] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class PositionRiskInfo:
    """仓位风险信息"""
    symbol: str
    entry_price: float
    current_price: float
    position_size: float
    position_side: str
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float
    take_profit: float
    liquidation_price: Optional[float] = None
    margin_ratio: float = 0
    risk_score: float = 0  # 0-100，越高越危险


class RiskManager:
    """风险管理器（增强版）"""

    def __init__(self):
        settings = get_settings()
        self._max_position_size = settings.max_position_size
        self._max_total_position = settings.max_total_position
        self._stop_loss_pct = settings.stop_loss_pct
        self._take_profit_pct = settings.take_profit_pct
        self._leverage = settings.leverage

        # 高级风控工具
        self.var_calculator = VaRCalculator()
        self.kelly_calculator = KellyCalculator()
        self.metrics_calculator = RiskMetricsCalculator()
        self.volatility_sizer = VolatilityAdjustedPositionSizer()
        self.correlation_checker = CorrelationRiskChecker()
        self.trailing_stop_manager = TrailingStopLossManager(
            activation_profit_pct=0.01,
            trail_distance_pct=0.02
        )

        # 风险预警阈值
        self._warning_drawdown_pct = 0.10  # 10%回撤警告
        self._critical_drawdown_pct = 0.20  # 20%回撤危险
        self._warning_consecutive_losses = 3
        self._critical_consecutive_losses = 5

        logger.info("Enhanced Risk Manager initialized")

    async def check_order_risk(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        current_positions: Optional[Dict] = None,
        current_balance: Optional[float] = None,
    ) -> RiskCheck:
        """
        检查订单风险（增强版）

        新增：
        - VaR风险分析
        - 凯利公式建议
        - 波动率调整
        """
        warnings = []
        var_analysis = None
        kelly_analysis = None

        # 计算订单价值
        order_value = quantity * (price or 50000)

        # === VaR风险分析 ===
        if current_balance:
            var_result = self.var_calculator.calculate_var(order_value)
            var_ratio = var_result.var_95 / current_balance

            var_analysis = {
                "var_95": var_result.var_95,
                "var_99": var_result.var_99,
                "var_ratio": var_ratio,
                "volatility": var_result.volatility,
            }

            if var_ratio > 0.05:  # VaR超过账户5%
                warnings.append(
                    f"VaR风险较高：95%置信度下最大损失{var_result.var_95:.2f}USDT"
                )

        # === 凯利公式建议 ===
        if current_balance:
            kelly_result = self.kelly_calculator.calculate_kelly(current_balance)
            kelly_analysis = {
                "kelly_fraction": kelly_result.kelly_fraction,
                "half_kelly_fraction": kelly_result.half_kelly_fraction,
                "optimal_size": kelly_result.optimal_position_size,
                "win_rate": kelly_result.win_rate,
            }

            if order_value > kelly_result.optimal_position_size * 2:
                warnings.append(
                    f"订单规模{order_value:.2f}USDT超过凯利建议"
                    f"{kelly_result.optimal_position_size:.2f}USDT的2倍"
                )

        # 检查单笔仓位大小
        if order_value > self._max_position_size:
            return RiskCheck(
                result=RiskCheckResult.REJECTED,
                reason=f"订单规模{order_value:.2f}USDT超过最大{self._max_position_size}USDT",
                var_analysis=var_analysis,
                kelly_analysis=kelly_analysis,
            )

        # 检查总仓位
        if current_positions:
            total_exposure = current_positions.get("total_exposure", 0)
            if total_exposure + order_value > self._max_total_position:
                return RiskCheck(
                    result=RiskCheckResult.REJECTED,
                    reason=f"总敞口{total_exposure + order_value:.2f}USDT超过最大{self._max_total_position}USDT",
                    var_analysis=var_analysis,
                    kelly_analysis=kelly_analysis,
                )

            # 接近上限警告
            if total_exposure + order_value > self._max_total_position * 0.8:
                warnings.append(
                    f"总敞口将达到{total_exposure + order_value:.2f}USDT，"
                    f"接近最大{self._max_total_position}USDT"
                )

        # 检查杠杆
        if current_balance:
            required_margin = order_value / self._leverage
            margin_ratio = required_margin / current_balance

            if margin_ratio > 0.5:
                return RiskCheck(
                    result=RiskCheckResult.REJECTED,
                    reason=f"订单需要{margin_ratio*100:.1f}%的保证金，超过50%限制",
                    var_analysis=var_analysis,
                    kelly_analysis=kelly_analysis,
                )

            if margin_ratio > 0.3:
                warnings.append(
                    f"订单需要{margin_ratio*100:.1f}%的保证金，建议减少规模"
                )

        if warnings:
            return RiskCheck(
                result=RiskCheckResult.WARNING,
                reason="订单获批，但有风险警告",
                warnings=warnings,
                var_analysis=var_analysis,
                kelly_analysis=kelly_analysis,
            )

        return RiskCheck(
            result=RiskCheckResult.APPROVED,
            reason="订单获批",
            var_analysis=var_analysis,
            kelly_analysis=kelly_analysis,
        )

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        account_balance: float = 10000.0,
        use_kelly: bool = False,
        current_atr: Optional[float] = None,
    ) -> float:
        """
        计算基于风险的仓位大小（增强版）

        新增：
        - 凯利公式计算
        - 波动率调整
        """
        if use_kelly:
            # 使用凯利公式
            kelly_result = self.kelly_calculator.calculate_kelly(account_balance)
            position_value = kelly_result.optimal_position_size
        else:
            # 使用固定风险百分比
            risk_per_trade = 0.02  # 2%风险
            risk_amount = account_balance * risk_per_trade
            stop_distance = abs(entry_price - stop_loss_price) / entry_price

            if stop_distance == 0:
                return self._max_position_size / entry_price

            position_value = risk_amount / stop_distance

        # 波动率调整
        if current_atr:
            position_value = self.volatility_sizer.calculate_adjusted_position_size(
                account_balance=account_balance,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                current_atr=current_atr
            )

        # 限制最大仓位
        position_value = min(position_value, self._max_position_size)
        position_size = position_value / entry_price

        return position_size

    def calculate_stop_loss(
        self,
        entry_price: float,
        position_side: PositionSide,
        atr: Optional[float] = None,
        volatility_adjusted: bool = False,
    ) -> float:
        """
        计算止损价格（增强版）

        新增：
        - 波动率自适应
        """
        if atr and volatility_adjusted:
            # 基于ATR的动态止损
            # 根据波动率调整止损距离
            stop_distance_atr = atr * 2

            # 如果波动率很高，增加止损距离
            if self.var_calculator._returns_history:
                recent_volatility = np.std(list(self.var_calculator._returns_history[-20:]))
                if recent_volatility > 0.03:  # 高波动率
                    stop_distance_atr = atr * 2.5

            stop_distance = max(stop_distance_atr, entry_price * self._stop_loss_pct)
        elif atr:
            stop_distance = atr * 2
        else:
            stop_distance = entry_price * self._stop_loss_pct

        if position_side == PositionSide.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def calculate_take_profit(
        self,
        entry_price: float,
        position_side: PositionSide,
        atr: Optional[float] = None,
        risk_reward_ratio: float = 2.0,
    ) -> float:
        """
        计算止盈价格（增强版）

        新增：
        - 基于止损的盈亏比
        """
        if atr:
            profit_distance = atr * 3
        else:
            profit_distance = entry_price * self._take_profit_pct

        # 确保至少2:1的盈亏比
        stop_distance = entry_price * self._stop_loss_pct
        min_profit_distance = stop_distance * risk_reward_ratio

        profit_distance = max(profit_distance, min_profit_distance)

        if position_side == PositionSide.LONG:
            return entry_price + profit_distance
        else:
            return entry_price - profit_distance

    def update_trailing_stop(
        self,
        symbol: str,
        entry_price: float,
        position_side: str,
        current_price: float,
        initial_stop: float,
    ) -> Optional[float]:
        """
        更新移动止损

        Returns:
            新的止损价格，如果没有更新则返回None
        """
        # 确保仓位已添加到管理器
        if symbol not in self.trailing_stop_manager._positions:
            self.trailing_stop_manager.add_position(
                symbol=symbol,
                entry_price=entry_price,
                position_side=position_side,
                initial_stop=initial_stop
            )

        return self.trailing_stop_manager.update_stop_loss(symbol, current_price)

    def check_correlation_risk(
        self,
        symbols: List[str],
        threshold: float = 0.7
    ) -> Dict[str, List[str]]:
        """检查投资组合相关性风险"""
        return self.correlation_checker.check_portfolio_correlation(symbols, threshold)

    def get_risk_metrics(
        self,
        account_balance: float,
        total_equity: float,
        unrealized_pnl: float,
        margin_used: float,
        margin_free: float,
    ) -> RiskMetrics:
        """
        获取综合风险指标

        Returns:
            完整的风险指标报告
        """
        self.metrics_calculator.update_balance(account_balance, total_equity)
        return self.metrics_calculator.calculate_metrics(
            account_balance=account_balance,
            total_equity=total_equity,
            unrealized_pnl=unrealized_pnl,
            margin_used=margin_used,
            margin_free=margin_free
        )

    def assess_overall_risk(
        self,
        account_balance: float,
        total_equity: float,
        margin_used: float,
        margin_free: float,
        positions: List[Dict],
    ) -> Dict:
        """
        评估整体风险状况

        Returns:
            {
                "risk_level": "low/medium/high/critical",
                "score": 0-100,
                "warnings": [],
                "recommendations": []
            }
        """
        # 获取风险指标
        metrics = self.get_risk_metrics(
            account_balance=account_balance,
            total_equity=total_equity,
            unrealized_pnl=sum(p.get("unrealized_profit", 0) for p in positions),
            margin_used=margin_used,
            margin_free=margin_free
        )

        # 计算风险分数
        risk_score = 0
        max_score = 100

        # 回撤风险 (25分)
        if metrics.current_drawdown > 0.20:
            risk_score += 25
        elif metrics.current_drawdown > 0.15:
            risk_score += 20
        elif metrics.current_drawdown > 0.10:
            risk_score += 15
        elif metrics.current_drawdown > 0.05:
            risk_score += 10

        # 保证金风险 (25分)
        if metrics.margin_ratio > 0.8:
            risk_score += 25
        elif metrics.margin_ratio > 0.6:
            risk_score += 20
        elif metrics.margin_ratio > 0.4:
            risk_score += 15
        elif metrics.margin_ratio > 0.3:
            risk_score += 10

        # 连续亏损风险 (20分)
        if metrics.consecutive_losses >= 5:
            risk_score += 20
        elif metrics.consecutive_losses >= 3:
            risk_score += 15
        elif metrics.consecutive_losses >= 2:
            risk_score += 10

        # VaR风险 (15分)
        if metrics.var_95 / account_balance > 0.05:
            risk_score += 15
        elif metrics.var_95 / account_balance > 0.03:
            risk_score += 10
        elif metrics.var_95 / account_balance > 0.02:
            risk_score += 5

        # 胜率风险 (15分)
        if metrics.win_rate < 0.3 and metrics.total_trades >= 10:
            risk_score += 15
        elif metrics.win_rate < 0.4 and metrics.total_trades >= 10:
            risk_score += 10
        elif metrics.win_rate < 0.45 and metrics.total_trades >= 10:
            risk_score += 5

        # 确定风险等级
        if risk_score >= 70:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        # 生成建议
        recommendations = []
        if metrics.current_drawdown > 0.10:
            recommendations.append("当前回撤较大，建议降低仓位或暂停交易")

        if metrics.margin_ratio > 0.5:
            recommendations.append(f"保证金使用率{metrics.margin_ratio*100:.1f}%，建议减少敞口")

        if metrics.consecutive_losses >= 3:
            recommendations.append(f"连续{metrics.consecutive_losses}次亏损，建议检查策略并休息")

        if metrics.var_95 / account_balance > 0.05:
            recommendations.append("VaR风险较高，建议分散投资或减少仓位")

        return {
            "risk_level": risk_level,
            "score": risk_score,
            "max_score": max_score,
            "warnings": metrics.warnings,
            "metrics": metrics,
            "recommendations": recommendations
        }

    def validate_leverage(self, requested_leverage: int) -> bool:
        """验证杠杆倍数"""
        return 1 <= requested_leverage <= self._leverage

    def get_risk_limits(self) -> Dict:
        """获取风险限制"""
        return {
            "max_position_size": self._max_position_size,
            "max_total_position": self._max_total_position,
            "stop_loss_pct": self._stop_loss_pct,
            "take_profit_pct": self._take_profit_pct,
            "max_leverage": self._leverage,
        }

    def set_risk_limits(
        self,
        max_position_size: Optional[float] = None,
        max_total_position: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        leverage: Optional[int] = None,
    ) -> None:
        """设置风险限制"""
        if max_position_size is not None:
            self._max_position_size = max_position_size
        if max_total_position is not None:
            self._max_total_position = max_total_position
        if stop_loss_pct is not None:
            self._stop_loss_pct = stop_loss_pct
        if take_profit_pct is not None:
            self._take_profit_pct = take_profit_pct
        if leverage is not None:
            self._leverage = leverage

        logger.info(f"Risk limits updated: {self.get_risk_limits()}")

    def record_trade(
        self,
        pnl: float,
        entry_price: float,
        exit_price: float,
        position_size: float,
        symbol: str,
        entry_time: datetime,
        exit_time: datetime,
    ) -> None:
        """记录交易（用于计算历史指标）"""
        self.kelly_calculator.add_trade(pnl, entry_price, exit_price, position_size)
        self.metrics_calculator.add_trade(
            pnl=pnl,
            entry_price=entry_price,
            exit_price=exit_price,
            position_size=position_size,
            symbol=symbol,
            entry_time=entry_time,
            exit_time=exit_time
        )

        logger.info(f"Trade recorded: {symbol} PnL={pnl:.2f}USDT")

    def update_market_data(
        self,
        symbol: str,
        price: float,
        atr: Optional[float] = None,
    ) -> None:
        """更新市场数据（用于VaR和相关性计算）"""
        if self.correlation_checker._price_history:
            old_price = list(self.correlation_checker._price_history.get(symbol, []))[-1] if symbol in self.correlation_checker._price_history and len(self.correlation_checker._price_history[symbol]) > 0 else price
            self.var_calculator.add_price_change(old_price, price)

        self.correlation_checker.update_price(symbol, price)

        if atr:
            self.volatility_sizer.update_atr(atr, price)


# 导入numpy（在文件末尾避免循环依赖）
import numpy as np
