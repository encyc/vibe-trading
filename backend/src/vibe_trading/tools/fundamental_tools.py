"""
链上数据和基本面分析工具

为 Agent 提供获取链上数据的基本面分析工具。
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# 工具参数模型
# =============================================================================

class GetOnChainMetricsParams(BaseModel):
    """获取链上指标参数"""
    symbol: str = Field(description="交易对符号")


class GetWhaleAlertParams(BaseModel):
    """获取大额转账参数"""
    symbol: str = Field(description="交易对符号")
    min_amount: float = Field(default=100.0, description="最小金额（USD）")


# =============================================================================
# 工具函数
# =============================================================================

async def get_fear_and_greed_index() -> dict:
    """
    获取加密货币恐惧与贪婪指数

    Returns:
        恐惧与贪婪指数数据
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.alternative.me/fng/")
            data = response.json()

            return {
                "value": int(data["data"][0]["value"]),
                "classification": data["data"][0]["value_classification"],
                "timestamp": data["data"][0]["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching Fear & Greed Index: {e}")
        return {"error": str(e)}


async def get_funding_rates(symbol: Optional[str] = None) -> dict:
    """
    获取多个交易所的资金费率

    Args:
        symbol: 可选的交易对符号

    Returns:
        资金费率数据
    """
    try:
        async with httpx.AsyncClient() as client:
            # 使用 Binance API
            if symbol:
                url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
            else:
                url = "https://fapi.binance.com/fapi/v1/premiumIndex"

            response = await client.get(url)
            data = response.json()

            if isinstance(data, list):
                return [
                    {
                        "symbol": item["symbol"],
                        "funding_rate": float(item.get("lastFundingRate", 0)),
                        "mark_price": float(item.get("markPrice", 0)),
                    }
                    for item in data
                ]
            else:
                return {
                    "symbol": data["symbol"],
                    "funding_rate": float(data.get("lastFundingRate", 0)),
                    "mark_price": float(data.get("markPrice", 0)),
                }
    except Exception as e:
        logger.error(f"Error fetching funding rates: {e}")
        return {"error": str(e)}


async def get_long_short_ratio(symbol: str, period: str = "1h") -> dict:
    """
    获取多空比例

    Args:
        symbol: 交易对符号
        period: 时间周期 (5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d)

    Returns:
        多空比例数据
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            params = {"symbol": symbol, "period": period}

            response = await client.get(url, params=params)
            data = response.json()

            if not data:
                return {"error": "No data available"}

            latest = data[-1]
            return {
                "symbol": symbol,
                "period": period,
                "long_short_ratio": float(latest["longShortRatio"]),
                "long_account": float(latest["longAccount"]),
                "short_account": float(latest["shortAccount"]),
                "timestamp": latest["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching long/short ratio: {e}")
        return {"error": str(e)}


async def get_taker_buy_sell_ratio(symbol: str, period: str = "30m") -> dict:
    """
    获取主动买卖比例

    Args:
        symbol: 交易对符号
        period: 时间周期

    Returns:
        主动买卖比例数据
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://fapi.binance.com/futures/data/takerlongshortRatio"
            params = {"symbol": symbol, "period": period}

            response = await client.get(url, params=params)
            data = response.json()

            if not data:
                return {"error": "No data available"}

            latest = data[-1]
            return {
                "symbol": symbol,
                "period": period,
                "buy_sell_ratio": float(latest["buySellRatio"]),
                "buy_volume": float(latest["buyVol"]),
                "sell_volume": float(latest["sellVol"]),
                "timestamp": latest["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching taker buy/sell ratio: {e}")
        return {"error": str(e)}


async def get_open_interest(symbol: str, period: str = "30m") -> dict:
    """
    获取持仓量变化

    Args:
        symbol: 交易对符号
        period: 时间周期

    Returns:
        持仓量数据
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://fapi.binance.com/futures/data/openInterestHist"
            params = {"symbol": symbol, "period": period, "limit": 30}

            response = await client.get(url, params=params)
            data = response.json()

            if not data:
                return {"error": "No data available"}

            # 计算变化
            latest = data[-1]
            prev = data[0]

            oi_change = float(latest["sumOpenInterest"]) - float(prev["sumOpenInterest"])
            oi_change_pct = (oi_change / float(prev["sumOpenInterest"])) * 100

            return {
                "symbol": symbol,
                "period": period,
                "open_interest": float(latest["sumOpenInterest"]),
                "open_interest_value": float(latest["sumOpenInterestValue"]),
                "change": oi_change,
                "change_percent": oi_change_pct,
                "timestamp": latest["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching open interest: {e}")
        return {"error": str(e)}


async def get_top_trader_long_short_ratio(symbol: str, period: str = "1h") -> dict:
    """
    获取大户多空比例

    Args:
        symbol: 交易对符号
        period: 时间周期

    Returns:
        大户多空比例数据
    """
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio"
            params = {"symbol": symbol, "period": period}

            response = await client.get(url, params=params)
            data = response.json()

            if not data:
                return {"error": "No data available"}

            latest = data[-1]
            return {
                "symbol": symbol,
                "period": period,
                "long_short_ratio": float(latest["longShortRatio"]),
                "long_position": float(latest["longPosition"]),
                "short_position": float(latest["shortPosition"]),
                "timestamp": latest["timestamp"],
            }
    except Exception as e:
        logger.error(f"Error fetching top trader ratio: {e}")
        return {"error": str(e)}


async def get_liquidation_orders(symbol: Optional[str] = None) -> dict:
    """
    获取强制平仓订单

    Args:
        symbol: 可选的交易对符号

    Returns:
        强平订单数据
    """
    try:
        async with httpx.AsyncClient() as client:
            url = "https://fapi.binance.com/fapi/v1/allForceOrders"
            params = {}
            if symbol:
                params["symbol"] = symbol

            response = await client.get(url, params=params)
            data = response.json()

            return {
                "count": len(data),
                "orders": [
                    {
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "type": order["type"],
                        "quantity": float(order["origQty"]),
                        "price": float(order["price"]),
                        "average_price": float(order.get("avgPrice", 0)),
                        "time_in_force": order["timeInForce"],
                    }
                    for order in data[-20:]  # 最近20笔
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching liquidation orders: {e}")
        return {"error": str(e)}
