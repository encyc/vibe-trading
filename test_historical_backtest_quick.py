#!/usr/bin/env python3
"""
快速回测 - 只分析1条K线，展示完整的Agent调用流程
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.data_sources.binance_client import Kline
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.config.agent_config import AgentTeamConfig

console = Console()


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


async def run_quick_backtest():
    """执行快速回测"""

    console.print()
    console.print(Panel(
        "[bold yellow]📊 Vibe Trading 快速回测[/bold yellow]",
        padding=(1, 1),
        subtitle="展示真实Agent调用",
    ))

    # 配置
    symbol = "BTCUSDT"
    interval = "1m"

    # 生成单条K线
    console.print()
    console.print(Panel(f"[bold cyan]生成模拟K线数据[/bold cyan]"))
    kline = generate_single_kline(symbol, interval)

    console.print(f"  时间: {kline.close_datetime}")
    console.print(f"  开: ${kline.open:.2f}  高: ${kline.high:.2f}  低: ${kline.low:.2f}  收: ${kline.close:.2f}")
    console.print(f"  成交量: {kline.volume:.2f}")

    # 初始化存储
    storage = KlineStorage()
    await storage.init()
    await storage.store_klines([kline])

    # 创建协调器
    console.print()
    console.print(Panel("[bold cyan]初始化交易协调器[/bold cyan]"))
    agent_config = AgentTeamConfig()
    coordinator = TradingCoordinator(
        symbol=symbol,
        interval=interval,
        storage=storage,
        memory=None,
        agent_config=agent_config,
    )
    await coordinator.initialize()

    # 执行分析
    console.print()
    console.print(Panel(
        "[bold yellow]开始Agent分析流程[/bold yellow]",
        subtitle="这将调用13个Agent，需要2-3分钟",
    ))

    import time
    start_time = time.time()

    try:
        decision = await coordinator.analyze_and_decide(
            current_price=kline.close,
            account_balance=10000.0,
            current_positions=[],
        )

        total_time = time.time() - start_time

        # 显示结果
        console.print()
        console.print(Panel(
            "[bold green]分析完成[/bold green]",
            border_style="green",
            padding=(1, 1),
        ))

        colors = {
            "STRONG BUY": "bold green",
            "BUY": "green",
            "WEAK BUY": "dim green",
            "HOLD": "yellow",
            "WEAK SELL": "dim red",
            "SELL": "red",
            "STRONG SELL": "bold red",
        }
        color = colors.get(decision.decision, "white")

        console.print(f"  决策: [{color}]{decision.decision}[/{color}]")
        console.print(f"  总耗时: {total_time:.2f}秒")
        console.print(f"  理由: {decision.rationale[:300]}...")

    except Exception as e:
        console.print(f"[red]分析失败: {e}[/red]")
        import traceback
        traceback.print_exc()

    finally:
        await storage.close()

    console.print()
    console.print("[green]✅ 回测完成[/green]")


if __name__ == "__main__":
    asyncio.run(run_quick_backtest())
