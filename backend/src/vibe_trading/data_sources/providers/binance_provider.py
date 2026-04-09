"""
Binance 交易所数据提供者

包装现有的 BinanceClient，实现标准化的 ExchangeProvider 接口。
"""
import asyncio
import logging
from typing import List, Optional, Callable

from .base import ExchangeProvider, ConnectionStatus
from .models import StandardKline, StandardTicker, StandardOrderBook, OrderBookLevel
from ..exchange_config import BinanceExchangeConfig
from ..binance_client import BinanceClient, Kline, KlineInterval


logger = logging.getLogger(__name__)


class BinanceProvider(ExchangeProvider):
    """Binance 交易所数据提供者

    通过适配器模式包装现有的 BinanceClient，
    实现 ExchangeProvider 接口。
    """

    def __init__(self, config: BinanceExchangeConfig):
        """初始化 Binance Provider

        Args:
            config: BinanceExchangeConfig 配置对象
        """
        super().__init__(config)

        # 将 BinanceExchangeConfig 转换为 BinanceConfig
        binance_config = config.to_binance_config()

        # 使用现有的 BinanceClient
        self._client = BinanceClient(binance_config)

        # 跟踪订阅的流
        self._subscribed_streams = set()

    # ==================== 连接管理 ====================

    async def connect(self) -> None:
        """建立连接

        连接 Binance WebSocket。
        """
        try:
            await self._client.ws.connect()
            self._status.connected = True
            logger.info(f"Binance provider connected: {self._status}")
        except Exception as e:
            self._status.connected = False
            self._status.last_error = str(e)
            logger.error(f"Failed to connect Binance provider: {e}")
            raise

    async def disconnect(self) -> None:
        """断开连接"""
        try:
            await self._client.close()
            self._status.connected = False
            logger.info("Binance provider disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting Binance provider: {e}")

    @property
    def exchange_name(self) -> str:
        """交易所名称"""
        return "binance"

    # ==================== 市场数据 ====================

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[StandardKline]:
        """获取K线数据

        Args:
            symbol: 交易对符号
            interval: K线间隔（如 "1m", "5m", "1h"）
            limit: 获取数量
            start_time: 开始时间（毫秒时间戳，可选）
            end_time: 结束时间（毫秒时间戳，可选）

        Returns:
            标准化K线数据列表
        """
        # 转换间隔格式
        try:
            binance_interval = KlineInterval(interval)
        except ValueError:
            logger.warning(f"Invalid interval '{interval}', defaulting to 30m")
            binance_interval = KlineInterval.MINUTE_30

        # 调用现有客户端
        raw_klines = await self._client.rest.get_klines(
            symbol=symbol,
            interval=binance_interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

        # 转换为标准格式
        # raw_klines 是 List[List]，需要先转换为 Kline 对象
        return [
            self._convert_raw_kline(k, symbol, interval)
            for k in raw_klines
        ]

    async def get_ticker(self, symbol: str) -> StandardTicker:
        """获取24小时行情

        Args:
            symbol: 交易对符号

        Returns:
            标准化24小时ticker数据
        """
        # 使用 REST API 直接请求
        data = await self._client.rest._request(
            "GET",
            "/fapi/v1/ticker/24hr",
            params={"symbol": symbol},
        )

        return StandardTicker(
            exchange="binance",
            symbol=data["symbol"],
            price_change=float(data["priceChange"]),
            price_change_percent=float(data["priceChangePercent"]),
            high=float(data["highPrice"]),
            low=float(data["lowPrice"]),
            volume=float(data["volume"]),
            quote_volume=float(data["quoteVolume"]),
            open=float(data["openPrice"]),
            close=float(data["lastPrice"]),
            timestamp=data["closeTime"],
        )

    async def get_orderbook(
        self,
        symbol: str,
        limit: int = 20,
    ) -> StandardOrderBook:
        """获取订单簿

        Args:
            symbol: 交易对符号
            limit: 深度级别

        Returns:
            标准化订单簿数据
        """
        data = await self._client.rest._request(
            "GET",
            "/fapi/v1/depth",
            params={"symbol": symbol, "limit": limit},
        )

        return StandardOrderBook(
            exchange="binance",
            symbol=symbol,
            bids=[
                OrderBookLevel(price=float(p), quantity=float(q))
                for p, q in data["bids"][:limit]
            ],
            asks=[
                OrderBookLevel(price=float(p), quantity=float(q))
                for p, q in data["asks"][:limit]
            ],
            timestamp=data.get("lastUpdateId", 0),
        )

    async def get_current_price(self, symbol: str) -> float:
        """获取当前价格

        Args:
            symbol: 交易对符号

        Returns:
            当前价格
        """
        ticker = await self._client.rest._request(
            "GET",
            "/fapi/v1/ticker/price",
            params={"symbol": symbol},
        )
        return float(ticker["price"])

    # ==================== 订阅管理 ====================

    async def subscribe_klines(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[StandardKline], None],
    ) -> None:
        """订阅K线数据

        Args:
            symbol: 交易对符号
            interval: K线间隔
            callback: 回调函数，接收新的K线数据
        """
        stream_key = f"{symbol}@{interval}"

        # 包装回调函数
        async def wrapped_callback(kline: Kline):
            std_kline = self._convert_kline(kline, symbol, interval)
            if callback:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(std_kline)
                    else:
                        callback(std_kline)
                except Exception as e:
                    logger.error(f"Error in kline callback: {e}")

        # 订阅
        try:
            binance_interval = KlineInterval(interval)
        except ValueError:
            binance_interval = KlineInterval.MINUTE_30

        self._client.ws.subscribe_kline(
            symbol=symbol,
            interval=binance_interval,
            callback=wrapped_callback,
        )

        self._subscribed_streams.add(stream_key)
        logger.info(f"Subscribed to {stream_key}")

    async def unsubscribe_klines(
        self,
        symbol: str,
        interval: str,
    ) -> None:
        """取消订阅K线数据

        Args:
            symbol: 交易对符号
            interval: K线间隔

        Note:
            Binance WebSocket 不支持单独取消订阅。
            需要重新建立连接来移除订阅。
        """
        stream_key = f"{symbol}@{interval}"
        self._subscribed_streams.discard(stream_key)
        logger.info(f"Unsubscribed from {stream_key} (requires reconnection)")

    # ==================== 辅助方法 ====================

    def _convert_raw_kline(
        self,
        raw_kline: list,
        symbol: str,
        interval: str,
    ) -> StandardKline:
        """转换原始REST API数据为StandardKline

        Args:
            raw_kline: 原始REST API返回的列表数据
            symbol: 交易对符号
            interval: K线间隔

        Returns:
            标准化K线对象
        """
        return StandardKline(
            exchange="binance",
            symbol=symbol,
            interval=interval,
            open_time=int(raw_kline[0]),
            open=float(raw_kline[1]),
            high=float(raw_kline[2]),
            low=float(raw_kline[3]),
            close=float(raw_kline[4]),
            volume=float(raw_kline[5]),
            close_time=int(raw_kline[6]),
            quote_volume=float(raw_kline[7]),
            trades=int(raw_kline[8]),
            taker_buy_base=float(raw_kline[9]),
            taker_buy_quote=float(raw_kline[10]),
            is_final=True,  # REST API返回的都是已完成的K线
        )

    def _convert_kline(
        self,
        kline: Kline,
        symbol: str,
        interval: str,
    ) -> StandardKline:
        """转换Kline为StandardKline

        Args:
            kline: Binance Kline对象
            symbol: 交易对符号
            interval: K线间隔

        Returns:
            标准化K线对象
        """
        return StandardKline(
            exchange="binance",
            symbol=kline.symbol or symbol,
            interval=kline.interval or interval,
            open_time=kline.open_time,
            open=kline.open,
            high=kline.high,
            low=kline.low,
            close=kline.close,
            volume=kline.volume,
            close_time=kline.close_time,
            quote_volume=kline.quote_volume,
            trades=kline.trades,
            taker_buy_base=kline.taker_buy_base,
            taker_buy_quote=kline.taker_buy_quote,
            is_final=kline.is_final,
        )
