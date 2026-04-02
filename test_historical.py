#!/usr/bin/env python
"""
使用历史数据回测交易系统

获取历史 K线数据，模拟触发交易决策流程。
支持 Web 界面实时监控。
"""
import asyncio
import sys
import os
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.config.settings import get_settings
from vibe_trading.config.binance_config import BinanceConfig
from vibe_trading.data_sources.binance_client import BinanceClient, KlineInterval, Kline
from vibe_trading.data_sources.kline_storage import KlineStorage, KlineQuery
from vibe_trading.data_sources.technical_indicators import TechnicalIndicators
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.config.agent_config import AgentTeamConfig

console = Console()

# Web 推送
_web_enabled = False
try:
    from vibe_trading.web.server import (
        send_kline, send_decision, send_log, send_phase, send_report, run_server
    )
    _web_enabled = True
    console.print("[green]✓ Web 推送已启用[/green]")
except ImportError:
    _web_enabled = False
    console.print("[yellow]⚠ Web 模块未找到，运行: uv add fastapi uvicorn[/yellow]")


async def send_log_both(level: str, tag: str, message: str):
    """同时发送到控制台和 Web"""
    if _web_enabled:
        await send_log(level, tag, message)


async def fetch_historical_klines(symbol: str, interval: str, limit: int = 100) -> list[Kline]:
    """获取历史 K线数据"""
    console.print(Panel(f"[bold cyan]获取 {symbol} {interval} 历史数据 (最近 {limit} 条)[/bold cyan]"))
    await send_log_both("info", "System", f"获取 {symbol} {interval} 历史数据...")

    config = BinanceConfig.from_env()
    client = BinanceClient(config)

    try:
        klines_data = await client.rest.get_klines(
            symbol=symbol,
            interval=KlineInterval(interval),
            limit=limit,
        )

        klines = []
        for k in klines_data:
            kline = Kline.from_rest(k)
            kline.symbol = symbol
            kline.interval = interval
            klines.append(kline)

        console.print(f"  ✓ 获取到 {len(klines)} 条 K线数据")
        console.print(f"  ✓ 时间范围: {klines[0].close_datetime} ~ {klines[-1].close_datetime}")
        console.print(f"  ✓ 价格区间: ${min(k.low for k in klines):.2f} ~ ${max(k.high for k in klines):.2f}")

        await send_log_both("success", "Data", f"获取到 {len(klines)} 条 K线数据")

        # 推送所有历史 K线数据到 Web
        if _web_enabled:
            for kline in klines:
                await send_kline({
                    "time": kline.close_datetime.isoformat(),
                    "open": kline.open,
                    "high": kline.high,
                    "low": kline.low,
                    "close": kline.close,
                    "volume": kline.volume,
                })

        return klines
    finally:
        await client.close()


async def analyze_kline(coordinator: TradingCoordinator, kline: Kline, index: int, total: int) -> dict:
    """分析单条 K线"""
    console.print()
    console.print(Panel(f"[bold yellow]分析 K线 #{index}/{total}[/bold yellow]"))
    console.print(f"  时间: {kline.close_datetime}")
    console.print(f"  开: ${kline.open:.2f}  高: ${kline.high:.2f}  低: ${kline.low:.2f}  收: ${kline.close:.2f}")
    console.print(f"  成交量: {kline.volume:.2f}")

    await send_log_both("info", "Kline", f"#{index}/{total} {kline.close_datetime} @ ${kline.close:.2f}")

    # 推送 K线数据
    if _web_enabled:
        await send_kline({
            "time": kline.close_datetime.isoformat(),
            "open": kline.open,
            "high": kline.high,
            "low": kline.low,
            "close": kline.close,
            "volume": kline.volume,
        })

    try:
        decision = await coordinator.analyze_and_decide(
            current_price=kline.close,
            account_balance=10000.0,
            current_positions=[],
        )

        # 显示决策
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

        console.print(f"\n[bold]决策: [{color}]{decision.decision}[/{color}][/bold]")

        # 显示理由摘要（前3行）
        for line in decision.rationale.split("\n")[:3]:
            if line.strip():
                console.print(f"  {line.strip()}")

        await send_log_both("success", "Decision", f"{decision.decision}: {decision.rationale[:100]}...")

        # 推送决策
        if _web_enabled:
            await send_decision({
                "index": index,
                "time": kline.close_datetime.isoformat(),
                "close": kline.close,
                "decision": decision.decision,
                "rationale": decision.rationale,
            })

        return {
            "index": index,
            "time": kline.close_datetime,
            "close": kline.close,
            "decision": decision.decision,
            "rationale": decision.rationale[:200],
        }
    except Exception as e:
        console.print(f"[red]分析失败: {e}[/red]")
        await send_log_both("error", "Error", str(e))
        return {
            "index": index,
            "time": kline.close_datetime,
            "close": kline.close,
            "decision": "ERROR",
            "rationale": str(e),
        }


async def main():
    """主函数"""
    console.print()
    console.print(Panel("[bold yellow]📊 Vibe Trading 历史数据回测[/bold yellow]", padding=(1, 1)))
    console.print()

    # 配置
    symbol = "BTCUSDT"
    interval = "1m"
    num_klines = 200  # 获取200条K线用于技术指标计算
    analyze_count = 3  # 只分析最近3条

    # 启动 Web 服务器（如果启用）
    if _web_enabled:
        import threading
        import time

        def run_server_sync():
            run_server(port=8000)

        server_thread = threading.Thread(target=run_server_sync, daemon=True)
        server_thread.start()

        # 等待服务器启动
        console.print("[dim]等待 Web 服务器启动...[/dim]")
        time.sleep(2)  # 给服务器时间启动
        console.print("[green]✓ Web 服务器: http://localhost:8000[/green]")
        console.print()

    # 初始化存储
    storage = KlineStorage()
    await storage.init()

    # 获取历史数据
    klines = await fetch_historical_klines(symbol, interval, num_klines)

    # 存储到数据库
    console.print(f"\n[dim]存储 K线数据到数据库...[/dim]")
    await storage.store_klines(klines)

    # 创建协调器
    console.print(f"\n[bold cyan]初始化交易协调器...[/bold cyan]")
    agent_config = AgentTeamConfig()
    coordinator = TradingCoordinator(
        symbol=symbol,
        interval=interval,
        storage=storage,
        memory=None,  # 回测不使用记忆
        agent_config=agent_config,
    )
    await coordinator.initialize()
    console.print(f"  ✓ 协调器已初始化")

    # 逐条分析K线（只分析最近几条）
    console.print()
    console.print(Panel(f"[bold magenta]开始逐条分析 K线 (最近 {analyze_count} 条)[/bold magenta]"))
    results = []

    klines_to_analyze = klines[-analyze_count:]
    for i, kline in enumerate(klines_to_analyze, 1):
        result = await analyze_kline(coordinator, kline, i, len(klines_to_analyze))
        results.append(result)

    # 汇总结果
    console.print()
    console.print(Panel("[bold green]📋 回测结果汇总[/bold green]"))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("时间", width=16)
    table.add_column("价格", justify="right")
    table.add_column("决策", justify="center")

    for r in results:
        decision_color = "green" if "BUY" in r["decision"] else "red" if "SELL" in r["decision"] else "yellow"
        table.add_row(
            str(r["index"]),
            r["time"].strftime("%m-%d %H:%M"),
            f"${r["close"]:.2f}",
            f"[{decision_color}]{r['decision']}[/{decision_color}]",
        )

    console.print(table)

    # 统计
    buys = sum(1 for r in results if "BUY" in r["decision"])
    sells = sum(1 for r in results if "SELL" in r["decision"])
    holds = sum(1 for r in results if r["decision"] == "HOLD")

    console.print(f"\n[bold]决策统计:[/bold]")
    console.print(f"  买入信号: {buys}")
    console.print(f"  卖出信号: {sells}")
    console.print(f"  观望: {holds}")

    # 清理
    await storage.close()

    console.print()
    console.print("[green]✅ 回测完成[/green]")

    if _web_enabled:
        console.print("\n[dim]Web 界面仍在运行，按 Ctrl+C 退出[/dim]")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(main())
