"""
交易所数据提供者抽象基类

定义所有交易所必须实现的标准接口。
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
import time

from .models import StandardKline, StandardTicker, StandardOrderBook


@dataclass
class ConnectionStatus:
    """连接状态

    跟踪交易所的连接状态和健康信息。
    """

    connected: bool  # 是否已连接
    latency_ms: float  # 延迟（毫秒）
    last_error: Optional[str] = None  # 最后的错误信息
    last_ping: Optional[float] = None  # 最后一次ping时间戳

    def __str__(self) -> str:
        status = "✓ Connected" if self.connected else "✗ Disconnected"
        latency_str = f", {self.latency_ms:.0f}ms" if self.connected else ""
        error_str = f" - {self.last_error}" if self.last_error else ""
        return f"{status}{latency_str}{error_str}"


class ExchangeProvider(ABC):
    """交易所数据提供者抽象接口

    所有交易所实现必须继承此类并实现所有抽象方法。
    """

    def __init__(self, config: Any):
        """初始化提供者

        Args:
            config: 交易所配置对象
        """
        self.config = config
        self._status = ConnectionStatus(connected=False, latency_ms=0)
        self._callbacks: Dict[str, List[Callable]] = {}

    # ==================== 连接管理 ====================

    @abstractmethod
    async def connect(self) -> None:
        """建立连接

        初始化与交易所的连接，包括WebSocket和REST API。
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接

        清理所有连接和资源。
        """
        pass

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """交易所名称

        Returns:
            交易所标识符（如 "binance", "okx"）
        """
        pass

    # ==================== 市场数据 ====================

    @abstractmethod
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
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> StandardTicker:
        """获取24小时行情

        Args:
            symbol: 交易对符号

        Returns:
            标准化24小时ticker数据
        """
        pass

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> StandardOrderBook:
        """获取订单簿

        Args:
            symbol: 交易对符号
            limit: 深度级别

        Returns:
            标准化订单簿数据
        """
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """获取当前价格

        Args:
            symbol: 交易对符号

        Returns:
            当前价格
        """
        pass

    # ==================== 订阅管理 ====================

    @abstractmethod
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
        pass

    @abstractmethod
    async def unsubscribe_klines(self, symbol: str, interval: str) -> None:
        """取消订阅K线数据

        Args:
            symbol: 交易对符号
            interval: K线间隔
        """
        pass

    # ==================== 状态查询 ====================

    @property
    def status(self) -> ConnectionStatus:
        """获取连接状态

        Returns:
            当前连接状态
        """
        return self._status

    async def health_check(self) -> bool:
        """健康检查

        尝试执行一个简单的操作来验证连接是否正常。

        Returns:
            True 如果连接健康，False 否则
        """
        try:
            # 尝试获取一个简单的数据
            start_time = time.time()
            await self.get_current_price("BTCUSDT")
            latency = (time.time() - start_time) * 1000

            self._status.connected = True
            self._status.latency_ms = latency
            self._status.last_error = None
            return True
        except Exception as e:
            self._status.connected = False
            self._status.last_error = str(e)
            return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(exchange='{self.exchange_name}', status={self._status})"
