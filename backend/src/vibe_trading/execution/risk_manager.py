"""
风险管理模块

提供基础风控规则和风险检查。
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from vibe_trading.config.settings import get_settings
from vibe_trading.data_sources.binance_client import OrderSide, OrderType, PositionSide

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

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RiskManager:
    """风险管理器"""

    def __init__(self):
        settings = get_settings()
        self._max_position_size = settings.max_position_size
        self._max_total_position = settings.max_total_position
        self._stop_loss_pct = settings.stop_loss_pct
        self._take_profit_pct = settings.take_profit_pct
        self._leverage = settings.leverage

    async def check_order_risk(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: Optional[float] = None,
        current_positions: Optional[Dict] = None,
        current_balance: Optional[float] = None,
    ) -> RiskCheck:
        """检查订单风险"""
        warnings = []

        # 计算订单价值
        order_value = quantity * (price or 50000)  # 使用默认价格估算

        # 检查单笔仓位大小
        if order_value > self._max_position_size:
            return RiskCheck(
                result=RiskCheckResult.REJECTED,
                reason=f"Order size {order_value:.2f} USDT exceeds maximum {self._max_position_size} USDT",
            )

        # 检查总仓位
        if current_positions:
            total_exposure = current_positions.get("total_exposure", 0)
            if total_exposure + order_value > self._max_total_position:
                return RiskCheck(
                    result=RiskCheckResult.REJECTED,
                    reason=f"Total exposure {total_exposure + order_value:.2f} USDT exceeds maximum {self._max_total_position} USDT",
                )

            # 检查是否接近上限
            if total_exposure + order_value > self._max_total_position * 0.8:
                warnings.append(
                    f"Total exposure will be {total_exposure + order_value:.2f} USDT, "
                    f"close to maximum {self._max_total_position} USDT"
                )

        # 检查杠杆
        if current_balance:
            required_margin = order_value / self._leverage
            margin_ratio = required_margin / current_balance

            if margin_ratio > 0.5:
                return RiskCheck(
                    result=RiskCheckResult.REJECTED,
                    reason=f"Order requires {margin_ratio*100:.1f}% of balance, exceeds 50% limit",
                )

            if margin_ratio > 0.3:
                warnings.append(
                    f"Order requires {margin_ratio*100:.1f}% of balance, consider reducing size"
                )

        if warnings:
            return RiskCheck(result=RiskCheckResult.WARNING, reason="Order approved with warnings", warnings=warnings)

        return RiskCheck(result=RiskCheckResult.APPROVED, reason="Order approved")

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        risk_per_trade: float = 0.02,
        account_balance: float = 10000.0,
    ) -> float:
        """计算基于风险的仓位大小"""
        risk_amount = account_balance * risk_per_trade
        stop_distance = abs(entry_price - stop_loss_price) / entry_price

        if stop_distance == 0:
            return self._max_position_size / entry_price

        position_value = risk_amount / stop_distance
        position_size = min(position_value, self._max_position_size) / entry_price

        return position_size

    def calculate_stop_loss(
        self, entry_price: float, position_side: PositionSide, atr: Optional[float] = None
    ) -> float:
        """计算止损价格"""
        if atr:
            # 基于 ATR 的动态止损
            stop_distance = atr * 2
        else:
            # 固定百分比止损
            stop_distance = entry_price * self._stop_loss_pct

        if position_side == PositionSide.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def calculate_take_profit(
        self, entry_price: float, position_side: PositionSide, atr: Optional[float] = None
    ) -> float:
        """计算止盈价格"""
        if atr:
            # 基于 ATR 的动态止盈
            profit_distance = atr * 3
        else:
            # 固定百分比止盈
            profit_distance = entry_price * self._take_profit_pct

        if position_side == PositionSide.LONG:
            return entry_price + profit_distance
        else:
            return entry_price - profit_distance

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
