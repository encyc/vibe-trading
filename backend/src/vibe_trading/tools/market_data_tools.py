"""
市场数据工具

为 Agent 提供获取市场数据的工具函数。
"""
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from vibe_trading.data_sources.binance_client import BinanceClient, KlineInterval
from vibe_trading.data_sources.kline_storage import KlineStorage, KlineQuery
from vibe_trading.data_sources.technical_indicators import TechnicalIndicators

# 改进工具导入
from vibe_trading.data_sources.cache import cached, get_global_cache
from vibe_trading.data_sources.rate_limiter import get_multi_endpoint_limiter

logger = logging.getLogger(__name__)

# 获取全局实例
_cache = get_global_cache()
_rate_limiter = get_multi_endpoint_limiter()


# =============================================================================
# 工具参数模型
# =============================================================================

class GetKlineDataParams(BaseModel):
    """获取 K线数据参数"""
    symbol: str = Field(description="交易对符号，如 BTCUSDT")
    interval: str = Field(default="30m", description="K线间隔，如 1m, 5m, 15m, 30m, 1h, 4h, 1d")
    limit: int = Field(default=100, description="获取的数据条数")


class GetCurrentPriceParams(BaseModel):
    """获取当前价格参数"""
    symbol: str = Field(description="交易对符号，如 BTCUSDT")


class Get24hrTickerParams(BaseModel):
    """获取24小时ticker参数"""
    symbol: str = Field(description="交易对符号，如 BTCUSDT")


# =============================================================================
# 工具函数
# =============================================================================

async def get_kline_data(
    symbol: str,
    interval: str = "30m",
    limit: int = 100,
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    获取 K线数据

    Args:
        symbol: 交易对符号
        interval: K线间隔
        limit: 获取的数据条数

    Returns:
        包含 OHLCV 数据的字典
    """
    if storage:
        # 从数据库获取
        query = KlineQuery(symbol=symbol, interval=interval, limit=limit)
        klines = await storage.query_klines(query)
    else:
        # 从 API 获取
        client = BinanceClient()
        try:
            data = await client.rest.get_klines(
                symbol=symbol,
                interval=KlineInterval(interval),
                limit=limit,
            )
            klines = [Kline.from_rest(k) for k in data]
        finally:
            await client.close()

    if not klines:
        return {"error": "No kline data available"}

    # 格式化返回
    result = {
        "symbol": symbol,
        "interval": interval,
        "data": [
            {
                "timestamp": k.open_time,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "volume": k.volume,
            }
            for k in klines
        ],
        "latest": {
            "timestamp": klines[-1].open_time,
            "open": klines[-1].open,
            "high": klines[-1].high,
            "low": klines[-1].low,
            "close": klines[-1].close,
            "volume": klines[-1].volume,
        },
        "count": len(klines),
    }

    return result


@cached(ttl=5, key_prefix="price", cache_instance=_cache)
async def get_current_price(symbol: str, storage: Optional[KlineStorage] = None) -> dict:
    """
    获取当前价格

    Args:
        symbol: 交易对符号

    Returns:
        当前价格信息
    """
    if storage:
        kline = await storage.get_latest_kline(symbol, "1m")
        if kline:
            return {
                "symbol": symbol,
                "price": kline.close,
                "timestamp": kline.close_time,
                "volume": kline.volume,
            }

    # ========== 改进工具: API限流 ==========
    await _rate_limiter.acquire("binance_rest", tokens=1)

    # 从 API 获取
    client = BinanceClient()
    try:
        ticker = await client.rest._request(
            "GET",
            "/fapi/v1/ticker/price",
            params={"symbol": symbol},
        )
        return {
            "symbol": symbol,
            "price": float(ticker["price"]),
            "timestamp": ticker["time"],
        }
    finally:
        await client.close()


@cached(ttl=30, key_prefix="ticker_24h", cache_instance=_cache)
async def get_24hr_ticker(symbol: str) -> dict:
    """
    获取24小时价格变动数据

    Args:
        symbol: 交易对符号

    Returns:
        24小时 ticker 数据
    """
    # ========== 改进工具: API限流 ==========
    await _rate_limiter.acquire("binance_rest", tokens=1)

    client = BinanceClient()
    try:
        ticker = await client.rest._request(
            "GET",
            "/fapi/v1/ticker/24hr",
            params={"symbol": symbol},
        )
        return {
            "symbol": ticker["symbol"],
            "price_change": float(ticker["priceChange"]),
            "price_change_percent": float(ticker["priceChangePercent"]),
            "high": float(ticker["highPrice"]),
            "low": float(ticker["lowPrice"]),
            "volume": float(ticker["volume"]),
            "quote_volume": float(ticker["quoteVolume"]),
            "open": float(ticker["openPrice"]),
            "close": float(ticker["lastPrice"]),
        }
    finally:
        await client.close()


@cached(ttl=10, key_prefix="orderbook", cache_instance=_cache)
async def get_order_book(symbol: str, limit: int = 20) -> dict:
    """
    获取订单簿数据

    Args:
        symbol: 交易对符号
        limit: 深度级别

    Returns:
        订单簿数据
    """
    # ========== 改进工具: API限流 ==========
    await _rate_limiter.acquire("binance_rest", tokens=1)

    client = BinanceClient()
    try:
        data = await client.rest._request(
            "GET",
            "/fapi/v1/depth",
            params={"symbol": symbol, "limit": limit},
        )
        return {
            "symbol": symbol,
            "bids": [[float(p), float(q)] for p, q in data["bids"][:10]],
            "asks": [[float(p), float(q)] for p, q in data["asks"][:10]],
            "timestamp": data.get("lastUpdateId", 0),
        }
    finally:
        await client.close()


@cached(ttl=60, key_prefix="funding_rate", cache_instance=_cache)
async def get_funding_rate(symbol: str) -> dict:
    """
    获取资金费率

    Args:
        symbol: 交易对符号

    Returns:
        资金费率数据
    """
    # ========== 改进工具: API限流 ==========
    await _rate_limiter.acquire("binance_rest", tokens=1)

    client = BinanceClient()
    try:
        data = await client.rest._request(
            "GET",
            "/fapi/v1/premiumIndex",
            params={"symbol": symbol},
        )
        return {
            "symbol": symbol,
            "funding_rate": float(data.get("lastFundingRate", "0")),
            "funding_time": int(data.get("nextFundingTime", 0)),
            "mark_price": float(data.get("markPrice", "0")),
            "index_price": float(data.get("indexPrice", "0")),
        }
    finally:
        await client.close()


@cached(ttl=60, key_prefix="open_interest", cache_instance=_cache)
async def get_open_interest(symbol: str) -> dict:
    """
    获取持仓量

    Args:
        symbol: 交易对符号

    Returns:
        持仓量数据
    """
    # ========== 改进工具: API限流 ==========
    await _rate_limiter.acquire("binance_rest", tokens=1)

    client = BinanceClient()
    try:
        data = await client.rest._request(
            "GET",
            "/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        return {
            "symbol": symbol,
            "open_interest": float(data["openInterest"]),
            "timestamp": data["time"],
        }
    finally:
        await client.close()
