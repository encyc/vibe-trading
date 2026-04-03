"""
WebSocket管理器 - 管理Binance WebSocket连接

支持实时K线订阅和自动重连
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

from binance.client import AsyncClient
from binance import BinanceSocketManager
from binance.streams import BinanceSocketManager

from vibe_trading.data_sources.binance_client import Kline
from pi_logger import get_logger, info, warning, error, success

logger = logging.getLogger(__name__)
log = get_logger("WebSocketManager")


@dataclass
class StreamConfig:
    """流配置"""
    symbol: str
    interval: str
    callback: Callable[[Kline], None]
    enabled: bool = True


class WebSocketManager:
    """
    WebSocket管理器

    管理Binance WebSocket连接，支持：
    - 多symbol订阅
    - 自动重连
    - 回调处理
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # Binance客户端
        self._client: Optional[AsyncClient] = None
        self._bsm: Optional[BinanceSocketManager] = None

        # 流管理
        self._streams: Dict[str, StreamConfig] = {}
        self._active_connections: Dict[str, Any] = {}
        self._running = False

        # 重连配置
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 5  # 秒
        self._reconnect_attempts = 0

        logger.info("WebSocketManager initialized")

    async def initialize(self) -> None:
        """初始化Binance客户端"""
        if self._client is not None:
            return

        try:
            self._client = AsyncClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
            )
            self._bsm = BinanceSocketManager(self._client)
            log.success("Binance WebSocket客户端初始化成功")
        except Exception as e:
            log.error(f"WebSocket客户端初始化失败: {e}")
            raise

    async def subscribe_kline(
        self,
        symbol: str,
        interval: str,
        callback: Callable[[Kline], None],
    ) -> None:
        """
        订阅K线流

        Args:
            symbol: 交易对符号，如BTCUSDT
            interval: K线间隔，如1m, 5m, 15m, 30m, 1h, 4h, 1d
            callback: K线数据到达时的回调函数
        """
        stream_key = f"{symbol.lower()}@kline_{interval}"

        if stream_key in self._streams:
            log.warning(f"{symbol} {interval} 已订阅，跳过")
            return

        self._streams[stream_key] = StreamConfig(
            symbol=symbol,
            interval=interval,
            callback=callback,
        )

        log.success(f"已订阅 {symbol} {interval} K线流")

    async def unsubscribe_kline(self, symbol: str, interval: str) -> None:
        """取消订阅K线流"""
        stream_key = f"{symbol.lower()}@kline_{interval}"

        if stream_key in self._streams:
            del self._streams[stream_key]
            log.success(f"已取消订阅 {symbol} {interval}")

    async def start(self) -> None:
        """
        启动WebSocket连接

        开始监听所有订阅的流，新K线到达时触发回调
        """
        if not self._streams:
            warning("没有订阅任何流，无法启动", tag="WebSocket")
            return

        await self.initialize()
        self._running = True
        self._reconnect_attempts = 0

        log.info(f"🚀 启动WebSocket监听，订阅数量: {len(self._streams)}")

        await self._start_with_reconnect()

    async def _start_with_reconnect(self) -> None:
        """启动WebSocket连接（带重连）"""
        while self._running and self._reconnect_attempts < self._max_reconnect_attempts:
            try:
                await self._connect_streams()

                # 成功连接，重置重连计数
                self._reconnect_attempts = 0

                # 保持运行
                while self._running:
                    await asyncio.sleep(1)

            except Exception as e:
                self._reconnect_attempts += 1

                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    log.error(f"WebSocket重连失败，达到最大重连次数: {e}")
                    break

                log.warning(
                    f"WebSocket断开，{self._reconnect_delay}秒后重试 ({self._reconnect_attempts}/{self._max_reconnect_attempts})",
                    tag="WebSocket"
                )
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_streams(self) -> None:
        """连接所有订阅的流"""
        streams = []
        for stream_key, config in self._streams.items():
            if not config.enabled:
                continue
            streams.append(stream_key)

        if not streams:
            return

        # 创建多流socket
        stream_path = "/".join(streams)
        socket = self._bsm.multiplex_socket(streams)

        log.success(f"WebSocket已连接: {len(streams)} 个流")

        # 处理消息
        async with socket as stream:
            async for msg in stream:
                if not self._running:
                    break

                try:
                    await self._handle_message(msg)
                except Exception as e:
                    logger.error(f"处理消息失败: {e}", exc_info=True)

    async def _handle_message(self, msg: dict) -> None:
        """处理WebSocket消息"""
        if not msg or "stream" not in msg:
            return

        stream = msg["stream"]
        data = msg.get("data", {})

        if not data or "k" not in data:
            return

        kline_data = data["k"]

        # 解析K线数据
        kline = Kline(
            symbol=kline_data.get("s", ""),
            interval=self._streams.get(stream, StreamConfig("", "", None)).interval,
            open_time=kline_data.get("t", 0),
            open=float(kline_data.get("o", 0)),
            high=float(kline_data.get("h", 0)),
            low=float(kline_data.get("l", 0)),
            close=float(kline_data.get("c", 0)),
            volume=float(kline_data.get("v", 0)),
            close_time=kline_data.get("T", 0),
            quote_volume=float(kline_data.get("q", 0)),
            trades=int(kline_data.get("n", 0)),
            taker_buy_base=float(kline_data.get("V", 0)),
            taker_buy_quote=float(kline_data.get("Q", 0)),
            is_final=kline_data.get("x", False),
        )

        # 只在K线完成时触发回调
        if kline.is_final:
            stream_config = self._streams.get(stream)
            if stream_config and stream_config.callback:
                try:
                    # 如果是协程，await它
                    result = stream_config.callback(kline)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"回调执行失败: {e}", exc_info=True)

    async def stop(self) -> None:
        """停止WebSocket连接"""
        log.info("停止WebSocket连接...")
        self._running = False

        # 关闭所有连接
        for stream_key, conn in self._active_connections.items():
            try:
                await conn.close()
            except Exception:
                pass

        self._active_connections.clear()

        # 关闭BSM
        if self._bsm:
            await self._bsm.close()
            self._bsm = None

        # 关闭客户端
        if self._client:
            await self._client.close_connection()
            await self._client.close()
            self._client = None

        log.success("WebSocket已停止")

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running

    def get_active_streams(self) -> List[str]:
        """获取活跃的流列表"""
        return [k for k, v in self._streams.items() if v.enabled]


# 单例模式
_websocket_manager: Optional[WebSocketManager] = None


def get_websocket_manager(
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    testnet: bool = False,
) -> WebSocketManager:
    """获取WebSocket管理器单例"""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )
    return _websocket_manager
