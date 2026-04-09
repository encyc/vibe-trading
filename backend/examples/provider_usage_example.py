"""
标准化交易所接口使用示例

演示如何使用新的Provider接口。
"""
import asyncio
from vibe_trading.data_sources.providers.factory import ProviderFactory
from vibe_trading.data_sources.providers.models import StandardKline, StandardTicker


async def example_basic_usage():
    """基础使用示例"""
    print("=" * 60)
    print("示例1: 基础使用")
    print("=" * 60)

    # 创建Provider
    provider = await ProviderFactory.get_provider("binance")
    print(f"✓ 已连接到: {provider.exchange_name}")
    print(f"✓ 连接状态: {provider.status}")

    # 获取当前价格
    price = await provider.get_current_price("BTCUSDT")
    print(f"\nBTC/USDT 当前价格: ${price:,.2f}")

    # 获取K线数据
    klines = await provider.get_klines("BTCUSDT", "5m", 5)
    print(f"\n最近5根5分钟K线:")
    for i, k in enumerate(klines, 1):
        print(f"  {i}. 开:{k.open:,.2f} 高:{k.high:,.2f} 低:{k.low:,.2f} 收:{k.close:,.2f}")

    # 获取24小时行情
    ticker = await provider.get_ticker("BTCUSDT")
    print(f"\n24小时统计:")
    print(f"  价格变化: {ticker.price_change:+,.2f} ({ticker.price_change_percent:+.2f}%)")
    print(f"  最高价: ${ticker.high:,.2f}")
    print(f"  最低价: ${ticker.low:,.2f}")
    print(f"  成交量: {ticker.volume:,.2f} BTC")

    # 获取订单簿
    orderbook = await provider.get_orderbook("BTCUSDT", 5)
    print(f"\n订单簿 (前5档):")
    print(f"  买一: ${orderbook.bids[0].price:,.2f} (数量: {orderbook.bids[0].quantity:.4f})")
    print(f"  卖一: ${orderbook.asks[0].price:,.2f} (数量: {orderbook.asks[0].quantity:.4f})")
    print(f"  价差: ${orderbook.get_spread():,.2f}")


async def example_standard_models():
    """标准数据模型示例"""
    print("\n" + "=" * 60)
    print("示例2: 标准数据模型")
    print("=" * 60)

    provider = await ProviderFactory.get_provider("binance")
    klines = await provider.get_klines("ETHUSDT", "1h", 1)

    if klines:
        k = klines[0]
        print(f"\nStandardKline 对象示例:")
        print(f"  exchange:    {k.exchange}")
        print(f"  symbol:      {k.symbol}")
        print(f"  interval:     {k.interval}")
        print(f"  open_time:   {k.open_datetime}")
        print(f"  open:        ${k.open:,.2f}")
        print(f"  high:        ${k.high:,.2f}")
        print(f"  low:         ${k.low:,.2f}")
        print(f"  close:       ${k.close:,.2f}")
        print(f"  volume:      {k.volume:,.4f}")
        print(f"  is_final:    {k.is_final}")

        # 转换为字典
        data = k.to_dict()
        print(f"\n转换为字典: {len(data)}个字段")


async def example_multiple_exchanges():
    """多交易所示例（未来功能）"""
    print("\n" + "=" * 60)
    print("示例3: 多交易所支持（未来扩展）")
    print("=" * 60)

    print("\n当前支持的交易所:")
    from vibe_trading.data_sources.providers.registry import ProviderRegistry
    for exchange in ProviderRegistry.list_providers():
        print(f"  - {exchange}")

    print("\n未来可以轻松添加新交易所:")
    print("  1. 创建 OkxProvider(ExchangeProvider)")
    print("  2. ProviderRegistry.register('okx', OkxProvider)")
    print("  3. provider = await ProviderFactory.get_provider('okx')")


async def example_health_check():
    """健康检查示例"""
    print("\n" + "=" * 60)
    print("示例4: 健康检查")
    print("=" * 60)

    provider = await ProviderFactory.get_provider("binance")

    # 健康检查
    is_healthy = await provider.health_check()
    print(f"\n健康检查: {'✓ 健康' if is_healthy else '✗ 不健康'}")
    print(f"连接状态: {provider.status}")

    # 延迟信息
    if provider.status.latency_ms > 0:
        print(f"延迟: {provider.status.latency_ms:.1f}ms")


async def example_backward_compatibility():
    """向后兼容性示例"""
    print("\n" + "=" * 60)
    print("示例5: 向后兼容性")
    print("=" * 60)

    # 现有工具函数仍然可以正常使用
    from vibe_trading.tools.market_data_tools import get_current_price, get_kline_data

    print("\n使用原有工具函数:")
    result = await get_current_price("BTCUSDT")
    print(f"  get_current_price: ${result['price']:,.2f}")

    kline_result = await get_kline_data("BTCUSDT", "5m", 3)
    print(f"  get_kline_data: {kline_result['count']}条K线")

    print("\n✓ 所有现有代码无需修改即可工作")


async def main():
    """运行所有示例"""
    try:
        await example_basic_usage()
        await example_standard_models()
        await example_multiple_exchanges()
        await example_health_check()
        await example_backward_compatibility()

        print("\n" + "=" * 60)
        print("所有示例完成！")
        print("=" * 60)

    finally:
        # 清理资源
        await ProviderFactory.close_all()
        print("\n✓ 资源已清理")


if __name__ == "__main__":
    asyncio.run(main())
