"""
技术分析功能测试脚本

测试新增的K线形态识别、背离检测、成交量分析等功能。
"""
import asyncio
import sys
from pathlib import Path
import os
# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.data_sources.technical_indicators import TechnicalIndicators
import pandas as pd
import numpy as np


def generate_test_klines(pattern: str = "uptrend") -> list:
    """生成测试用K线数据"""

    if pattern == "uptrend":
        # 上升趋势
        base_price = 50000
        klines = []
        for i in range(100):
            open_p = base_price + i * 100 + np.random.randn() * 200
            close_p = open_p + np.random.randn() * 300 + 50
            high_p = max(open_p, close_p) + abs(np.random.randn() * 200)
            low_p = min(open_p, close_p) - abs(np.random.randn() * 150)
            volume = 1000000 + np.random.randn() * 200000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    elif pattern == "downtrend":
        # 下降趋势
        base_price = 60000
        klines = []
        for i in range(100):
            open_p = base_price - i * 100 + np.random.randn() * 200
            close_p = open_p + np.random.randn() * 300 - 50
            high_p = max(open_p, close_p) + abs(np.random.randn() * 200)
            low_p = min(open_p, close_p) - abs(np.random.randn() * 150)
            volume = 1000000 + np.random.randn() * 200000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    elif pattern == "ranging":
        # 震荡市
        base_price = 55000
        klines = []
        for i in range(100):
            open_p = base_price + np.random.randn() * 500
            close_p = open_p + np.random.randn() * 400
            high_p = max(open_p, close_p) + abs(np.random.randn() * 200)
            low_p = min(open_p, close_p) - abs(np.random.randn() * 150)
            volume = 1000000 + np.random.randn() * 200000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    elif pattern == "morning_star":
        # 早晨之星形态 (看涨反转)
        klines = []
        # 下跌趋势
        for i in range(30):
            open_p = 60000 - i * 100
            close_p = open_p - 50 - np.random.randn() * 100
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 1000000
            klines.append((open_p, high_p, low_p, close_p, volume))
        # 第一根：大阴线
        klines.append((57000, 57100, 56500, 56550, 1500000))
        # 第二根：小十字星（Doji）
        klines.append((56550, 56700, 56400, 56580, 800000))
        # 第三根：大阳线（超过第一根跌幅一半）
        klines.append((56580, 57200, 56500, 57100, 1800000))
        # 继续上涨
        for i in range(20):
            open_p = 57100 + i * 80
            close_p = open_p + 50 + np.random.randn() * 100
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 1200000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    elif pattern == "engulfing_bullish":
        # 看涨吞没形态
        klines = []
        # 下跌趋势
        for i in range(30):
            open_p = 60000 - i * 100
            close_p = open_p - 50 - np.random.randn() * 100
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 1000000
            klines.append((open_p, high_p, low_p, close_p, volume))
        # 第一根：小阴线
        klines.append((57000, 57100, 56800, 56850, 1000000))
        # 第二根：大阳线吞没
        klines.append((56800, 57500, 56750, 57450, 2000000))
        # 继续上涨
        for i in range(20):
            open_p = 57450 + i * 80
            close_p = open_p + 50 + np.random.randn() * 100
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 1200000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    elif pattern == "divergence_bullish":
        # 看涨背离（价格创新低，RSI未创新低）
        klines = []
        # 第一波下跌
        for i in range(20):
            open_p = 60000 - i * 200
            close_p = open_p - 100 - np.random.randn() * 200
            high_p = max(open_p, close_p) + 150
            low_p = min(open_p, close_p) - 150
            volume = 1500000
            klines.append((open_p, high_p, low_p, close_p, volume))
        # 反弹
        for i in range(10):
            open_p = 56000 + i * 150
            close_p = open_p + 80 + np.random.randn() * 100
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 800000
            klines.append((open_p, high_p, low_p, close_p, volume))
        # 第二波下跌（创新低，但力度小）
        for i in range(15):
            open_p = 57500 - i * 100
            close_p = open_p - 50 - np.random.randn() * 150
            high_p = max(open_p, close_p) + 100
            low_p = min(open_p, close_p) - 100
            volume = 1000000 - i * 30000  # 成交量萎缩
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines

    else:
        # 默认随机
        klines = []
        for i in range(100):
            open_p = 55000 + np.random.randn() * 1000
            close_p = open_p + np.random.randn() * 500
            high_p = max(open_p, close_p) + abs(np.random.randn() * 300)
            low_p = min(open_p, close_p) - abs(np.random.randn() * 300)
            volume = 1000000 + np.random.randn() * 300000
            klines.append((open_p, high_p, low_p, close_p, volume))
        return klines


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_candlestick_patterns():
    """测试K线形态识别"""
    print_section("测试 1: K线形态识别")

    test_cases = [
        ("uptrend", "上升趋势"),
        ("downtrend", "下降趋势"),
        ("ranging", "震荡市"),
        ("morning_star", "早晨之星形态"),
        ("engulfing_bullish", "看涨吞没形态"),
    ]

    for pattern, name in test_cases:
        print(f"\n--- {name} ---")
        klines = generate_test_klines(pattern)
        opens = [k[0] for k in klines]
        highs = [k[1] for k in klines]
        lows = [k[2] for k in klines]
        closes = [k[3] for k in klines]
        volumes = [k[4] for k in klines]

        ti = TechnicalIndicators()
        ti.load_data(opens, highs, lows, closes, volumes)
        result = ti.detect_candlestick_patterns(lookback=min(30, len(klines)))

        print(f"检测到形态: {result['found']}")
        print(f"总结: {result['summary']}")

        if result['found']:
            for category, patterns in result['patterns'].items():
                if patterns:
                    print(f"  [{category}]")
                    for p in patterns[:3]:  # 只显示前3个
                        print(f"    - {p.get('type', 'Unknown')}: {p.get('description', '')}")


def test_divergence_detection():
    """测试背离检测"""
    print_section("测试 2: 指标背离检测")

    test_cases = [
        ("divergence_bullish", "看涨背离（价格创新低RSI未创新低）"),
        ("uptrend", "上升趋势（通常无背离）"),
    ]

    for pattern, name in test_cases:
        print(f"\n--- {name} ---")
        klines = generate_test_klines(pattern)
        opens = [k[0] for k in klines]
        highs = [k[1] for k in klines]
        lows = [k[2] for k in klines]
        closes = [k[3] for k in klines]
        volumes = [k[4] for k in klines]

        ti = TechnicalIndicators()
        ti.load_data(opens, highs, lows, closes, volumes)

        # RSI背离
        rsi_div = ti.detect_divergence(lookback=30, indicator="rsi")
        print(f"RSI背离: {rsi_div['found']}")
        print(f"  总结: {rsi_div['summary']}")

        if rsi_div['found']:
            if rsi_div['divergences']['bullish']:
                print(f"  看涨背离: {len(rsi_div['divergences']['bullish'])}个")
            if rsi_div['divergences']['bearish']:
                print(f"  看跌背离: {len(rsi_div['divergences']['bearish'])}个")


def test_volume_analysis():
    """测试成交量分析"""
    print_section("测试 3: 成交量分析")

    # 创建不同成交量模式的测试数据
    print("\n--- 放量上涨模式 ---")
    klines = generate_test_klines("uptrend")
    # 修改最后几根K线为放量上涨
    for i in range(-5, 0):
        o, h, l, c, v = klines[i]
        klines[i] = (o, h + 100, l, c + 150, v * 2.5)  # 放量2.5倍

    opens = [k[0] for k in klines]
    highs = [k[1] for k in klines]
    lows = [k[2] for k in klines]
    closes = [k[3] for k in klines]
    volumes = [k[4] for k in klines]

    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    result = ti.analyze_volume(lookback=20)

    print(f"当前成交量: {result['current_volume']:,.0f}")
    print(f"平均成交量: {result['avg_volume']:,.0f}")
    print(f"成交量比率: {result['volume_ratio']:.2f}x")
    print(f"成交量状态: {result['volume_status']}")
    print(f"OBV趋势: {result.get('obv_trend', 'N/A')}")
    print(f"信号:")
    for signal in result['signals']:
        print(f"  - {signal}")
    print(f"模式:")
    for pattern in result['patterns']:
        print(f"  - {pattern}")


def test_trend_analysis():
    """测试趋势分析"""
    print_section("测试 4: 趋势分析")

    test_cases = [
        ("uptrend", "上升趋势"),
        ("downtrend", "下降趋势"),
        ("ranging", "震荡市"),
    ]

    for pattern, name in test_cases:
        print(f"\n--- {name} ---")
        klines = generate_test_klines(pattern)
        opens = [k[0] for k in klines]
        highs = [k[1] for k in klines]
        lows = [k[2] for k in klines]
        closes = [k[3] for k in klines]
        volumes = [k[4] for k in klines]

        ti = TechnicalIndicators()
        ti.load_data(opens, highs, lows, closes, volumes)
        result = ti.get_trend_analysis()

        print(f"趋势方向: {result['trend']}")
        print(f"趋势强度: {result['strength']}")
        print(f"信号:")
        for signal in result['signals']:
            print(f"  - {signal}")


def test_all_indicators():
    """测试所有技术指标计算"""
    print_section("测试 5: 技术指标计算")

    klines = generate_test_klines("uptrend")
    opens = [k[0] for k in klines]
    highs = [k[1] for k in klines]
    lows = [k[2] for k in klines]
    closes = [k[3] for k in klines]
    volumes = [k[4] for k in klines]

    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    indicators = ti.get_latest_indicators()

    print("\n=== 趋势指标 ===")
    print(f"SMA 20:  {indicators.sma_20:,.2f}" if indicators.sma_20 else "SMA 20:  N/A")
    print(f"SMA 50:  {indicators.sma_50:,.2f}" if indicators.sma_50 else "SMA 50:  N/A")
    print(f"EMA 12:  {indicators.ema_12:,.2f}" if indicators.ema_12 else "EMA 12:  N/A")
    print(f"EMA 26:  {indicators.ema_26:,.2f}" if indicators.ema_26 else "EMA 26:  N/A")

    print("\n=== 动量指标 ===")
    print(f"RSI:     {indicators.rsi:.2f}" if indicators.rsi else "RSI:     N/A")
    print(f"MACD:    {indicators.macd:.2f}" if indicators.macd else "MACD:    N/A")
    print(f"MACD信号: {indicators.macd_signal:.2f}" if indicators.macd_signal else "MACD信号: N/A")
    print(f"MACD柱:  {indicators.macd_hist:.2f}" if indicators.macd_hist else "MACD柱:  N/A")

    print("\n=== 波动率指标 ===")
    print(f"布林上轨: {indicators.bollinger_upper:,.2f}" if indicators.bollinger_upper else "布林上轨: N/A")
    print(f"布林中轨: {indicators.bollinger_middle:,.2f}" if indicators.bollinger_middle else "布林中轨: N/A")
    print(f"布林下轨: {indicators.bollinger_lower:,.2f}" if indicators.bollinger_lower else "布林下轨: N/A")
    print(f"ATR:     {indicators.atr:.2f}" if indicators.atr else "ATR:     N/A")

    print("\n=== 成交量指标 ===")
    print(f"成交量MA: {indicators.volume_sma:,.0f}" if indicators.volume_sma else "成交量MA: N/A")


def main():
    """运行所有测试"""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  技术分析功能测试".center(56) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    try:
        test_all_indicators()
        test_trend_analysis()
        test_candlestick_patterns()
        test_divergence_detection()
        test_volume_analysis()

        print_section("测试完成")
        print("✅ 所有功能测试通过")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
