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


async def detect_candlestick_patterns(
    symbol: str,
    interval: str = "30m",
    lookback: int = 20,
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    检测K线形态

    识别常见的反转和持续形态，如头肩顶/底、双顶/底、吞没形态等。

    Args:
        symbol: 交易对符号
        interval: K线间隔
        lookback: 回溯K线数量
        storage: K线存储

    Returns:
        检测到的K线形态
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=lookback)
    klines = await storage.query_klines(query)

    if len(klines) < 10:
        return {"error": f"Insufficient data: {len(klines)} bars, need at least 10"}

    # 提取数据
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]

    # 计算K线形态
    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    patterns = ti.detect_candlestick_patterns(lookback)

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": klines[-1].close_time,
        "current_price": closes[-1],
        **patterns,
    }


async def detect_divergence(
    symbol: str,
    interval: str = "30m",
    lookback: int = 20,
    indicator: str = "rsi",
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    检测指标背离

    检测RSI或MACD与价格的背离信号，这是重要的反转预警信号。

    Args:
        symbol: 交易对符号
        interval: K线间隔
        lookback: 回溯K线数量
        indicator: 检测背离的指标 (rsi, macd)
        storage: K线存储

    Returns:
        背离检测结果
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=lookback + 20)
    klines = await storage.query_klines(query)

    if len(klines) < lookback + 10:
        return {"error": f"Insufficient data: {len(klines)} bars"}

    # 提取数据
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]

    # 计算背离
    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    divergence = ti.detect_divergence(lookback, indicator)

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": klines[-1].close_time,
        "current_price": closes[-1],
        **divergence,
    }


async def analyze_volume_patterns(
    symbol: str,
    interval: str = "30m",
    lookback: int = 20,
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    分析成交量模式

    检测成交量异常（放量/缩量）和成交量确认信号。

    Args:
        symbol: 交易对符号
        interval: K线间隔
        lookback: 回溯K线数量
        storage: K线存储

    Returns:
        成交量分析结果
    """
    if not storage:
        return {"error": "Storage not configured"}

    query = KlineQuery(symbol=symbol, interval=interval, limit=lookback + 20)
    klines = await storage.query_klines(query)

    if len(klines) < lookback + 10:
        return {"error": f"Insufficient data: {len(klines)} bars"}

    # 提取数据
    opens = [k.open for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]

    # 分析成交量
    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    volume_analysis = ti.analyze_volume(lookback)

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": klines[-1].close_time,
        "current_price": closes[-1],
        **volume_analysis,
    }


async def get_comprehensive_technical_analysis(
    symbol: str,
    interval: str = "30m",
    storage: Optional[KlineStorage] = None,
) -> dict:
    """
    获取综合技术分析

    整合所有技术分析工具，提供完整的技术分析报告。

    Args:
        symbol: 交易对符号
        interval: K线间隔
        storage: K线存储

    Returns:
        综合技术分析报告
    """
    if not storage:
        return {"error": "Storage not configured"}

    # 并行获取所有分析
    import asyncio

    results = await asyncio.gather(
        get_technical_indicators(symbol, interval, 100, storage),
        analyze_trend(symbol, interval, storage),
        detect_candlestick_patterns(symbol, interval, 30, storage),
        detect_divergence(symbol, interval, 30, "rsi", storage),
        detect_divergence(symbol, interval, 30, "macd", storage),
        analyze_volume_patterns(symbol, interval, 30, storage),
        detect_support_resistance(symbol, interval, 100, storage),
        calculate_pivots(symbol, interval, storage),
        return_exceptions=True,
    )

    # 整合结果
    indicators_data = results[0] if not isinstance(results[0], Exception) else {}
    trend_data = results[1] if not isinstance(results[1], Exception) else {}
    patterns_data = results[2] if not isinstance(results[2], Exception) else {}
    rsi_divergence = results[3] if not isinstance(results[3], Exception) else {}
    macd_divergence = results[4] if not isinstance(results[4], Exception) else {}
    volume_data = results[5] if not isinstance(results[5], Exception) else {}
    sr_data = results[6] if not isinstance(results[6], Exception) else {}
    pivots_data = results[7] if not isinstance(results[7], Exception) else {}

    # 计算综合信号
    signals = []
    confidence_score = 0

    # 从趋势分析获取信号
    if "analysis" in trend_data:
        trend_analysis = trend_data["analysis"]
        trend = trend_analysis.get("trend", "neutral")

        if trend == "strong_up":
            signals.append("强烈看涨趋势")
            confidence_score += 2
        elif trend == "up":
            signals.append("看涨趋势")
            confidence_score += 1
        elif trend == "strong_down":
            signals.append("强烈看跌趋势")
            confidence_score -= 2
        elif trend == "down":
            signals.append("看跌趋势")
            confidence_score -= 1

    # 从K线形态获取信号
    if "patterns" in patterns_data:
        for pattern in patterns_data["patterns"].get("reversal", []):
            if pattern["signal"] == "bullish":
                signals.append(f"K线形态: {pattern['type']} (看涨)")
                confidence_score += 1
            elif pattern["signal"] == "bearish":
                signals.append(f"K线形态: {pattern['type']} (看跌)")
                confidence_score -= 1

    # 从背离获取信号
    if "divergences" in rsi_divergence:
        if rsi_divergence["divergences"]["bullish"]:
            signals.append("RSI看涨背离")
            confidence_score += len(rsi_divergence["divergences"]["bullish"])
        if rsi_divergence["divergences"]["bearish"]:
            signals.append("RSI看跌背离")
            confidence_score -= len(rsi_divergence["divergences"]["bearish"])

    if "divergences" in macd_divergence:
        if macd_divergence["divergences"]["bullish"]:
            signals.append("MACD看涨背离")
            confidence_score += len(macd_divergence["divergences"]["bullish"])
        if macd_divergence["divergences"]["bearish"]:
            signals.append("MACD看跌背离")
            confidence_score -= len(macd_divergence["divergences"]["bearish"])

    # 从成交量获取信号
    if "patterns" in volume_data:
        for pattern in volume_data["patterns"]:
            if "放量上涨" in pattern or "资金流入" in pattern:
                confidence_score += 1
                signals.append(f"成交量: {pattern}")
            elif "放量下跌" in pattern or "资金流出" in pattern:
                confidence_score -= 1
                signals.append(f"成交量: {pattern}")

    # 确定综合信号
    if confidence_score >= 3:
        overall_signal = "strong_buy"
        overall_text = "强烈买入"
    elif confidence_score >= 1:
        overall_signal = "buy"
        overall_text = "买入"
    elif confidence_score <= -3:
        overall_signal = "strong_sell"
        overall_text = "强烈卖出"
    elif confidence_score <= -1:
        overall_signal = "sell"
        overall_text = "卖出"
    else:
        overall_signal = "hold"
        overall_text = "持有观望"

    return {
        "symbol": symbol,
        "interval": interval,
        "timestamp": indicators_data.get("timestamp"),
        "current_price": indicators_data.get("current_price"),
        "overall_signal": overall_signal,
        "overall_text": overall_text,
        "confidence_score": confidence_score,
        "signals": signals,
        "indicators": indicators_data.get("indicators", {}),
        "trend": trend_data.get("analysis", {}),
        "patterns": patterns_data.get("patterns", {}),
        "divergence": {
            "rsi": rsi_divergence.get("divergences", {}),
            "macd": macd_divergence.get("divergences", {}),
        },
        "volume": volume_data,
        "support_resistance": sr_data,
        "pivots": pivots_data,
    }
