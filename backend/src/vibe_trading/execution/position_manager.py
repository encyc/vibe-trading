"""
持仓管理模块

管理交易持仓的生命周期。
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from vibe_trading.data_sources.binance_client import Position, PositionSide, OrderSide
from vibe_trading.execution.order_executor import OrderExecutor

logger = logging.getLogger(__name__)


@dataclass
class PositionRisk:
    """持仓风险信息"""
    position: Position
    unrealized_pnl_pct: float
    distance_to_liquidation: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL


class PositionManager:
    """持仓管理器"""

    def __init__(self, executor: OrderExecutor):
        self._executor = executor
        self._positions: Dict[str, Position] = {}
        self._max_position_size = 0.1  # 最大仓位 (USDT)

    async def update_positions(self) -> None:
        """更新持仓信息"""
        positions = await self._executor.get_positions()
        self._positions.clear()
        for pos in positions:
            key = f"{pos.symbol}_{pos.position_side.value}"
            self._positions[key] = pos

    def get_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self._positions.values())

    def get_position(self, symbol: str, position_side: PositionSide) -> Optional[Position]:
        """获取指定持仓"""
        key = f"{symbol}_{position_side.value}"
        return self._positions.get(key)

    def has_position(self, symbol: str, position_side: Optional[PositionSide] = None) -> bool:
        """检查是否有持仓"""
        if position_side:
            key = f"{symbol}_{position_side.value}"
            return key in self._positions
        return any(k.startswith(symbol) for k in self._positions.keys())

    def get_total_exposure(self) -> float:
        """获取总敞口"""
        return sum(abs(pos.notional) for pos in self._positions.values())

    def get_total_unrealized_pnl(self) -> float:
        """获取总未实现盈亏"""
        return sum(pos.unrealized_profit for pos in self._positions.values())

    async def close_position(
        self, symbol: str, position_side: PositionSide, quantity: Optional[float] = None
    ) -> bool:
        """平仓"""
        pos = self.get_position(symbol, position_side)
        if not pos:
            logger.warning(f"No position to close: {symbol}_{position_side.value}")
            return False

        close_qty = quantity if quantity else abs(pos.position_amount)

        try:
            # 确定平仓方向
            side = OrderSide.SELL if position_side == PositionSide.LONG else OrderSide.BUY

            await self._executor.place_order(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=close_qty,
                position_side=position_side,
            )
            logger.info(f"Closed position: {symbol} {position_side.value} {close_qty}")
            return True
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False

    async def close_all_positions(self) -> None:
        """平掉所有持仓"""
        for pos in self.get_positions():
            await self.close_position(pos.symbol, pos.position_side)

    def assess_position_risks(self) -> List[PositionRisk]:
        """评估持仓风险"""
        risks = []

        for pos in self.get_positions():
            if pos.position_amount == 0:
                continue

            # 计算未实现盈亏百分比
            if pos.entry_price > 0:
                if pos.position_side == PositionSide.LONG:
                    pnl_pct = (pos.mark_price - pos.entry_price) / pos.entry_price * 100
                else:
                    pnl_pct = (pos.entry_price - pos.mark_price) / pos.entry_price * 100
            else:
                pnl_pct = 0.0

            # 计算距离强平的距离
            if pos.liquidation_price > 0:
                if pos.position_side == PositionSide.LONG:
                    dist_to_liq = ((pos.mark_price - pos.liquidation_price) / pos.mark_price) * 100
                else:
                    dist_to_liq = ((pos.liquidation_price - pos.mark_price) / pos.mark_price) * 100
            else:
                dist_to_liq = 100.0  # 无强平风险

            # 评估风险等级
            if dist_to_liq < 10:
                risk_level = "CRITICAL"
            elif dist_to_liq < 20:
                risk_level = "HIGH"
            elif dist_to_liq < 40:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            risks.append(
                PositionRisk(
                    position=pos,
                    unrealized_pnl_pct=pnl_pct,
                    distance_to_liquidation=dist_to_liq,
                    risk_level=risk_level,
                )
            )

        return risks

    def get_risk_summary(self) -> dict:
        """获取风险摘要"""
        risks = self.assess_position_risks()

        return {
            "total_positions": len(self.get_positions()),
            "total_exposure": self.get_total_exposure(),
            "total_unrealized_pnl": self.get_total_unrealized_pnl(),
            "risk_levels": {
                "CRITICAL": sum(1 for r in risks if r.risk_level == "CRITICAL"),
                "HIGH": sum(1 for r in risks if r.risk_level == "HIGH"),
                "MEDIUM": sum(1 for r in risks if r.risk_level == "MEDIUM"),
                "LOW": sum(1 for r in risks if r.risk_level == "LOW"),
            },
            "positions": risks,
        }
