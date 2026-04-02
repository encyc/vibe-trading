"""
技术指标计算模块

提供常用技术指标的计算功能。
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Indicators:
    """技术指标数据"""

    # 趋势指标
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None

    # 动量指标
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None

    # 波动率指标
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    atr: Optional[float] = None

    # 成交量指标
    volume_sma: Optional[float] = None


def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """计算简单移动平均线"""
    return data.rolling(window=period).mean()


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """计算指数移动平均线"""
    return data.ewm(span=period, adjust=False).mean()


def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """计算相对强弱指数 (RSI)"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    data: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple:
    """计算 MACD 指标"""
    ema_fast = calculate_ema(data, fast_period)
    ema_slow = calculate_ema(data, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    data: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple:
    """计算布林带"""
    middle = calculate_sma(data, period)
    std = data.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def calculate_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """计算平均真实波幅 (ATR)"""
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr


def calculate_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3
) -> tuple:
    """计算随机指标 (Stochastic)"""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()

    k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    d = k.rolling(window=d_period).mean()
    return k, d


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """计算能量潮 (OBV)"""
    obv = pd.Series(index=close.index, dtype=float)
    obv.iloc[0] = volume.iloc[0]

    for i in range(1, len(close)):
        if close.iloc[i] > close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]

    return obv


class TechnicalIndicators:
    """技术指标计算器"""

    def __init__(self):
        self.data: Optional[pd.DataFrame] = None

    def load_data(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
        timestamps: Optional[List[int]] = None,
    ) -> None:
        """加载 K线数据"""
        self.data = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        )
        if timestamps:
            self.data["timestamp"] = timestamps

    def calculate_all(self) -> pd.DataFrame:
        """计算所有技术指标"""
        if self.data is None or len(self.data) < 50:
            raise ValueError("Insufficient data for indicator calculation")

        df = self.data.copy()

        # 移动平均线
        df["sma_20"] = calculate_sma(df["close"], 20)
        df["sma_50"] = calculate_sma(df["close"], 50)
        df["ema_12"] = calculate_ema(df["close"], 12)
        df["ema_26"] = calculate_ema(df["close"], 26)

        # RSI
        df["rsi"] = calculate_rsi(df["close"])

        # MACD
        df["macd"], df["macd_signal"], df["macd_hist"] = calculate_macd(df["close"])

        # 布林带
        df["bb_upper"], df["bb_middle"], df["bb_lower"] = calculate_bollinger_bands(df["close"])

        # ATR
        df["atr"] = calculate_atr(df["high"], df["low"], df["close"])

        # 成交量 MA
        df["volume_sma"] = calculate_sma(df["volume"], 20)

        # 随机指标
        df["stoch_k"], df["stoch_d"] = calculate_stochastic(df["high"], df["low"], df["close"])

        # OBV
        df["obv"] = calculate_obv(df["close"], df["volume"])

        return df

    def get_latest_indicators(self) -> Indicators:
        """获取最新的技术指标"""
        df = self.calculate_all()
        latest = df.iloc[-1]

        return Indicators(
            sma_20=latest.get("sma_20"),
            sma_50=latest.get("sma_50"),
            ema_12=latest.get("ema_12"),
            ema_26=latest.get("ema_26"),
            rsi=latest.get("rsi"),
            macd=latest.get("macd"),
            macd_signal=latest.get("macd_signal"),
            macd_hist=latest.get("macd_hist"),
            bollinger_upper=latest.get("bb_upper"),
            bollinger_middle=latest.get("bb_middle"),
            bollinger_lower=latest.get("bb_lower"),
            atr=latest.get("atr"),
            volume_sma=latest.get("volume_sma"),
        )

    def get_trend_analysis(self) -> dict:
        """获取趋势分析"""
        indicators = self.get_latest_indicators()

        analysis = {
            "trend": "neutral",
            "strength": "weak",
            "signals": [],
        }

        # 价格与均线关系
        current_price = self.data["close"].iloc[-1]
        if indicators.sma_20 and indicators.sma_50:
            if current_price > indicators.sma_20 > indicators.sma_50:
                analysis["trend"] = "strong_up"
                analysis["signals"].append("Price above both SMAs, golden cross pattern")
            elif current_price > indicators.sma_20:
                analysis["trend"] = "up"
                analysis["signals"].append("Price above SMA20")
            elif current_price < indicators.sma_20 < indicators.sma_50:
                analysis["trend"] = "strong_down"
                analysis["signals"].append("Price below both SMAs, death cross pattern")
            elif current_price < indicators.sma_20:
                analysis["trend"] = "down"
                analysis["signals"].append("Price below SMA20")

        # RSI 分析
        if indicators.rsi:
            if indicators.rsi > 70:
                analysis["signals"].append(f"RSI overbought ({indicators.rsi:.2f})")
            elif indicators.rsi < 30:
                analysis["signals"].append(f"RSI oversold ({indicators.rsi:.2f})")
            else:
                analysis["signals"].append(f"RSI neutral ({indicators.rsi:.2f})")

        # MACD 分析
        if indicators.macd and indicators.macd_signal:
            if indicators.macd > indicators.macd_signal:
                analysis["signals"].append("MACD bullish (above signal)")
            else:
                analysis["signals"].append("MACD bearish (below signal)")

        # 布林带分析
        if indicators.bollinger_upper and indicators.bollinger_lower:
            bb_width = indicators.bollinger_upper - indicators.bollinger_lower
            bb_position = (current_price - indicators.bollinger_lower) / bb_width

            if bb_position > 0.8:
                analysis["signals"].append(f"Price near upper Bollinger Band ({bb_position:.2%})")
            elif bb_position < 0.2:
                analysis["signals"].append(f"Price near lower Bollinger Band ({bb_position:.2%})")
            else:
                analysis["signals"].append(f"Price within Bollinger Bands ({bb_position:.2%})")

        return analysis
