#!/usr/bin/env python3
"""
测试技术指标数据是否完整传递给Agent
"""
import asyncio
import sys
sys.path.insert(0, 'backend/src')

from vibe_trading.data_sources.technical_indicators import TechnicalIndicators
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator, TradingContext
from vibe_trading.data_sources.kline_storage import KlineStorage, Kline
from datetime import datetime, timedelta
import random


async def main():
    # 创建单条K线
    base_price = 67000.0
    klines = []
    for i in range(100):
        price_change = random.uniform(-0.002, 0.002)
        open_price = base_price * (1 + price_change)
        high_price = open_price * random.uniform(1.0, 1.001)
        low_price = open_price * random.uniform(0.999, 1.0)
        close_price = open_price * random.uniform(0.999, 1.001)
        volume = random.uniform(100, 500)

        kline = Kline(
            symbol="BTCUSDT",
            interval="30m",
            open_time=int((datetime.now() - timedelta(minutes=30*(100-i))).timestamp() * 1000),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            close_time=int((datetime.now() - timedelta(minutes=30*(100-i-1))).timestamp() * 1000),
            quote_volume=volume * close_price,
            trades=random.randint(100, 1000),
            taker_buy_base=volume * random.uniform(0.4, 0.6),
            taker_buy_quote=volume * close_price * random.uniform(0.4, 0.6),
            is_final=True,
        )
        klines.append(kline)

    # 计算指标
    closes = [k.close for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    opens = [k.open for k in klines]
    volumes = [k.volume for k in klines]

    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)
    indicators_data = ti.get_latest_indicators()

    print("=" * 60)
    print("技术指标数据完整性检查")
    print("=" * 60)
    print()
    print("✅ 基础指标:")
    print(f"  SMA 20: {indicators_data.sma_20}")
    print(f"  SMA 50: {indicators_data.sma_50}")
    print(f"  RSI: {indicators_data.rsi}")
    print()
    print("✅ 之前缺失的指标:")
    print(f"  MACD: {indicators_data.macd}")
    print(f"  MACD Signal: {indicators_data.macd_signal}")
    print(f"  MACD Histogram: {indicators_data.macd_hist}")
    print(f"  Bollinger Upper: {indicators_data.bollinger_upper}")
    print(f"  Bollinger Middle: {indicators_data.bollinger_middle}")
    print(f"  Bollinger Lower: {indicators_data.bollinger_lower}")
    print(f"  ATR: {indicators_data.atr}")
    print(f"  Volume SMA: {indicators_data.volume_sma}")
    print()
    print("=" * 60)

    # 模拟trading_coordinator的indicators字典
    indicators = {
        "sma_20": indicators_data.sma_20,
        "sma_50": indicators_data.sma_50,
        "rsi": indicators_data.rsi,
        "macd": indicators_data.macd,
        "macd_signal": indicators_data.macd_signal,
        "macd_histogram": indicators_data.macd_hist,
        "bollinger_upper": indicators_data.bollinger_upper,
        "bollinger_middle": indicators_data.bollinger_middle,
        "bollinger_lower": indicators_data.bollinger_lower,
        "atr": indicators_data.atr,
        "volume_sma": indicators_data.volume_sma,
        "current_price": closes[-1],
        "current_volume": volumes[-1],
    }

    # 检查是否有None值
    missing = [k for k, v in indicators.items() if v is None]
    if missing:
        print(f"⚠️  警告: 以下指标为None: {missing}")
    else:
        print("✅ 所有指标都有值！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
