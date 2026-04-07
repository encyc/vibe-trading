#!/usr/bin/env python3
"""
回测系统快速演示

展示如何使用回测系统进行策略测试。
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.backtest.engine import BacktestEngine
from vibe_trading.backtest.models import BacktestConfig, LLMMode, ReportFormat


async def demo_basic_backtest():
    """基础回测演示"""
    print("=" * 70)
    print("演示 1: 基础回测（使用模拟模式）")
    print("=" * 70)

    # 创建配置 - 测试最近3天
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval="1h",
        start_time=datetime.now() - timedelta(days=3),
        end_time=datetime.now(),
        initial_balance=10000.0,
        llm_mode=LLMMode.SIMULATED,
        report_formats=[ReportFormat.TEXT],
    )

    print(f"\n回测配置:")
    print(f"  交易品种: {config.symbol}")
    print(f"  K线间隔: {config.interval}")
    print(f"  时间范围: {config.start_time} ~ {config.end_time}")
    print(f"  初始余额: ${config.initial_balance:,.2f}")
    print(f"  LLM模式: {config.llm_mode.value}")

    # 运行回测
    print(f"\n开始回测...")
    engine = BacktestEngine(config)
    result = await engine.run_backtest()

    # 显示结果
    if result.metrics:
        print(f"\n📊 回测结果:")
        print(f"  总收益率: {result.metrics.total_return:.2%}")
        print(f"  夏普比率: {result.metrics.sharpe_ratio:.2f}")
        print(f"  最大回撤: {result.metrics.max_drawdown:.2%}")
        print(f"  胜率: {result.metrics.win_rate:.2%}")
        print(f"  总交易: {result.metrics.total_trades}")
        print(f"  执行时间: {result.execution_time:.2f}秒")


async def demo_parameter_comparison():
    """参数对比演示"""
    print("\n" + "=" * 70)
    print("演示 2: 对比不同 K线周期的表现")
    print("=" * 70)

    end_time = datetime.now() - timedelta(days=7)  # 一周前
    start_time = end_time - timedelta(days=3)      # 测试3天

    intervals = ["15m", "30m", "1h", "4h"]
    results = {}

    for interval in intervals:
        print(f"\n测试 {interval} K线...")

        config = BacktestConfig(
            symbol="BTCUSDT",
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            initial_balance=10000.0,
            llm_mode=LLMMode.SIMULATED,
        )

        engine = BacktestEngine(config)
        result = await engine.run_backtest()

        if result.metrics:
            results[interval] = {
                "return": result.metrics.total_return,
                "sharpe": result.metrics.sharpe_ratio,
                "trades": result.metrics.total_trades,
                "drawdown": result.metrics.max_drawdown,
            }

    # 显示对比结果
    print("\n📊 参数对比结果:")
    print(f"{'周期':<8} {'收益率':<12} {'夏普比率':<10} {'交易数':<8} {'最大回撤':<12}")
    print("-" * 60)
    for interval, metrics in results.items():
        print(f"{interval:<8} {metrics['return']:>10.2%}   {metrics['sharpe']:>8.2f}   "
              f"{metrics['trades']:>6}   {metrics['drawdown']:>10.2%}")

    # 找出最佳周期
    best_interval = max(results, key=lambda x: results[x]['sharpe'])
    print(f"\n✨ 最佳周期: {best_interval} (夏普比率: {results[best_interval]['sharpe']:.2f})")


async def demo_llm_modes():
    """LLM模式对比演示"""
    print("\n" + "=" * 70)
    print("演示 3: 对比不同 LLM 模式的性能")
    print("=" * 70)

    end_time = datetime.now() - timedelta(days=7)
    start_time = end_time - timedelta(days=1)

    modes = [LLMMode.SIMULATED, LLMMode.CACHED]
    results = {}

    for mode in modes:
        print(f"\n测试 {mode.value} 模式...")

        config = BacktestConfig(
            symbol="BTCUSDT",
            interval="1h",
            start_time=start_time,
            end_time=end_time,
            initial_balance=10000.0,
            llm_mode=mode,
        )

        engine = BacktestEngine(config)
        result = await engine.run_backtest()

        if result.metrics:
            results[mode.value] = {
                "return": result.metrics.total_return,
                "time": result.execution_time,
                "klines": result.total_klines,
            }

    # 显示对比结果
    print("\n📊 LLM 模式对比:")
    print(f"{'模式':<15} {'收益率':<12} {'执行时间':<12} {'K线数':<10}")
    print("-" * 55)
    for mode, metrics in results.items():
        print(f"{mode:<15} {metrics['return']:>10.2%}   {metrics['time']:>8.2f}s   "
              f"{metrics['klines']:>8}")

    # 计算速度对比
    if len(results) >= 2:
        simulated_time = results.get('simulated', {}).get('time', 0)
        cached_time = results.get('cached', {}).get('time', 0)
        if simulated_time and cached_time:
            speedup = cached_time / simulated_time
            print(f"\n⚡ SIMULATED 模式比 CACHED 模式快 {speedup:.1f}x")


async def main():
    """主函数"""
    print("\n" + "🚀 " * 17)
    print("Vibe Trading 回测系统演示")
    print("🚀 " * 17)

    # 演示1: 基础回测
    await demo_basic_backtest()

    # 演示2: 参数对比（可选，需要较长时间）
    print("\n" + "=" * 70)
    choice = input("是否继续运行参数对比演示？(需要较长时间) [y/N]: ")
    if choice.lower() == 'y':
        await demo_parameter_comparison()

    # 演示3: LLM模式对比（可选，需要较长时间）
    print("\n" + "=" * 70)
    choice = input("是否继续运行 LLM 模式对比演示？(需要较长时间) [y/N]: ")
    if choice.lower() == 'y':
        await demo_llm_modes()

    print("\n" + "=" * 70)
    print("演示完成！")
    print("=" * 70)
    print("\n💡 提示:")
    print("  - 使用 SIMULATED 模式可以快速测试策略")
    print("  - 使用 CACHED 模式可以避免重复的 LLM 调用")
    print("  - 查看 BACKTEST_GUIDE.md 了解更多使用方法")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n演示已中断")
        sys.exit(0)
