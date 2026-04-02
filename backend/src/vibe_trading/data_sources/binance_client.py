"""
Binance API 客户端

提供 WebSocket K线订阅和 REST API 功能。
支持 Testnet 和 Mainnet 切换。
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import websockets
from pydantic import BaseModel

from vibe_trading.config.binance_config import BinanceConfig, BinanceEnvironment

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================


class KlineInterval(str, Enum):
    """K线间隔"""
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    DAY_3 = "3d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


@dataclass
class Kline:
    """K线数据"""

    symbol: str
    interval: str
    open_time: int  # 毫秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int
    taker_buy_base: float
    taker_buy_quote: float
    is_final: bool

    @classmethod
    def from_stream(cls, data: dict) -> "Kline":
        """从 WebSocket 流数据创建"""
        k = data["k"]
        return cls(
            symbol=data["s"],
            interval=k["i"],
            open_time=k["t"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            close_time=k["T"],
            quote_volume=float(k["q"]),
            trades=k["n"],
            taker_buy_base=float(k["V"]),
            taker_buy_quote=float(k["Q"]),
            is_final=k["x"],
        )

    @classmethod
    def from_rest(cls, data: list) -> "Kline":
        """从 REST API 数据创建"""
        return cls(
            symbol="",  # REST API 返回不包含 symbol
            interval="",
            open_time=int(data[0]),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            close_time=int(data[6]),
            quote_volume=float(data[7]),
            trades=int(data[8]),
            taker_buy_base=float(data[9]),
            taker_buy_quote=float(data[10]),
            is_final=True,
        )

    @property
    def open_datetime(self) -> datetime:
        """开盘时间"""
        return datetime.fromtimestamp(self.open_time / 1000)

    @property
    def close_datetime(self) -> datetime:
        """收盘时间"""
        return datetime.fromtimestamp(self.close_time / 1000)


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class PositionSide(str, Enum):
    """持仓方向"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Order:
    """订单"""

    symbol: str
    order_id: int
    client_order_id: str
    side: OrderSide
    order_type: OrderType
    position_side: PositionSide
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = ""
    executed_qty: float = 0.0
    cum_qty: float = 0.0


@dataclass
class Position:
    """持仓"""

    symbol: str
    position_amount: float
    entry_price: float
    mark_price: float
    unrealized_profit: float
    liquidation_price: float
    leverage: int
    position_side: PositionSide
    notional: float
    isolated: bool = False
    adl_quantile: int = 0


# =============================================================================
# Binance WebSocket 客户端
# =============================================================================


class BinanceWebSocketClient:
    """Binance WebSocket 客户端"""

    def __init__(self, config: BinanceConfig):
        self.config = config
        self._ws = None
        self._running = False
        self._kline_callbacks: Dict[str, List[Callable]] = {}

    async def connect(self) -> None:
        """连接 WebSocket"""
        if self._ws is not None:
            return

        url = f"{self.config.ws_base_url}/ws"
        logger.info(f"Connecting to WebSocket: {url}")
        self._ws = await websockets.connect(url)
        self._running = True

    async def disconnect(self) -> None:
        """断开 WebSocket"""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    def subscribe_kline(
        self,
        symbol: str,
        interval: KlineInterval,
        callback: Callable[[Kline], None],
    ) -> None:
        """订阅 K线数据"""
        stream_name = f"{symbol.lower()}@kline_{interval.value}"
        self._kline_callbacks[stream_name] = self._kline_callbacks.get(stream_name, [])
        self._kline_callbacks[stream_name].append(callback)

        logger.info(f"Subscribed to kline stream: {stream_name}")

    async def _listen(self) -> None:
        """监听 WebSocket 消息"""
        if self._ws is None:
            await self.connect()

        async for message in self._ws:
            if not self._running:
                break

            try:
                data = json.loads(message)
                stream = data.get("stream", "")

                # 处理 K线数据
                if "@kline_" in stream:
                    callbacks = self._kline_callbacks.get(stream, [])
                    if callbacks:
                        kline = Kline.from_stream(data)
                        for callback in callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(kline)
                                else:
                                    callback(kline)
                            except Exception as e:
                                logger.error(f"Error in kline callback: {e}")

            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def start(self) -> None:
        """启动 WebSocket 监听"""
        await self.connect()
        await self._listen()

    async def subscribe_combined_stream(
        self,
        streams: List[str],
        callback: Callable[[dict], None],
    ) -> None:
        """订阅组合流"""
        stream_path = "/".join(streams)
        url = f"{self.config.ws_base_url}/stream?streams={stream_path}"

        async with websockets.connect(url) as ws:
            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    callback(data)
                except Exception as e:
                    logger.error(f"Error in combined stream callback: {e}")


# =============================================================================
# Binance REST API 客户端
# =============================================================================


class BinanceRestClient:
    """Binance REST API 客户端"""

    def __init__(self, config: BinanceConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """关闭 HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _sign(self, params: dict) -> dict:
        """签名请求参数"""
        import hmac
        import hashlib

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.config.api_secret.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    async def _request(
        self,
        method: str,
        endpoint: str,
        signed: bool = False,
        **kwargs,
    ) -> dict:
        """发送 HTTP 请求"""
        session = await self._get_session()
        url = f"{self.config.rest_base_url}{endpoint}"

        params = kwargs.get("params", {})
        headers = kwargs.get("headers", {})

        headers["X-MBX-APIKEY"] = self.config.api_key

        if signed:
            params["timestamp"] = int(asyncio.get_event_loop().time() * 1000)
            params = self._sign(params)

        kwargs["params"] = params
        kwargs["headers"] = headers

        async with session.request(method, url, **kwargs) as response:
            data = await response.json()
            if response.status != 200:
                logger.error(f"API Error: {data}")
                raise Exception(f"API Error: {data}")
            return data

    async def get_exchange_info(self) -> dict:
        """获取交易所信息"""
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    async def get_klines(
        self,
        symbol: str,
        interval: KlineInterval,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        """获取 K线数据"""
        params = {"symbol": symbol, "interval": interval.value, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        return await self._request("GET", "/fapi/v1/klines", **{"params": params})

    async def get_account_info(self) -> dict:
        """获取账户信息"""
        return await self._request("GET", "/fapi/v2/account", signed=True)

    async def get_position(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息"""
        params = {}
        if symbol:
            params["symbol"] = symbol

        data = await self._request("GET", "/fapi/v2/positionRisk", signed=True, **{"params": params})

        positions = []
        for item in data:
            if float(item["positionAmt"]) != 0:
                positions.append(
                    Position(
                        symbol=item["symbol"],
                        position_amount=float(item["positionAmt"]),
                        entry_price=float(item["entryPrice"]),
                        mark_price=float(item["markPrice"]),
                        unrealized_profit=float(item["unRealizedProfit"]),
                        liquidation_price=float(item["liquidationPrice"]),
                        leverage=int(item["leverage"]),
                        position_side=PositionSide(item["positionSide"]),
                        notional=float(item["notional"]),
                        isolated=item["isolated"],
                        adl_quantile=item["adlQuantile"],
                    )
                )
        return positions

    async def get_balance(self) -> dict:
        """获取账户余额"""
        data = await self._request("GET", "/fapi/v2/balance", signed=True)
        balance = {}
        for item in data:
            if float(item["balance"]) != 0:
                balance[item["asset"]] = {
                    "balance": float(item["balance"]),
                    "available": float(item["availableBalance"]),
                    "cross_wallet_balance": float(item["crossWalletBalance"]),
                }
        return balance

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        position_side: Optional[PositionSide] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Order:
        """下单"""
        params = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "quantity": quantity,
        }

        if position_side:
            params["positionSide"] = position_side.value
        if price is not None:
            params["price"] = price
        if stop_price is not None:
            params["stopPrice"] = stop_price
        if reduce_only:
            params["reduceOnly"] = "true"

        data = await self._request("POST", "/fapi/v1/order", signed=True, **{"params": params})

        return Order(
            symbol=data["symbol"],
            order_id=int(data["orderId"]),
            client_order_id=data["clientOrderId"],
            side=OrderSide(data["side"]),
            order_type=OrderType(data["type"]),
            position_side=PositionSide(data["positionSide"]),
            quantity=float(data["origQty"]),
            price=float(data.get("price", 0)),
            stop_price=float(data.get("stopPrice", 0)),
            status=data["status"],
            executed_qty=float(data["executedQty"]),
            cum_qty=float(data["cumQty"]),
        )

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> dict:
        """取消订单"""
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["origClientOrderId"] = client_order_id

        return await self._request("DELETE", "/fapi/v1/order", signed=True, **{"params": params})

    async def cancel_all_orders(self, symbol: str) -> dict:
        """取消所有订单"""
        return await self._request(
            "DELETE", "/fapi/v1/allOpenOrders", signed=True, **{"params": {"symbol": symbol}}
        )

    async def set_leverage(self, symbol: str, leverage: int) -> dict:
        """设置杠杆倍数"""
        return await self._request(
            "POST",
            "/fapi/v1/leverage",
            signed=True,
            **{"params": {"symbol": symbol, "leverage": leverage}},
        )

    async def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        """设置保证金模式（CROSSED/ISOLATED）"""
        return await self._request(
            "POST",
            "/fapi/v1/marginType",
            signed=True,
            **{"params": {"symbol": symbol, "marginType": margin_type}},
        )


# =============================================================================
# 组合客户端
# =============================================================================


class BinanceClient:
    """Binance 组合客户端（WebSocket + REST）"""

    def __init__(self, config: Optional[BinanceConfig] = None):
        self.config = config or BinanceConfig.from_env()
        self.ws = BinanceWebSocketClient(self.config)
        self.rest = BinanceRestClient(self.config)

    async def close(self) -> None:
        """关闭所有连接"""
        await self.ws.disconnect()
        await self.rest.close()
