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

    # 默认指标配置及其lookback需求
    DEFAULT_INDICATORS = {
        "rsi": {"period": 14},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "bollinger": {"period": 20, "std_dev": 2},
        "sma_20": {"period": 20},
        "sma_50": {"period": 50},
        "ema_12": {"period": 12},
        "ema_26": {"period": 26},
        "atr": {"period": 14},
        "stochastic": {"k_period": 14, "d_period": 3},
    }

    def __init__(self):
        self.data: Optional[pd.DataFrame] = None

    @classmethod
    def get_required_lookback(
        cls,
        indicators: Optional[List[str]] = None,
        safety_margin: float = 0.2
    ) -> int:
        """
        获取计算指定指标所需的最小lookback周期数

        这个方法用于确定回测时需要额外加载多少历史K线数据，
        以确保所有指定指标在回测第一天就能正确计算。

        Args:
            indicators: 需要计算的指标列表（如["rsi", "macd", "bollinger"]）
                       如果为None，则计算所有默认指标的lookback
            safety_margin: 安全边际比例（默认20%），用于确保数据充足

        Returns:
            需要的历史K线周期数

        Examples:
            >>> # 计算MACD和RSI的lookback
            >>> lookback = TechnicalIndicators.get_required_lookback(["macd", "rsi"])
            >>> print(lookback)  # 42 (max(35, 14) * 1.2)

            >>> # 计算所有默认指标的lookback
            >>> lookback = TechnicalIndicators.get_required_lookback()
            >>> print(lookback)  # 60 (max(50, 35, 14, ...) * 1.2)
        """
        if indicators is None:
            # 使用所有默认指标
            indicators = list(cls.DEFAULT_INDICATORS.keys())

        max_lookback = 0
        for indicator in indicators:
            if indicator in cls.DEFAULT_INDICATORS:
                params = cls.DEFAULT_INDICATORS[indicator]

                # 计算单个指标的lookback
                if indicator == "macd":
                    # MACD: max(fast, slow) + signal
                    fast = params.get("fast", 12)
                    slow = params.get("slow", 26)
                    signal = params.get("signal", 9)
                    lookback = max(fast, slow) + signal
                elif indicator == "stochastic":
                    # Stochastic: max(k_period, d_period)
                    k_period = params.get("k_period", 14)
                    d_period = params.get("d_period", 3)
                    lookback = max(k_period, d_period)
                elif "period" in params:
                    # 其他带period参数的指标
                    lookback = params["period"]
                else:
                    lookback = 20  # 默认值

                max_lookback = max(max_lookback, lookback)

        # 添加安全边际
        return int(max_lookback * (1 + safety_margin))

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

    def detect_candlestick_patterns(self, lookback: int = 20) -> dict:
        """检测K线形态

        检测常见的K线反转和持续形态。

        Returns:
            包含检测到的形态信息的字典
        """
        if self.data is None or len(self.data) < lookback:
            return {"error": "Insufficient data for pattern detection"}

        df = self.data.iloc[-lookback:].copy()
        patterns = {
            "reversal": [],  # 反转形态
            "continuation": [],  # 持续形态
            "single": [],  # 单根K线形态
        }

        # === 单根K线形态 ===
        for i in range(1, len(df)):
            open_price = df["open"].iloc[i]
            high = df["high"].iloc[i]
            low = df["low"].iloc[i]
            close = df["close"].iloc[i]
            body = abs(close - open_price)
            total_range = high - low

            if total_range == 0:
                continue

            upper_wick = (high - max(open_price, close)) / total_range
            lower_wick = (min(open_price, close) - low) / total_range
            body_ratio = body / total_range

            # 十字星/Doji
            if body_ratio < 0.1:
                patterns["single"].append({
                    "type": "Doji",
                    "index": i,
                    "signal": "potential_reversal",
                    "description": "Market indecision, watch for confirmation"
                })

            # 锤子线/Hammer (看涨反转)
            if (lower_wick > 0.6 and body_ratio < 0.3 and
                upper_wick < 0.1 and close > open_price):
                patterns["single"].append({
                    "type": "Hammer",
                    "index": i,
                    "signal": "bullish_reversal",
                    "description": "Potential bullish reversal at support"
                })

            # 上吊线/Hanging Man (看跌反转)
            if (lower_wick > 0.6 and body_ratio < 0.3 and
                upper_wick < 0.1 and close < open_price):
                patterns["single"].append({
                    "type": "Hanging Man",
                    "index": i,
                    "signal": "bearish_reversal",
                    "description": "Potential bearish reversal at resistance"
                })

            # 射击之星/ Shooting Star (看跌反转)
            if (upper_wick > 0.6 and body_ratio < 0.3 and
                lower_wick < 0.1):
                patterns["single"].append({
                    "type": "Shooting Star",
                    "index": i,
                    "signal": "bearish_reversal",
                    "description": "Potential bearish reversal after uptrend"
                })

        # === 双K线形态 ===
        for i in range(1, len(df)):
            # 吞没形态
            if i > 0:
                prev_open, prev_close = df["open"].iloc[i-1], df["close"].iloc[i-1]
                curr_open, curr_close = df["open"].iloc[i], df["close"].iloc[i]

                prev_body = abs(prev_close - prev_open)
                curr_body = abs(curr_close - curr_open)

                # 看涨吞没
                if (prev_close < prev_open and  # 前一根是阴线
                    curr_close > curr_open and  # 当前是阳线
                    curr_open < prev_close and   # 当前开盘低于前收盘
                    curr_close > prev_open):    # 当前收盘高于前开盘
                    patterns["reversal"].append({
                        "type": "Bullish Engulfing",
                        "index": i,
                        "signal": "bullish",
                        "strength": "strong" if curr_body > 1.5 * prev_body else "moderate",
                        "description": "Strong bullish reversal signal"
                    })

                # 看跌吞没
                if (prev_close > prev_open and  # 前一根是阳线
                    curr_close < curr_open and  # 当前是阴线
                    curr_open > prev_close and   # 当前开盘高于前收盘
                    curr_close < prev_open):    # 当前收盘低于前开盘
                    patterns["reversal"].append({
                        "type": "Bearish Engulfing",
                        "index": i,
                        "signal": "bearish",
                        "strength": "strong" if curr_body > 1.5 * prev_body else "moderate",
                        "description": "Strong bearish reversal signal"
                    })

        # === 三K线形态 ===
        for i in range(2, len(df)):
            # 早晨之星 (看涨反转)
            if (df["close"].iloc[i-2] < df["open"].iloc[i-2] and  # 第一根阴线
                abs(df["close"].iloc[i-1] - df["open"].iloc[i-1]) < 0.3 * (df["high"].iloc[i-1] - df["low"].iloc[i-1]) and  # 中间小实体
                df["close"].iloc[i] > df["open"].iloc[i] and  # 第三根阳线
                df["close"].iloc[i] > (df["open"].iloc[i-2] + df["close"].iloc[i-2]) / 2):  # 收复第一根跌幅的一半
                patterns["reversal"].append({
                    "type": "Morning Star",
                    "index": i,
                    "signal": "bullish",
                    "strength": "strong",
                    "description": "Bullish reversal pattern, trend likely to reverse upward"
                })

            # 黄昏之星 (看跌反转)
            if (df["close"].iloc[i-2] > df["open"].iloc[i-2] and  # 第一根阳线
                abs(df["close"].iloc[i-1] - df["open"].iloc[i-1]) < 0.3 * (df["high"].iloc[i-1] - df["low"].iloc[i-1]) and  # 中间小实体
                df["close"].iloc[i] < df["open"].iloc[i] and  # 第三根阴线
                df["close"].iloc[i] < (df["open"].iloc[i-2] + df["close"].iloc[i-2]) / 2):  # 跌破第一根涨幅的一半
                patterns["reversal"].append({
                    "type": "Evening Star",
                    "index": i,
                    "signal": "bearish",
                    "strength": "strong",
                    "description": "Bearish reversal pattern, trend likely to reverse downward"
                })

            # 上升三法 (看涨持续)
            if (df["close"].iloc[i-3] > df["open"].iloc[i-3] and  # 第一根大阳线
                all(df["close"].iloc[i-2+j] < df["open"].iloc[i-2+j] for j in range(2)) and  # 中间两根小阴线
                df["close"].iloc[i] > df["open"].iloc[i] and  # 最后大阳线
                df["close"].iloc[i] > df["close"].iloc[i-3]):  # 创新高
                patterns["continuation"].append({
                    "type": "Rising Three Methods",
                    "index": i,
                    "signal": "bullish_continuation",
                    "description": "Bullish trend continuation expected"
                })

        # === 多K线形态 (复杂形态) ===
        # 检测头肩顶/底
        if len(df) >= 10:
            highs = df["high"].values
            lows = df["low"].values

            # 寻找峰值
            peaks = []
            for i in range(2, len(highs) - 2):
                if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                    peaks.append(i)

            # 寻找谷值
            troughs = []
            for i in range(2, len(lows) - 2):
                if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                    troughs.append(i)

            # 头肩顶检测
            if len(peaks) >= 3:
                # 检查是否有左肩 < 头部 > 右肩的模式
                for i in range(len(peaks) - 2):
                    left_shoulder = peaks[i]
                    head = peaks[i + 1]
                    right_shoulder = peaks[i + 2]

                    if (highs[left_shoulder] < highs[head] and
                        highs[right_shoulder] < highs[head] and
                        abs(highs[left_shoulder] - highs[right_shoulder]) / highs[head] < 0.05):
                        patterns["reversal"].append({
                            "type": "Head and Shoulders Top",
                            "index": head,
                            "signal": "bearish",
                            "strength": "very_strong",
                            "description": "Major bearish reversal pattern, neckline breakout expected"
                        })

            # 头肩底检测
            if len(troughs) >= 3:
                for i in range(len(troughs) - 2):
                    left_shoulder = troughs[i]
                    head = troughs[i + 1]
                    right_shoulder = troughs[i + 2]

                    if (lows[left_shoulder] > lows[head] and
                        lows[right_shoulder] > lows[head] and
                        abs(lows[left_shoulder] - lows[right_shoulder]) / abs(lows[head]) < 0.05):
                        patterns["reversal"].append({
                            "type": "Head and Shoulders Bottom",
                            "index": head,
                            "signal": "bullish",
                            "strength": "very_strong",
                            "description": "Major bullish reversal pattern, neckline breakout expected"
                        })

        # 双顶/双底检测
        if len(df) >= 8:
            recent_highs = df["high"].values[-8:]
            recent_lows = df["low"].values[-8:]

            # 双顶
            max_high = max(recent_highs)
            high_indices = [i for i, h in enumerate(recent_highs) if h > max_high * 0.99]
            if len(high_indices) >= 2 and high_indices[-1] - high_indices[0] >= 3:
                patterns["reversal"].append({
                    "type": "Double Top",
                    "index": len(df) - 8 + high_indices[-1],
                    "signal": "bearish",
                    "strength": "strong",
                    "description": "Bearish reversal at resistance level"
                })

            # 双底
            min_low = min(recent_lows)
            low_indices = [i for i, l in enumerate(recent_lows) if l < min_low * 1.01]
            if len(low_indices) >= 2 and low_indices[-1] - low_indices[0] >= 3:
                patterns["reversal"].append({
                    "type": "Double Bottom",
                    "index": len(df) - 8 + low_indices[-1],
                    "signal": "bullish",
                    "strength": "strong",
                    "description": "Bullish reversal at support level"
                })

        return {
            "found": len(patterns["reversal"]) + len(patterns["continuation"]) + len(patterns["single"]) > 0,
            "patterns": patterns,
            "summary": self._summarize_patterns(patterns)
        }

    def _summarize_patterns(self, patterns: dict) -> str:
        """总结检测到的形态"""
        summary_parts = []

        if patterns["reversal"]:
            reversal_signals = [p["signal"] for p in patterns["reversal"]]
            bullish_count = sum(1 for s in reversal_signals if "bullish" in s)
            bearish_count = len(reversal_signals) - bullish_count

            if bullish_count > bearish_count:
                summary_parts.append(f"检测到 {bullish_count} 个看涨反转形态")
            elif bearish_count > bullish_count:
                summary_parts.append(f"检测到 {bearish_count} 个看跌反转形态")
            else:
                summary_parts.append(f"检测到 {len(reversal_signals)} 个反转形态")

        if patterns["continuation"]:
            summary_parts.append(f"检测到 {len(patterns['continuation'])} 个持续形态")

        if patterns["single"]:
            single_types = set(p["type"] for p in patterns["single"])
            summary_parts.append(f"单根K线形态: {', '.join(single_types)}")

        return "; ".join(summary_parts) if summary_parts else "未检测到明显形态"

    def detect_divergence(
        self,
        lookback: int = 20,
        indicator: str = "rsi"
    ) -> dict:
        """检测指标背离

        当价格创出新高/新低，但指标没有确认时，出现背离信号。
        这是趋势反转的重要预警信号。

        Args:
            lookback: 回溯K线数量
            indicator: 检测背离的指标 (rsi, macd)

        Returns:
            背离检测结果
        """
        # calculate_all() 需要至少50根K线
        min_required = max(50, lookback + 10)
        if self.data is None or len(self.data) < min_required:
            return {
                "found": False,
                "indicator": indicator,
                "divergences": {"bullish": [], "bearish": []},
                "summary": f"数据不足（需要至少{min_required}根K线，当前{len(self.data) if self.data is not None else 0}根）"
            }

        df = self.calculate_all()
        recent_df = df.iloc[-lookback:].copy()

        divergences = {
            "bullish": [],  # 看涨背离（价格创新低，指标未创新低）
            "bearish": [],  # 看跌背离（价格创新高，指标未创新高）
        }

        if indicator == "rsi" and "rsi" in df.columns:
            indicator_values = recent_df["rsi"].values
            price_values = recent_df["close"].values
        elif indicator == "macd" and "macd" in df.columns:
            indicator_values = recent_df["macd"].values
            price_values = recent_df["close"].values
        else:
            return {"error": f"Indicator {indicator} not available"}

        # 寻找价格波峰和波谷
        price_peaks = []
        price_troughs = []

        for i in range(2, len(price_values) - 2):
            # 局部高点
            if (price_values[i] > price_values[i-1] and
                price_values[i] > price_values[i-2] and
                price_values[i] > price_values[i+1] and
                price_values[i] > price_values[i+2]):
                price_peaks.append((i, price_values[i], indicator_values[i]))

            # 局部低点
            if (price_values[i] < price_values[i-1] and
                price_values[i] < price_values[i-2] and
                price_values[i] < price_values[i+1] and
                price_values[i] < price_values[i+2]):
                price_troughs.append((i, price_values[i], indicator_values[i]))

        # 检测看跌背离（价格创新高，指标未创新高）
        if len(price_peaks) >= 2:
            for i in range(len(price_peaks) - 1):
                idx1, price1, ind1 = price_peaks[i]
                idx2, price2, ind2 = price_peaks[i + 1]

                # 价格创新高，但指标没有创新高
                if price2 > price1 and ind2 < ind1:
                    # 确保背离幅度足够（避免噪音）
                    price_change = (price2 - price1) / price1
                    ind_change = abs(ind2 - ind1)

                    if price_change > 0.01 and ind_change > 2:  # 至少1%价格变化，2个指标单位
                        divergences["bearish"].append({
                            "type": "bearish_divergence",
                            "peak1_idx": idx1,
                            "peak2_idx": idx2,
                            "price_high1": price1,
                            "price_high2": price2,
                            "indicator_high1": ind1,
                            "indicator_high2": ind2,
                            "strength": "moderate" if ind_change > 5 else "weak",
                            "description": f"价格创新高但{indicator.upper()}未确认，可能趋势反转"
                        })

        # 检测看涨背离（价格创新低，指标未创新低）
        if len(price_troughs) >= 2:
            for i in range(len(price_troughs) - 1):
                idx1, price1, ind1 = price_troughs[i]
                idx2, price2, ind2 = price_troughs[i + 1]

                # 价格创新低，但指标没有创新低
                if price2 < price1 and ind2 > ind1:
                    price_change = abs((price2 - price1) / price1)
                    ind_change = abs(ind2 - ind1)

                    if price_change > 0.01 and ind_change > 2:
                        divergences["bullish"].append({
                            "type": "bullish_divergence",
                            "trough1_idx": idx1,
                            "trough2_idx": idx2,
                            "price_low1": price1,
                            "price_low2": price2,
                            "indicator_low1": ind1,
                            "indicator_low2": ind2,
                            "strength": "moderate" if ind_change > 5 else "weak",
                            "description": f"价格创新低但{indicator.upper()}未确认，可能趋势反转"
                        })

        return {
            "found": len(divergences["bullish"]) > 0 or len(divergences["bearish"]) > 0,
            "indicator": indicator,
            "divergences": divergences,
            "summary": self._summarize_divergences(divergences, indicator)
        }

    def _summarize_divergences(self, divergences: dict, indicator: str) -> str:
        """总结背离检测结果"""
        summary_parts = []

        if divergences["bullish"]:
            bullish_strength = [d["strength"] for d in divergences["bullish"]]
            strong_count = sum(1 for s in bullish_strength if s == "strong" or s == "moderate")
            summary_parts.append(
                f"检测到 {len(divergences['bullish'])} 个看涨背离({indicator.upper()})，"
                f"其中 {strong_count} 个强度较高"
            )

        if divergences["bearish"]:
            bearish_strength = [d["strength"] for d in divergences["bearish"]]
            strong_count = sum(1 for s in bearish_strength if s == "strong" or s == "moderate")
            summary_parts.append(
                f"检测到 {len(divergences['bearish'])} 个看跌背离({indicator.upper()})，"
                f"其中 {strong_count} 个强度较高"
            )

        return "; ".join(summary_parts) if summary_parts else f"未检测到{indicator.upper()}背离"

    def analyze_volume(self, lookback: int = 20) -> dict:
        """分析成交量

        检测成交量异常（放量/缩量）和成交量确认信号。

        Args:
            lookback: 回溯K线数量

        Returns:
            成交量分析结果
        """
        if self.data is None or len(self.data) < lookback + 20:
            return {"error": "Insufficient data for volume analysis"}

        df = self.data.iloc[-lookback:].copy()
        df["volume_sma"] = calculate_sma(df["volume"], 20)

        analysis = {
            "current_volume": df["volume"].iloc[-1],
            "avg_volume": df["volume_sma"].iloc[-1],
            "volume_ratio": df["volume"].iloc[-1] / df["volume_sma"].iloc[-1],
            "signals": [],
            "patterns": [],
        }

        vol_ratio = analysis["volume_ratio"]

        # 成交量状态分类
        if vol_ratio > 2.0:
            volume_status = "heavy_volume"  # 放量
            analysis["signals"].append("成交量显著放大（2倍以上平均）")
        elif vol_ratio > 1.5:
            volume_status = "above_average"  # 高于平均
            analysis["signals"].append("成交量高于平均")
        elif vol_ratio < 0.5:
            volume_status = "low_volume"  # 缩量
            analysis["signals"].append("成交量显著萎缩（低于平均50%）")
        elif vol_ratio < 0.8:
            volume_status = "below_average"  # 低于平均
            analysis["signals"].append("成交量低于平均")
        else:
            volume_status = "normal"  # 正常
            analysis["signals"].append("成交量正常")

        analysis["volume_status"] = volume_status

        # 成交量趋势分析
        recent_volumes = df["volume"].values[-5:]
        if all(recent_volumes[i] > recent_volumes[i+1] for i in range(len(recent_volumes)-1)):
            analysis["patterns"].append("成交量持续萎缩（市场观望）")
        elif all(recent_volumes[i] < recent_volumes[i+1] for i in range(len(recent_volumes)-1)):
            analysis["patterns"].append("成交量持续放大（市场活跃）")

        # OBV趋势分析
        df["obv"] = calculate_obv(df["close"], df["volume"])
        obv_trend = df["obv"].iloc[-5:].diff().mean()

        if obv_trend > 0:
            analysis["obv_trend"] = "up"
            analysis["signals"].append("OBV上升趋势（资金流入）")
        elif obv_trend < 0:
            analysis["obv_trend"] = "down"
            analysis["signals"].append("OBV下降趋势（资金流出）")
        else:
            analysis["obv_trend"] = "neutral"

        # 成交量与价格关系分析
        price_change = (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2]

        if vol_ratio > 1.5:  # 放量情况
            if price_change > 0:
                analysis["patterns"].append("放量上涨（买盘积极，看涨确认）")
            elif price_change < 0:
                analysis["patterns"].append("放量下跌（卖压沉重，看跌确认）")

        elif vol_ratio < 0.5:  # 缩量情况
            if price_change > 0:
                analysis["patterns"].append("缩量上涨（上涨乏力，需警惕）")
            elif price_change < 0:
                analysis["patterns"].append("缩量下跌（卖压有限，可能反弹）")

        # 成交量背离检测
        recent_prices = df["close"].values[-5:]
        recent_vols = df["volume"].values[-5:]

        price_trend = recent_prices[-1] - recent_prices[0]
        volume_trend = recent_vols[-1] - recent_vols[0]

        if price_trend > 0 and volume_trend < 0:
            analysis["patterns"].append("量价背离：价格上涨但成交量萎缩（预警）")
        elif price_trend < 0 and volume_trend > 0:
            analysis["patterns"].append("量价背离：价格下跌但成交量放大（可能见底）")

        return analysis

    def multi_timeframe_analysis(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
        interval: str = "30m"
    ) -> dict:
        """多时间框架分析

        分析不同时间框架的趋势一致性，这是技术分析的重要原则。

        Args:
            opens, highs, lows, closes, volumes: K线数据
            interval: 当前时间框架

        Returns:
            多时间框架分析结果
        """
        # 保存原始数据
        original_data = self.data

        # 定义时间框架层级
        if interval in ["1m", "3m", "5m"]:
            timeframes = [(interval, 50), ("15m", 50), ("1h", 50)]
        elif interval in ["15m", "30m"]:
            timeframes = [(interval, 50), ("1h", 50), ("4h", 50)]
        elif interval in ["1h", "2h", "4h"]:
            timeframes = [(interval, 50), ("4h", 50), ("1d", 50)]
        else:
            timeframes = [(interval, 50)]

        mtf_analysis = {
            "current_interval": interval,
            "timeframes": {},
            "confluence": [],  # 趋势一致性
            "summary": "",
        }

        # 由于我们这里只有单时间框架数据，
        # 实际实现中需要获取多个时间框架的K线数据
        # 这里提供一个框架，完整实现需要数据源支持

        # 分析当前时间框架
        self.load_data(opens, highs, lows, closes, volumes)
        current_trend = self.get_trend_analysis()
        mtf_analysis["timeframes"][interval] = current_trend

        # 恢复原始数据
        self.data = original_data

        # 计算趋势一致性（这里简化处理）
        trend = current_trend.get("trend", "neutral")
        mtf_analysis["confluence"] = [f"当前时间框架({interval})趋势: {trend}"]
        mtf_analysis["summary"] = f"基于{interval}时间框架分析，当前趋势为{trend}"

        return mtf_analysis
