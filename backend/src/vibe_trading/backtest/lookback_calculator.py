"""
回测数据Lookback计算器

计算技术指标所需的历史数据量，确保回测时有足够的数据预加载。
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional


@dataclass
class IndicatorLookback:
    """单个指标的lookback需求"""
    indicator_name: str
    lookback_periods: int  # 需要的历史K线数
    parameters: Dict[str, Any]  # 指标参数


class LookbackCalculator:
    """
    计算技术指标所需的历史数据量

    用于确定回测时需要额外加载多少历史K线数据，
    以确保技术指标在回测第一天就能正确计算。

    Examples:
        >>> calculator = LookbackCalculator()
        >>> lookback = calculator.calculate_indicator_lookback("macd", {"fast": 12, "slow": 26, "signal": 9})
        >>> print(lookback)  # 35 (26 + 9)

        >>> lookback = calculator.calculate_total_lookback([
        ...     {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        ...     {"name": "rsi", "params": {"period": 14}},
        ... ], interval="1d")
        >>> print(lookback)  # 42 (max(35, 14) * 1.2)
    """

    # 默认指标配置
    DEFAULT_INDICATORS = {
        "rsi": {"period": 14},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "bollinger": {"period": 20, "std_dev": 2},
        "sma": {"period": 20},
        "ema": {"period": 20},
        "atr": {"period": 14},
        "stochastic": {"k_period": 14, "d_period": 3},
    }

    def calculate_indicator_lookback(
        self,
        indicator: str,
        params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        计算单个指标的lookback需求

        Args:
            indicator: 指标名称（如"macd", "rsi", "bollinger"）
            params: 指标参数（如果为None则使用默认值）

        Returns:
            需要的历史K线周期数

        Examples:
            >>> calculator = LookbackCalculator()
            >>> calculator.calculate_indicator_lookback("macd")
            35  # slow(26) + signal(9)

            >>> calculator.calculate_indicator_lookback("rsi", {"period": 14})
            14
        """
        # 使用默认参数
        if params is None:
            params = self.DEFAULT_INDICATORS.get(indicator, {})

        indicator = indicator.lower()

        # MACD: max(fast, slow) + signal
        if indicator == "macd":
            fast = params.get("fast", 12)
            slow = params.get("slow", 26)
            signal = params.get("signal", 9)
            return max(fast, slow) + signal

        # RSI: period
        elif indicator == "rsi":
            return params.get("period", 14)

        # Bollinger Bands: period
        elif indicator == "bollinger" or indicator == "bollinger_bands":
            return params.get("period", 20)

        # SMA/EMA: period
        elif indicator in ["sma", "ema"]:
            return params.get("period", 20)

        # ATR: period
        elif indicator == "atr":
            return params.get("period", 14)

        # Stochastic: max(k_period, d_period)
        elif indicator == "stochastic":
            k_period = params.get("k_period", 14)
            d_period = params.get("d_period", 3)
            return max(k_period, d_period)

        # 其他指标：默认返回20
        else:
            return 20

    def calculate_total_lookback(
        self,
        indicators_config: List[Dict[str, Any]],
        interval: str,
        safety_margin: float = 0.2
    ) -> int:
        """
        计算所有指标的最大lookback需求

        Args:
            indicators_config: 指标配置列表
                [{"name": "macd", "params": {...}}, {"name": "rsi", "params": {...}}]
            interval: K线间隔（如"30m", "1h", "1d"）
            safety_margin: 安全边际比例（默认20%）

        Returns:
            需要的总历史K线周期数（包含安全边际）

        Examples:
            >>> calculator = LookbackCalculator()
            >>> config = [
            ...     {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            ...     {"name": "rsi", "params": {"period": 14}},
            ... ]
            >>> lookback = calculator.calculate_total_lookback(config, "1d")
            >>> print(lookback)  # 42 (35 * 1.2)
        """
        if not indicators_config:
            # 如果没有指定指标，使用所有默认指标
            indicators_config = [
                {"name": name, "params": params}
                for name, params in self.DEFAULT_INDICATORS.items()
            ]

        # 计算每个指标的lookback
        max_lookback = 0
        for config in indicators_config:
            indicator_name = config.get("name", "")
            params = config.get("params", {})

            lookback = self.calculate_indicator_lookback(indicator_name, params)
            max_lookback = max(max_lookback, lookback)

        # 添加安全边际
        total_lookback = int(max_lookback * (1 + safety_margin))

        return total_lookback

    def calculate_lookback_timedelta(
        self,
        lookback_periods: int,
        interval: str
    ) -> timedelta:
        """
        将lookback周期数转换为时间增量

        Args:
            lookback_periods: lookback周期数
            interval: K线间隔（如"30m", "1h", "1d"）

        Returns:
            对应的时间增量

        Examples:
            >>> calculator = LookbackCalculator()
            >>> td = calculator.calculate_lookback_timedelta(35, "1d")
            >>> print(td)  # 35 days
        """
        interval_minutes = self._parse_interval_to_minutes(interval)
        total_minutes = interval_minutes * lookback_periods
        return timedelta(minutes=total_minutes)

    def adjust_data_load_range(
        self,
        start_time,
        lookback_periods: int,
        interval: str
    ):
        """
        调整数据加载的开始时间（包含lookback期间）

        Args:
            start_time: 原始回测开始时间
            lookback_periods: 需要额外加载的历史周期数
            interval: K线间隔

        Returns:
            调整后的开始时间（更早）

        Examples:
            >>> from datetime import datetime
            >>> calculator = LookbackCalculator()
            >>> start = datetime(2026, 1, 1)
            >>> adjusted = calculator.adjust_data_load_range(start, 35, "1d")
            >>> print(adjusted)  # 2025-11-27 (前推35天)
        """
        lookback_timedelta = self.calculate_lookback_timedelta(
            lookback_periods, interval
        )
        return start_time - lookback_timedelta

    def _parse_interval_to_minutes(self, interval: str) -> int:
        """
        解析interval字符串为分钟数

        Args:
            interval: K线间隔（如"1m", "5m", "1h", "1d"）

        Returns:
            对应的分钟数
        """
        interval = interval.lower()

        if interval.endswith('m'):
            return int(interval[:-1])
        elif interval.endswith('h'):
            return int(interval[:-1]) * 60
        elif interval.endswith('d'):
            return int(interval[:-1]) * 60 * 24
        elif interval.endswith('w'):
            return int(interval[:-1]) * 60 * 24 * 7
        else:
            # 默认30分钟
            return 30

    def get_lookback_summary(
        self,
        indicators_config: List[Dict[str, Any]],
        interval: str
    ) -> Dict[str, Any]:
        """
        获取lookback需求的摘要信息

        Args:
            indicators_config: 指标配置列表
            interval: K线间隔

        Returns:
            包含详细lookback信息的字典
        """
        individual_lookbacks = []
        for config in indicators_config:
            indicator_name = config.get("name", "")
            params = config.get("params", {})
            lookback = self.calculate_indicator_lookback(indicator_name, params)
            individual_lookbacks.append({
                "indicator": indicator_name,
                "lookback_periods": lookback,
                "parameters": params,
            })

        total_lookback = self.calculate_total_lookback(indicators_config, interval)
        lookback_timedelta = self.calculate_lookback_timedelta(total_lookback, interval)

        return {
            "individual_lookbacks": individual_lookbacks,
            "total_lookback_periods": total_lookback,
            "lookback_timedelta": str(lookback_timedelta),
            "max_individual_lookback": max(
                lb["lookback_periods"] for lb in individual_lookbacks
            ) if individual_lookbacks else 0,
        }


# =============================================================================
# 便捷函数
# =============================================================================

def calculate_lookback_for_backtest(
    indicators: Optional[List[str]] = None,
    interval: str = "30m"
) -> int:
    """
    便捷函数：计算回测所需的lookback周期数

    Args:
        indicators: 指标列表（如果为None则使用所有默认指标）
        interval: K线间隔

    Returns:
        需要的lookback周期数

    Examples:
        >>> calculate_lookback_for_backtest(["macd", "rsi"], "1d")
        42
    """
    calculator = LookbackCalculator()

    if indicators is None:
        # 使用所有默认指标
        indicators_config = [
            {"name": name, "params": params}
            for name, params in calculator.DEFAULT_INDICATORS.items()
        ]
    else:
        # 使用指定的指标
        indicators_config = [
            {"name": indicator, "params": calculator.DEFAULT_INDICATORS.get(indicator, {})}
            for indicator in indicators
            if indicator in calculator.DEFAULT_INDICATORS
        ]

    return calculator.calculate_total_lookback(indicators_config, interval)
