#!/usr/bin/env python3
"""
系统改进功能展示 - 在实际回测中展示改进效果
"""
import asyncio
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.layout import Layout

from vibe_trading.data_sources.binance_client import Kline
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.config.agent_config import AgentTeamConfig

# 导入改进功能模块用于展示
from vibe_trading.coordinator.state_machine import DecisionStateMachine, DecisionState, get_state_machine_manager
from vibe_trading.agents.messaging import get_message_broker
from vibe_trading.config.logging_config import configure_logging, get_logger, PerformanceLogger
from vibe_trading.data_sources.rate_limiter import get_multi_endpoint_limiter
from vibe_trading.data_sources.cache import get_global_cache, cached
from vibe_trading.agents.token_optimizer import get_token_optimizer

console = Console()

# 配置日志
configure_logging(log_level="INFO", json_output=False, enable_file_logging=False)
logger = get_logger("demo_improvements")


def generate_single_kline(symbol: str = "BTCUSDT", interval: str = "1m") -> Kline:
    """生成单条模拟K线数据"""
    import random

    base_price = 67000.0
    current_time = datetime.now() - timedelta(minutes=1)

    price_change = random.uniform(-0.001, 0.001)
    open_price = base_price * (1 + price_change)
    high_price = open_price * random.uniform(1.0, 1.0005)
    low_price = open_price * random.uniform(0.9995, 1.0)
    close_price = open_price * random.uniform(0.999, 1.001)
    volume = random.uniform(100, 500)

    kline = Kline(
        symbol=symbol,
        interval=interval,
        open_time=int(current_time.timestamp() * 1000),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        close_time=int((current_time + timedelta(minutes=1)).timestamp() * 1000),
        quote_volume=volume * close_price,
        trades=random.randint(100, 1000),
        taker_buy_base=volume * random.uniform(0.4, 0.6),
        taker_buy_quote=volume * close_price * random.uniform(0.4, 0.6),
        is_final=True,
    )

    return kline


class ImprovementsMonitor:
    """改进功能监控器"""

    def __init__(self):
        self.state_machine = None
        self.message_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.api_calls = 0
        self.tokens_saved = 0

        # 获取改进功能模块
        self.state_manager = get_state_machine_manager()
        self.message_broker = get_message_broker()
        self.rate_limiter = get_multi_endpoint_limiter()
        self.cache = get_global_cache()
        self.token_optimizer = get_token_optimizer()

    def show_state_machine_tracking(self):
        """展示状态机管理"""
        console.print()
        console.print(Panel(
            "[bold cyan]1️⃣ 状态机管理[/bold cyan]",
            title="决策流程状态追踪",
            border_style="cyan",
            padding=(1, 1),
        ))

        if self.state_machine:
            summary = self.state_machine.get_state_summary()
            console.print(f"  📊 决策ID: {summary['decision_id']}")
            console.print(f"  📍 当前阶段: {summary['current_phase']}")
            console.print(f"  ⏱ 耗时: {summary['duration_seconds']:.2f}秒")
            console.print(f"  📝 状态转换数: {len(summary['state_history'])}")
        else:
            console.print("  ℹ️ 当前没有活跃的状态机")

    def show_messaging(self):
        """展示Agent消息标准化"""
        stats = self.message_broker.get_statistics()
        console.print(f"  📨 消息总数: {stats['total_messages']}")
        console.print(f"  📊 活跃线程: {stats['active_threads']}")

    def show_rate_limiting(self):
        """展示API限流管理"""
        limiter = self.rate_limiter.get_limiter("binance_rest")
        remaining = limiter.get_remaining_tokens()

        console.print(f"  🛡️ API限流器状态:")
        console.print(f"     分钟剩余令牌: {remaining['minute']}")
        console.print(f"     小时剩余令牌: {remaining['hour']}")

    def show_caching(self):
        """展示缓存机制"""
        stats = self.cache.get_stats()
        self.cache_hits = stats['memory']['hits']
        self.cache_misses = stats['memory']['misses']

        hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0

        console.print(f"  💾 缓存统计:")
        console.print(f"     命中次数: {self.cache_hits}")
        console.print(f"     未命中: {self.cache_misses}")
        console.print(f"     命中率: {hit_rate:.1%}")

    def show_token_optimization(self, text: str):
        """展示Token优化"""
        original_len = len(text)
        compressed = self.token_optimizer.compress_prompt(text)
        saved_tokens = self.token_optimizer.estimate_tokens(text) - self.token_optimizer.estimate_tokens(compressed)

        console.print(f"  🎯 Token优化:")
        console.print(f"     原始长度: {original_len} 字符")
        console.print(f"     压缩后: {len(compressed)} 字符")
        console.print(f"     压缩率: {len(compressed)/original_len:.1%}")
        console.print(f"     节省Token: ~{saved_tokens} tokens")

        self.tokens_saved += saved_tokens

    async def demo_caching_benefit(self):
        """演示缓存加速效果"""
        @cached(ttl=60, key_prefix="demo")
        async def expensive_calculation(x: int, y: int) -> int:
            await asyncio.sleep(0.1)
            return x + y

        # 第一次调用
        start = time.time()
        result1 = await expensive_calculation(123, 456)
        time1 = time.time() - start

        # 第二次调用（从缓存）
        start = time.time()
        result2 = await expensive_calculation(123, 456)
        time2 = time.time() - start

        speedup = time1 / time2 if time2 > 0 else 1

        console.print(f"  ⚡ 缓存加速效果:")
        console.print(f"     首次调用: {time1*1000:.1f}ms")
        console.print(f"     第二次(缓存): {time2*1000:.1f}ms")
        console.print(f"     加速比: {speedup:.1f}x")


async def run_monitored_backtest():
    """运行带监控展示的回测"""

    console.print()
    console.print(Panel(
        "[bold yellow]📊 Vibe Trading 改进功能展示回测[/bold yellow]",
        padding=(1, 1),
        subtitle="可视化展示8项改进功能的实际效果",
    ))

    # 创建监控器
    monitor = ImprovementsMonitor()

    # 配置
    symbol = "BTCUSDT"
    interval = "1m"

    # 生成单条K线
    kline = generate_single_kline(symbol, interval)

    console.print(f"  📅 K线数据: {kline.close_datetime} | 价格: ${kline.close:.2f}")

    # 初始化存储
    storage = KlineStorage()
    await storage.init()
    await storage.store_klines([kline])

    # 创建协调器
    coordinator = TradingCoordinator(
        symbol=symbol,
        interval=interval,
        storage=storage,
        memory=None,
        agent_config=AgentTeamConfig(),
    )
    await coordinator.initialize()

    # 创建状态机用于追踪
    monitor.state_machine = DecisionStateMachine(
        decision_id=f"demo_{kline.close_datetime.timestamp()}",
        symbol=kline.symbol,
        interval=kline.interval,
    )

    console.print()
    console.print(Panel(
        "[bold green]开始分析 - 改进功能实时监控[/bold green]",
        border_style="green",
        padding=(1, 1),
    ))

    import time
    start_time = time.time()

    try:
        # 在分析前展示状态机
        monitor.state_machine.transition_to(DecisionState.ANALYZING, "开始分析师阶段")
        monitor.show_state_machine_tracking()

        # 分析前展示Token优化
        sample_prompt = f"分析 {symbol} 当前价格 ${kline.close:.2f} 的交易机会，考虑技术指标RSI、MACD、布林带等..."
        monitor.show_token_optimization(sample_prompt)

        # 演示缓存加速
        console.print("\n[dim]演示缓存加速效果...[/dim]")
        await monitor.demo_caching_benefit()

        # 演示API限流
        console.print("\n[dim]演示API限流保护...[/dim]")
        for i in range(3):
            await monitor.rate_limiter.get_limiter("binance_rest").acquire(tokens=1)
        monitor.api_calls += 1
        monitor.show_rate_limiting()

        # 执行实际分析
        console.print("\n[dim]▶ 执行coordinator.analyze_and_decide()...[/dim]")

        decision = await coordinator.analyze_and_decide(
            current_price=kline.close,
            account_balance=10000.0,
            current_positions=[],
        )

        total_time = time.time() - start_time

        # 分析完成后展示状态
        monitor.state_machine.transition_to(DecisionState.COMPLETED, "分析完成")
        monitor.show_state_machine_tracking()

        # 展示消息统计
        console.print()
        console.print(Panel(
            "[bold cyan]改进功能效果统计[/bold cyan]",
            border_style="cyan",
            padding=(1, 1),
        ))

        monitor.show_messaging()
        monitor.show_caching()
        console.print(f"\n  ⏱ 总耗时: {total_time:.2f}秒")
        console.print(f"  🎯 最终决策: {decision.decision}")

    except Exception as e:
        console.print(f"\n[red]分析失败: {e}[/red]")
        import traceback
        traceback.print_exc()

    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(run_monitored_backtest())
