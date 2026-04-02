"""
技术分析工具

为 Agent 提供技术分析相关的工具函数。
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field

from vibe_trading.data_sources.technical_indicators import (
    TechnicalIndicators,
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
)
from vibe_trading.data_sources.kline_storage import KlineStorage, KlineQuery

logger = logging.getLogger(__name__)


# =============================================================================
# 工具参数模型
# =============================================================================

class GetTechnicalIndicatorsParams(BaseModel):
    """获取技术指标参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")
    period: int = Field(default=50, description="计算周期")


class AnalyzeTrendParams(BaseModel):
    """分析趋势参数"""
    symbol: str = Field(description="交易对符号")
    interval: str = Field(default="30m", description="K线间隔")


# =============================================================================
# 工具函数
# =============================================================================

async def get_technical_indicators(
    symbol: str,
    interval: str = "30m",
    period: int = 50,
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    获取技术指标

    计算并返回主要技术指标，包括 RSI, MACD, 布林带等。

    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: 计算周期

    Returns:
        技术指标数据
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=period)
    klines = await storage.query_klines(query)

    if len(klines) < 50:
        return {"error": f"Insufficient data: {len(klines)} bars, need at least 50"}

    # 提取数据
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]

    # 计算技术指标
    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    indicators = ti.get_latest_indicators()

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": klines[-1].close_time,
        "current_price": closes[-1],
        "indicators": {
            # 趋势指标
            "sma_20": indicators.sma_20,
            "sma_50": indicators.sma_50,
            "ema_12": indicators.ema_12,
            "ema_26": indicators.ema_26,
            # 动量指标
            "rsi": indicators.rsi,
            "macd": indicators.macd,
            "macd_signal": indicators.macd_signal,
            "macd_histogram": indicators.macd_hist,
            # 波动率指标
            "bollinger_upper": indicators.bollinger_upper,
            "bollinger_middle": indicators.bollinger_middle,
            "bollinger_lower": indicators.bollinger_lower,
            "atr": indicators.atr,
            # 成交量指标
            "volume_sma": indicators.volume_sma,
        },
    }


async def analyze_trend(
    symbol: str,
    interval: str = "30m",
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    分析趋势

    基于技术指标分析当前趋势方向和强度。

    Args:
        symbol: 交易对符号
        interval: K线间隔

    Returns:
        趋势分析结果
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=100)
    klines = await storage.query_klines(query)

    if len(klines) < 50:
        return {"error": f"Insufficient data: {len(klines)} bars"}

    # 提取数据
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]

    # 计算技术指标和趋势分析
    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    analysis = ti.get_trend_analysis()

    current_price = closes[-1]
    prev_price = closes[-2]

    # 计算价格变化
    price_change_pct = ((current_price - prev_price) / prev_price) * 100

    # 添加价格变化信息
    analysis["current_price"] = current_price
    analysis["price_change_pct"] = price_change_pct

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": klines[-1].close_time,
        "analysis": analysis,
    }


async def detect_support_resistance(
    symbol: str,
    interval: str = "30m",
    lookback: int = 100,
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    检测支撑位和阻力位

    Args:
        symbol: 交易对符号
        interval: K线间隔
        lookback: 回溯K线数量

    Returns:
        支撑位和阻力位
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=lookback)
    klines = await storage.query_klines(query)

    if len(klines) < 20:
        return {"error": "Insufficient data"}

    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    current_price = closes[-1]

    # 找出局部高点（阻力位）
    resistance_levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(highs[i])

    # 找出局部低点（支撑位）
    support_levels = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(lows[i])

    # 选择最近的支撑位和阻力位
    relevant_resistance = [r for r in sorted(set(resistance_levels)) if r > current_price][:3]
    relevant_support = [s for s in sorted(set(support_levels), reverse=True) if s < current_price][:3]

    return {
        "symbol": symbol,
        "interval": interval,
        "current_price": current_price,
        "support_levels": relevant_support,
        "resistance_levels": relevant_resistance,
    }


async def calculate_pivots(
    symbol: str,
    interval: str = "30m",
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    计算枢轴点（Pivot Points）

    Args:
        symbol: 交易对符号
        interval: K线间隔

    Returns:
        枢轴点数据
    """
    if not storage:
        return {"error": "Storage not configured"}

    # 获取前一根K线数据
    query = KlineQuery(symbol=symbol, interval=interval, limit=2)
    klines = await storage.query_klines(query)

    if len(klines) < 2:
        return {"error": "Insufficient data"}

    prev = klines[-2]
    current_price = klines[-1].close

    # 计算枢轴点
    pivot = (prev.high + prev.low + prev.close) / 3

    # 计算支撑位和阻力位
    r1 = 2 * pivot - prev.low
    r2 = pivot + (prev.high - prev.low)
    r3 = prev.high + 2 * (pivot - prev.low)

    s1 = 2 * pivot - prev.high
    s2 = pivot - (prev.high - prev.low)
    s3 = prev.low - 2 * (prev.high - pivot)

    return {
        "symbol": symbol,
        "interval": interval,
        "current_price": current_price,
        "pivot": pivot,
        "resistance": {"r1": r1, "r2": r2, "r3": r3},
        "support": {"s1": s1, "s2": s2, "s3": s3},
    }
