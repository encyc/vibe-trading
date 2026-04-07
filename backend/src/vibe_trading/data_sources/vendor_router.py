"""
数据源路由器 - 支持多数据源自动回退

对应TradeAgents的dataflows/interface.py功能。
支持主数据源失败时自动切换到备用数据源。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from pi_logger import get_logger

logger = get_logger(__name__)


class DataSourceType(str, Enum):
    """数据源类型"""
    BINANCE = "binance"
    COINGECKO = "coingecko"
    CRYPTOCOMPARE = "cryptocompare"
    OKX = "okx"


class DataType(str, Enum):
    """数据类型"""
    KLINE = "kline"  # K线数据
    TICKER = "ticker"  # 24小时行情
    FUNDING_RATE = "funding_rate"  # 资金费率
    OPEN_INTEREST = "open_interest"  # 持仓量
    LONG_SHORT_RATIO = "long_short_ratio"  # 多空比
    NEWS = "news"  # 新闻
    SENTIMENT = "sentiment"  # 情绪


@dataclass
class VendorMethod:
    """供应商方法"""
    vendor: DataSourceType
    method: Callable
    priority: int = 0  # 优先级（数字越小优先级越高）


class DataSourceException(Exception):
    """数据源异常"""
    def __init__(self, message: str, vendor: DataSourceType, original_error: Optional[Exception] = None):
        self.message = message
        self.vendor = vendor
        self.original_error = original_error
        super().__init__(f"[{vendor.value}] {message}")


class RateLimitException(DataSourceException):
    """速率限制异常"""
    pass


class DataSourceRouter:
    """
    数据源路由器

    管理多个数据源，支持自动回退和负载均衡。
    """

    def __init__(self):
        """初始化路由器"""
        # 方法映射：数据类型 -> 供应商方法列表
        self._method_registry: Dict[DataType, List[VendorMethod]] = {}

        # 性能统计
        self._performance_stats: Dict[DataSourceType, Dict[str, Any]] = {}

        # 回退历史（用于学习）
        self._fallback_history: List[Tuple[DataType, DataSourceType, DataSourceType]] = []

    def register_method(
        self,
        data_type: DataType,
        vendor: DataSourceType,
        method: Callable,
        priority: int = 0,
    ):
        """
        注册数据源方法

        Args:
            data_type: 数据类型
            vendor: 数据源
            method: 获取方法
            priority: 优先级（数字越小优先级越高）
        """
        if data_type not in self._method_registry:
            self._method_registry[data_type] = []

        vendor_method = VendorMethod(
            vendor=vendor,
            method=method,
            priority=priority,
        )

        self._method_registry[data_type].append(vendor_method)

        # 按优先级排序
        self._method_registry[data_type].sort(key=lambda x: x.priority)

        logger.debug(
            f"注册数据源方法: {data_type.value} -> {vendor.value} (优先级: {priority})",
            tag="DataSourceRouter"
        )

    async def route(
        self,
        data_type: DataType,
        *args,
        **kwargs,
    ) -> Any:
        """
        路由数据请求到可用的数据源

        Args:
            data_type: 数据类型
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            数据结果

        Raises:
            RuntimeError: 所有数据源都不可用
        """
        if data_type not in self._method_registry:
            raise ValueError(f"不支持的数据类型: {data_type}")

        methods = self._method_registry[data_type]
        if not methods:
            raise RuntimeError(f"没有可用的数据源: {data_type}")

        last_error = None
        attempted_vendors = []

        # 尝试每个数据源（按优先级）
        for vendor_method in methods:
            vendor = vendor_method.vendor
            attempted_vendors.append(vendor)

            try:
                # 记录开始时间
                import time
                start_time = time.time()

                # 执行方法
                if asyncio.iscoroutinefunction(vendor_method.method):
                    result = await vendor_method.method(*args, **kwargs)
                else:
                    result = vendor_method.method(*args, **kwargs)

                # 记录成功统计
                elapsed = time.time() - start_time
                self._record_success(vendor, data_type, elapsed)

                # 如果不是首选数据源，记录回退
                if attempted_vendors.index(vendor) > 0:
                    primary_vendor = attempted_vendors[0]
                    self._record_fallback(data_type, primary_vendor, vendor)
                    logger.warning(
                        f"数据源回退: {data_type.value} 从 {primary_vendor.value} 回退到 {vendor.value}",
                        tag="DataSourceRouter"
                    )

                return result

            except RateLimitException as e:
                # 速率限制 - 尝试下一个
                logger.warning(
                    f"数据源速率限制: {vendor.value} - {e.message}",
                    tag="DataSourceRouter"
                )
                last_error = e
                self._record_failure(vendor, data_type, "rate_limit")

            except Exception as e:
                # 其他错误 - 尝试下一个
                logger.warning(
                    f"数据源失败: {vendor.value} - {str(e)}",
                    tag="DataSourceRouter"
                )
                last_error = e
                self._record_failure(vendor, data_type, "error")

        # 所有数据源都失败
        raise RuntimeError(
            f"所有数据源都失败: {data_type.value} (尝试了: {[v.value for v in attempted_vendors]})"
        ) from last_error

    def _record_success(self, vendor: DataSourceType, data_type: DataType, elapsed: float):
        """记录成功统计"""
        if vendor not in self._performance_stats:
            self._performance_stats[vendor] = {
                "success_count": 0,
                "failure_count": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
            }

        stats = self._performance_stats[vendor]
        stats["success_count"] += 1
        stats["total_time"] += elapsed
        stats["avg_time"] = stats["total_time"] / stats["success_count"]

    def _record_failure(self, vendor: DataSourceType, data_type: DataType, reason: str):
        """记录失败统计"""
        if vendor not in self._performance_stats:
            self._performance_stats[vendor] = {
                "success_count": 0,
                "failure_count": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
            }

        self._performance_stats[vendor]["failure_count"] += 1

    def _record_fallback(
        self,
        data_type: DataType,
        from_vendor: DataSourceType,
        to_vendor: DataSourceType,
    ):
        """记录回退历史"""
        self._fallback_history.append((data_type, from_vendor, to_vendor))

        # 限制历史长度
        if len(self._fallback_history) > 1000:
            self._fallback_history = self._fallback_history[-500:]

    def get_performance_stats(self) -> Dict[DataSourceType, Dict[str, Any]]:
        """获取性能统计"""
        return self._performance_stats.copy()

    def get_fallback_stats(self) -> Dict[str, Any]:
        """获取回退统计"""
        from collections import Counter

        fallback_counts = Counter(
            (data_type.value, to_vendor.value)
            for data_type, from_vendor, to_vendor in self._fallback_history
        )

        return {
            "total_fallbacks": len(self._fallback_history),
            "by_type_and_vendor": dict(fallback_counts),
        }


# ============================================================================
# 全局单例
# ============================================================================

_global_router: Optional[DataSourceRouter] = None


def get_data_source_router() -> DataSourceRouter:
    """获取全局数据源路由器"""
    global _global_router
    if _global_router is None:
        _global_router = DataSourceRouter()
    return _global_router


def register_vendor_method(
    data_type: DataType,
    vendor: DataSourceType,
    method: Callable,
    priority: int = 0,
):
    """
    便捷函数：注册数据源方法

    Args:
        data_type: 数据类型
        vendor: 数据源
        method: 获取方法
        priority: 优先级
    """
    router = get_data_source_router()
    router.register_method(data_type, vendor, method, priority)


# ============================================================================
# 装饰器：自动注册和路由
# ============================================================================

def vendor_routed(
    data_type: DataType,
    primary_vendor: DataSourceType = DataSourceType.BINANCE,
    priority: int = 0,
):
    """
    装饰器：将函数注册为数据源方法

    用法:
    @vendor_routed(DataType.KLINE, DataSourceType.BINANCE, priority=0)
    async def get_kline_data(symbol, interval, limit):
        ...
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # 直接通过路由器调用
            router = get_data_source_router()
            return await router.route(data_type, *args, **kwargs)

        # 注册原函数
        register_vendor_method(data_type, primary_vendor, func, priority)

        return wrapper


# ============================================================================
# 示例：Binance数据源包装
# ============================================================================

class BinanceDataSource:
    """Binance数据源包装器"""

    def __init__(self):
        from .binance_client import BinanceClient
        self.client = BinanceClient()

    async def get_kline(self, symbol: str, interval: str, limit: int = 100) -> Dict:
        """获取K线数据"""
        try:
            result = await self.client.get_klines(symbol, interval, limit)
            return {"success": True, "data": result}
        except Exception as e:
            raise DataSourceException(f"获取K线失败: {str(e)}", DataSourceType.BINANCE, e)

    async def get_ticker(self, symbol: str) -> Dict:
        """获取24小时行情"""
        try:
            result = await self.client.get_24h_ticker(symbol)
            return {"success": True, "data": result}
        except Exception as e:
            raise DataSourceException(f"获取行情失败: {str(e)}", DataSourceType.BINANCE, e)


class CoinGeckoDataSource:
    """CoinGecko备用数据源"""

    def __init__(self):
        self.api_key = None  # CoinGecko免费API无需key

    async def get_ticker(self, symbol: str) -> Dict:
        """获取当前价格（备用）"""
        import aiohttp

        try:
            # 转换交易对格式
            coin_id = symbol.replace("USDT", "").lower()

            async with aiohttp.ClientSession() as session:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": {
                                "symbol": symbol,
                                "price": data.get(coin_id, {}).get("usd"),
                                "source": "coingecko",
                            }
                        }
                    else:
                        raise DataSourceException(
                            f"HTTP {response.status}",
                            DataSourceType.COINGECKO
                        )
        except Exception as e:
            raise DataSourceException(f"CoinGecko请求失败: {str(e)}", DataSourceType.COINGECKO, e)


# ============================================================================
# 初始化默认数据源
# ============================================================================

def initialize_default_vendors():
    """初始化默认数据源"""
    get_data_source_router()  # 获取路由器实例

    # Binance数据源（主数据源）
    binance = BinanceDataSource()

    # CoinGecko数据源（备用）
    coingecko = CoinGeckoDataSource()

    # 注册K线数据
    register_vendor_method(
        DataType.KLINE,
        DataSourceType.BINANCE,
        binance.get_kline,
        priority=0,
    )

    # 注册行情数据
    register_vendor_method(
        DataType.TICKER,
        DataSourceType.BINANCE,
        binance.get_ticker,
        priority=0,
    )
    register_vendor_method(
        DataType.TICKER,
        DataSourceType.COINGECKO,
        coingecko.get_ticker,
        priority=1,  # 备用
    )

    logger.info("默认数据源已初始化", tag="DataSourceRouter")


# 启动时初始化
try:
    initialize_default_vendors()
except Exception as e:
    logger.warning(f"数据源初始化失败: {e}", tag="DataSourceRouter")
