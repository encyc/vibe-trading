"""
订单执行模块

提供订单执行的抽象层，支持 Paper Trading 和 Binance 实盘。
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import uuid

from vibe_trading.data_sources.binance_client import (
    BinanceClient,
    BinanceConfig,
    Position,
    OrderSide,
    OrderType,
    PositionSide,
)
from vibe_trading.config.binance_config import BinanceEnvironment
from vibe_trading.config.settings import get_settings

logger = logging.getLogger(__name__)


class TradingMode(str, Enum):
    """交易模式"""
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"


@dataclass
class OrderResult:
    """订单执行结果"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float]
    filled_price: Optional[float]
    filled_quantity: float
    status: str
    timestamp: int
    is_paper: bool


@dataclass
class PaperPosition:
    """Paper Trading 持仓"""
    symbol: str
    position_side: PositionSide
    entry_price: float
    quantity: float
    leverage: int = 5
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def notional(self) -> float:
        """持仓价值"""
        return self.quantity * self.entry_price

    def update_unrealized_pnl(self, current_price: float) -> None:
        """更新未实现盈亏"""
        if self.position_side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity


class OrderExecutor(ABC):
    """订单执行器抽象基类"""

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        position_side: Optional[PositionSide] = None,
    ) -> OrderResult:
        """下单"""
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """获取余额"""
        pass


class PaperOrderExecutor(OrderExecutor):
    """Paper Trading 订单执行器"""

    def __init__(self, initial_balance: float = 10000.0):
        self._positions: Dict[str, PaperPosition] = {}
        self._balance = initial_balance
        self._orders: Dict[str, OrderResult] = {}
        self._current_prices: Dict[str, float] = {}

    def update_price(self, symbol: str, price: float) -> None:
        """更新当前价格（模拟市场价格）"""
        self._current_prices[symbol] = price
        # 更新所有持仓的未实现盈亏
        for pos in self._positions.values():
            if pos.symbol == symbol:
                pos.update_unrealized_pnl(price)

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        position_side: Optional[PositionSide] = None,
    ) -> OrderResult:
        """下单（模拟）"""
        order_id = f"paper_{uuid.uuid4().hex[:8]}"
        timestamp = int(datetime.now().timestamp() * 1000)

        # 获取执行价格
        if price is None:
            execution_price = self._current_prices.get(symbol, 0)
        else:
            execution_price = price

        if execution_price == 0:
            logger.warning(f"No price available for {symbol}, using mock price 50000")
            execution_price = 50000.0  # 模拟价格

        filled_quantity = quantity
        status = "FILLED"

        # 更新持仓
        if position_side:
            pos_key = f"{symbol}_{position_side.value}"

            if side == OrderSide.BUY:
                if pos_key in self._positions:
                    # 加仓
                    self._positions[pos_key].quantity += quantity
                    avg_price = (
                        self._positions[pos_key].entry_price * (self._positions[pos_key].quantity - quantity)
                        + execution_price * quantity
                    ) / self._positions[pos_key].quantity
                    self._positions[pos_key].entry_price = avg_price
                else:
                    # 新建仓位
                    self._positions[pos_key] = PaperPosition(
                        symbol=symbol,
                        position_side=position_side,
                        entry_price=execution_price,
                        quantity=quantity,
                    )
            else:
                # 平仓
                if pos_key in self._positions:
                    pos = self._positions[pos_key]
                    pos.realized_pnl += pos.unrealized_pnl
                    pos.quantity -= quantity

                    if pos.quantity <= 0:
                        del self._positions[pos_key]
                else:
                    logger.warning(f"No position to close for {pos_key}")

        result = OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            filled_price=execution_price,
            filled_quantity=filled_quantity,
            status=status,
            timestamp=timestamp,
            is_paper=True,
        )

        self._orders[order_id] = result
        logger.info(f"Paper order placed: {side.value} {quantity} {symbol} @ {execution_price}")

        return result

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单（模拟）"""
        if order_id in self._orders:
            self._orders[order_id].status = "CANCELED"
            logger.info(f"Paper order canceled: {order_id}")
            return True
        return False

    async def get_positions(self) -> List[Position]:
        """获取持仓（转换为标准格式）"""
        positions = []
        for pos in self._positions.values():
            current_price = self._current_prices.get(pos.symbol, pos.entry_price)
            pos.update_unrealized_pnl(current_price)

            positions.append(
                Position(
                    symbol=pos.symbol,
                    position_amount=pos.quantity,
                    entry_price=pos.entry_price,
                    mark_price=current_price,
                    unrealized_profit=pos.unrealized_pnl,
                    liquidation_price=0.0,  # Paper trading 不计算强平价
                    leverage=pos.leverage,
                    position_side=pos.position_side,
                    notional=pos.notional,
                    isolated=False,
                    adl_quantile=0,
                )
            )
        return positions

    async def get_balance(self) -> Dict[str, float]:
        """获取余额"""
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self._positions.values())
        total_realized_pnl = sum(pos.realized_pnl for pos in self._positions.values())

        return {
            "USDT": {
                "balance": self._balance + total_realized_pnl,
                "available": self._balance + total_realized_pnl + total_unrealized_pnl,
                "unrealized_pnl": total_unrealized_pnl,
                "realized_pnl": total_realized_pnl,
            }
        }


class BinanceOrderExecutor(OrderExecutor):
    """Binance 实盘订单执行器"""

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, dry_run: bool = False):
        config = BinanceConfig(
            environment=BinanceEnvironment.TESTNET if testnet else BinanceEnvironment.MAINNET,
            api_key=api_key,
            api_secret=api_secret,
        )
        self._client = BinanceClient(config)
        self._dry_run = dry_run  # dry-run模式：只打印订单不执行

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        position_side: Optional[PositionSide] = None,
    ) -> OrderResult:
        """下单"""
        if self._dry_run:
            # ========== dry-run模式：只打印不执行 ==========
            order_id = f"dryrun_{uuid.uuid4().hex[:8]}"
            timestamp = int(datetime.now().timestamp() * 1000)

            logger.info("=" * 60)
            logger.info("🚨 [DRY-RUN] 订单打印 (不会实际执行)")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {side.value}")
            logger.info(f"  Type: {order_type.value}")
            logger.info(f"  Quantity: {quantity}")
            logger.info(f"  Price: {price}")
            logger.info(f"  Position Side: {position_side.value if position_side else 'N/A'}")
            logger.info("=" * 60)

            return OrderResult(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                filled_price=price,  # dry-run假设立即成交
                filled_quantity=quantity,
                status="FILLED",  # dry-run假设立即成交
                timestamp=timestamp,
                is_paper=False,  # 不是paper，是dry-run
            )

        # 真实执行
        order = await self._client.rest.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            position_side=position_side,
        )

        return OrderResult(
            order_id=str(order.order_id),
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.price,
            filled_price=order.price if order.status == "FILLED" else None,
            filled_quantity=order.executed_qty,
            status=order.status,
            timestamp=int(datetime.now().timestamp() * 1000),
            is_paper=False,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        if self._dry_run:
            logger.info(f"🚨 [DRY-RUN] 取消订单: {order_id} (不会实际执行)")
            return True

        try:
            await self._client.rest.cancel_order(symbol, order_id=int(order_id))
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        return await self._client.rest.get_position()

    async def get_balance(self) -> Dict[str, float]:
        """获取余额"""
        balance = await self._client.rest.get_balance()
        return {k: v["balance"] for k, v in balance.items()}

    async def close(self) -> None:
        """关闭连接"""
        await self._client.close()


def create_executor(mode: TradingMode = TradingMode.PAPER, dry_run: bool = False) -> OrderExecutor:
    """创建订单执行器

    Args:
        mode: 交易模式 (PAPER 或 LIVE)
        dry_run: 是否为dry-run模式 (仅打印订单不执行，仅适用于LIVE模式)
    """
    settings = get_settings()

    if mode == TradingMode.PAPER:
        logger.info("Creating Paper Trading executor")
        return PaperOrderExecutor()
    elif mode == TradingMode.TESTNET:
        if not settings.binance_testnet_api_key or not settings.binance_testnet_api_secret:
            raise ValueError("BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET are required for testnet trading")

        logger.info("Creating Binance Testnet executor")
        return BinanceOrderExecutor(
            api_key=settings.binance_testnet_api_key,
            api_secret=settings.binance_testnet_api_secret,
            testnet=True,
            dry_run=dry_run,
        )
    else:
        if dry_run:
            logger.info("Creating Binance Live executor (DRY-RUN mode - orders will be printed but not executed)")
        else:
            logger.info("Creating Binance Live executor (orders will be executed)")

        if not settings.binance_api_key or not settings.binance_api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required for live trading")

        return BinanceOrderExecutor(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_api_secret,
            testnet=False,
            dry_run=dry_run,
        )
