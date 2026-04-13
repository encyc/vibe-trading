"""
实际回测执行脚本

运行一个简单的回测来验证整个系统的工作状态。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加backend/src到路径
sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))

from pi_logger import get_logger

logger = get_logger(__name__)


async def run_simple_backtest():
    """运行一个简单的回测"""
    print("\n" + "="*60)
    print("开始实际回测执行")
    print("="*60)

    from vibe_trading.backtest.engine import BacktestEngine
    from vibe_trading.backtest.models import BacktestConfig, LLMMode, ReportFormat

    # 创建配置
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval="1d",
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 10),  # 短时间范围测试
        initial_balance=10000.0,

        # 使用SIMULATED模式快速测试
        llm_mode=LLMMode.SIMULATED,

        # 启用进度条
        enable_progress_bar=True,

        # 生成HTML和JSON报告
        report_formats=[ReportFormat.TEXT, ReportFormat.JSON],

        # 启用检查点
        save_checkpoints=True,
        checkpoint_interval=2,  # 每2根K线保存一次
    )

    print(f"\n回测配置:")
    print(f"  交易品种: {config.symbol}")
    print(f"  K线间隔: {config.interval}")
    print(f"  时间范围: {config.start_time} ~ {config.end_time}")
    print(f"  初始资金: ${config.initial_balance:,.2f}")
    print(f"  LLM模式: {config.llm_mode.value}")

    try:
        # 创建引擎
        engine = BacktestEngine(config)

        # 运行回测
        print(f"\n开始回测...")
        result = await engine.run_backtest()

        # 显示结果
        if result.error_message:
            print(f"\n❌ 回测失败: {result.error_message}")
            return False

        print(f"\n{'='*60}")
        print(f"回测完成！")
        print(f"{'='*60}")

        if result.metrics:
            print(f"\n📊 性能指标:")
            print(f"  总收益率: {result.metrics.total_return:.2%}")
            print(f"  夏普比率: {result.metrics.sharpe_ratio:.2f}")
            print(f"  最大回撤: {result.metrics.max_drawdown:.2%}")
            print(f"  胜率: {result.metrics.win_rate:.2%}")
            print(f"  总交易: {result.metrics.total_trades}")
            print(f"  盈利交易: {result.metrics.profitable_trades}")
            print(f"  亏损交易: {result.metrics.losing_trades}")

        print(f"\n⏱️  执行统计:")
        print(f"  总K线数: {result.total_klines}")
        print(f"  执行时间: {result.execution_time:.2f}秒")
        print(f"  LLM调用: {result.llm_calls}")
        print(f"  缓存命中: {result.llm_cache_hits}")
        print(f"  缓存命中率: {result.cache_hit_rate:.1%}")

        print(f"\n📈 交易统计:")
        print(f"  总交易数: {len(result.trades)}")
        if result.trades:
            winning_trades = [t for t in result.trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in result.trades if t.pnl and t.pnl <= 0]
            print(f"  盈利交易: {len(winning_trades)}")
            print(f"  亏损交易: {len(losing_trades)}")

            if result.trades:
                total_pnl = sum(t.pnl for t in result.trades if t.pnl)
                print(f"  总盈亏: ${total_pnl:.2f}")

        print(f"\n📁 结果文件:")
        print(f"  CSV: ./backtest_results/trades_{config.symbol}_*.csv")
        print(f"  JSON: ./backtest_results/result_{config.symbol}_*.json")
        print(f"  检查点: ./checkpoints/{config.symbol}_*.json")

        return True

    except Exception as e:
        print(f"\n❌ 回测执行异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    try:
        success = await run_simple_backtest()
        if success:
            print(f"\n✅ 回测执行成功！")
        else:
            print(f"\n❌ 回测执行失败")
    except KeyboardInterrupt:
        print(f"\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 未处理的异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
