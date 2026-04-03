"""
CLI 入口

提供命令行界面来启动和管理交易系统。
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from vibe_trading.config.settings import get_settings, TradingMode, set_settings, Settings
from vibe_trading.config.binance_config import BinanceConfig, BinanceEnvironment
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.data_sources.binance_client import BinanceClient
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.memory.memory import PersistentMemory
from vibe_trading.execution.order_executor import create_executor, TradingMode as ExecutorTradingMode

app = typer.Typer(help="Vibe Trading - Multi-Agent Cryptocurrency Trading System")
console = Console()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console)],
)
logger = logging.getLogger(__name__)


@app.command()
def start(
    symbol: str = typer.Argument(..., help="Trading symbol, e.g., BTCUSDT"),
    interval: str = typer.Option("30m", help="Kline interval (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    mode: str = typer.Option("paper", help="Trading mode: paper or live"),
    execute: bool = typer.Option(False, help="--execute: In live mode, actually execute orders (default: print only)"),
    debate_rounds: int = typer.Option(2, help="Number of debate rounds"),
    enable_memory: bool = typer.Option(True, help="Enable memory system"),
):
    """
    Start the trading bot for the specified symbol.

    The bot will subscribe to Kline data and make trading decisions
    using the multi-agent system.

    Example: vibe-trade start BTCUSDT
             vibe-trade start BTCUSDT --mode live
             vibe-trade start BTCUSDT --mode live --execute
    """
    # 实盘模式安全确认
    if mode == "live":
        if not execute:
            console.print("[red]⚠️  Warning: Live mode (dry-run) - orders will be printed but not executed[/red]")
            confirm = typer.confirm("Continue?")
            if not confirm:
                raise typer.Abort()
        else:
            console.print("[red]⚠️  Warning: Live mode (EXECUTE) - orders will be actually executed![/red]")
            console.print("[red]⚠️  This will use REAL funds for trading![/red]")
            confirm = typer.confirm("Continue?", default=False)
            if not confirm:
                raise typer.Abort()

    settings = get_settings()
    settings.trading_mode = TradingMode(mode)
    settings.debate_rounds = debate_rounds
    settings.enable_memory = enable_memory
    settings.symbols = [symbol]
    settings.interval = interval
    settings.execute_trades = execute  # 新增
    set_settings(settings)

    console.print(f"[bold cyan]Starting Vibe Trading Bot[/bold cyan]")
    console.print(f"Symbol: {symbol}")
    console.print(f"Interval: {interval}")
    console.print(f"Mode: {mode.upper()}")
    console.print(f"Execute Trades: {'Yes' if execute else 'No (print only)'}")
    console.print(f"Debate Rounds: {debate_rounds}")
    console.print(f"Memory: {'Enabled' if enable_memory else 'Disabled'}")
    console.print()

    # 运行交易机器人
    asyncio.run(run_trading_bot(symbol, interval, execute))


@app.command()
def analyze(
    symbol: str = typer.Option(..., help="Trading symbol"),
    interval: str = typer.Option("30m", help="Kline interval"),
    agent: str = typer.Option("all", help="Agent to run: all, analysts, researchers, risk, or decision"),
):
    """
    Run a single analysis cycle and display results.
    """
    asyncio.run(run_single_analysis(symbol, interval, agent))


@app.command()
def memory(
    action: str = typer.Option(..., help="Action: show, add, clear, export, import"),
    file: Optional[str] = typer.Option(None, help="File path for export/import"),
    situation: Optional[str] = typer.Option(None, help="Situation description (for add)"),
    advice: Optional[str] = typer.Option(None, help="Advice given (for add)"),
):
    """
    Manage the memory system.
    """
    asyncio.run(run_memory_command(action, file, situation, advice))


@app.command()
def config(
    show: bool = typer.Option(False, help="Show current configuration"),
    set_leverage: Optional[int] = typer.Option(None, help="Set maximum leverage"),
    set_position_size: Optional[float] = typer.Option(None, help="Set max position size"),
):
    """
    View or modify configuration.
    """
    settings = get_settings()

    if show:
        display_config(settings)
    else:
        modified = False
        if set_leverage:
            settings.leverage = set_leverage
            modified = True
        if set_position_size:
            settings.max_position_size = set_position_size
            modified = True

        if modified:
            set_settings(settings)
            console.print("[green]Configuration updated[/green]")
            display_config(settings)


async def run_trading_bot(symbol: str, interval: str, execute_trades: bool = False):
    """运行交易机器人"""
    settings = get_settings()

    # 初始化存储
    storage = KlineStorage()
    await storage.init()

    # 初始化记忆
    memory = None
    if settings.enable_memory:
        memory = PersistentMemory(f"./memory_{symbol.lower()}.pkl")
        memory.load()
        console.print(f"[green]Memory system loaded ({memory.size()} entries)[/green]")

    # 创建协调器
    coordinator = TradingCoordinator(
        symbol=symbol,
        interval=interval,
        storage=storage,
        memory=memory,
    )
    await coordinator.initialize()

    # 创建执行器 (支持dry-run模式)
    executor_mode = ExecutorTradingMode.LIVE if execute_trades else ExecutorTradingMode.PAPER
    executor = create_executor(executor_mode, dry_run=not execute_trades)

    # 创建 Binance 客户端用于订阅
    binance_config = BinanceConfig.from_env(
        BinanceEnvironment.TESTNET if settings.trading_mode == TradingMode.PAPER else BinanceEnvironment.MAINNET
    )
    binance_client = BinanceClient(binance_config)

    console.print("[bold green]Bot initialized. Starting to listen for Kline updates...[/bold green]")

    # K线处理函数
    async def handle_kline(kline):
        from vibe_trading.data_sources.binance_client import Kline

        # 存储K线
        await storage.store_kline(kline)

        # 只在K线完成时执行分析
        if kline.is_final:
            console.print(f"\n[bold yellow]New Kline closed for {symbol}[/bold yellow]")
            console.print(f"Close: {kline.close} | Volume: {kline.volume}")

            # 更新 Paper Trading 价格
            if settings.trading_mode == TradingMode.PAPER:
                from vibe_trading.execution.order_executor import PaperOrderExecutor
                if isinstance(executor, PaperOrderExecutor):
                    executor.update_price(symbol, kline.close)

            # 获取账户余额
            balance = await executor.get_balance()
            usdt_balance = balance.get("USDT", {}).get("balance", 10000.0)

            # 获取当前持仓
            positions = await executor.get_positions()

            # 执行分析决策
            decision = await coordinator.analyze_and_decide(
                current_price=kline.close,
                account_balance=usdt_balance,
                current_positions=[{
                    "symbol": p.symbol,
                    "position_amount": p.position_amount,
                    "entry_price": p.entry_price,
                    "unrealized_profit": p.unrealized_profit,
                } for p in positions],
            )

            # 显示决策
            display_decision(decision)

            # 执行交易（如果需要）
            if decision.decision in ["BUY", "STRONG BUY", "SELL", "STRONG SELL"]:
                console.print(f"[bold red]Would execute trade: {decision.decision}[/bold red]")
                # 实际交易执行逻辑可以在这里添加

    # 订阅K线
    from vibe_trading.data_sources.binance_client import KlineInterval
    try:
        # 先注册订阅回调
        binance_client.ws.subscribe_kline(
            symbol,
            KlineInterval(interval),
            handle_kline,
        )

        stream = f"{symbol.lower()}@kline_{interval}"
        console.print(f"[green]Subscribed to {stream}[/green]")
        console.print("Press Ctrl+C to stop...\n")

        # 启动 WebSocket 监听（会阻塞直到断开）
        await binance_client.ws.start()

    except KeyboardInterrupt:
        console.print("\n[bold]Stopping bot...[/bold]")
    finally:
        await binance_client.ws.disconnect()
        await storage.close()


async def run_single_analysis(symbol: str, interval: str, agent_filter: str):
    """运行单次分析"""
    console.print(f"[bold cyan]Running analysis for {symbol} ({interval})[/bold cyan]")

    # 初始化
    storage = KlineStorage()
    await storage.init()

    # 获取当前价格
    from vibe_trading.tools.market_data_tools import get_current_price
    price_data = await get_current_price(symbol, storage)
    current_price = price_data.get("price", 50000)

    console.print(f"Current price: ${current_price:.2f}\n")

    # 创建协调器
    coordinator = TradingCoordinator(symbol=symbol, interval=interval, storage=storage)
    await coordinator.initialize()

    # 执行分析
    decision = await coordinator.analyze_and_decide(current_price=current_price)

    # 显示结果
    display_decision(decision)

    # 显示Agent输出详情
    if agent_filter in ["all", "analysts"]:
        display_agent_outputs("Analysts", decision.agent_outputs.get("analysts", {}))

    await storage.close()


async def run_memory_command(action: str, file: Optional[str], situation: Optional[str], advice: Optional[str]):
    """运行记忆命令"""
    memory = PersistentMemory()
    memory.load()

    if action == "show":
        display_memory(memory)
    elif action == "add":
        if not situation or not advice:
            console.print("[red]Error: --situation and --advice required[/red]")
            return
        memory.add_memory(situation, advice)
        memory.save()
        console.print("[green]Memory entry added[/green]")
    elif action == "clear":
        memory.clear()
        memory.save()
        console.print("[green]Memory cleared[/green]")
    elif action == "export":
        if not file:
            file = "./memory_export.json"
        memory.export_to_json(file)
        console.print(f"[green]Memory exported to {file}[/green]")
    elif action == "import":
        if not file:
            console.print("[red]Error: --file required[/red]")
            return
        count = memory.import_from_json(file)
        memory.save()
        console.print(f"[green]Imported {count} memories from {file}[/green]")


def display_decision(decision):
    """显示交易决策"""
    # 决策颜色映射
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

    console.print(f"\n[bold]Final Decision:[/bold] [{color}]{decision.decision}[/{color}]")
    console.print(f"Time: {decision.timestamp}")

    # 显示决策理由摘要
    rationale_lines = decision.rationale.split("\n")[:5]
    for line in rationale_lines:
        if line.strip():
            console.print(f"  {line}")


def display_agent_outputs(title: str, outputs: dict):
    """显示Agent输出"""
    console.print(f"\n[bold]{title}:[/bold]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Agent", style="dim")
    table.add_column("Output")

    for agent, output in outputs.items():
        # 只显示前100个字符
        preview = output[:100] + "..." if len(output) > 100 else output
        table.add_row(agent, preview)

    console.print(table)


def display_memory(memory: PersistentMemory):
    """显示记忆内容"""
    memories = memory.get_all_memories()

    console.print(f"\n[bold]Memory Entries ({len(memories)}):[/bold]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim")
    table.add_column("Situation")
    table.add_column("Advice")
    table.add_column("PnL")

    for i, mem in enumerate(memories[-20:], 1):  # 只显示最近20条
        pnl_str = f"{mem.pnl:.2f}%" if mem.pnl is not None else "N/A"
        table.add_row(
            str(i),
            mem.situation[:50] + "..." if len(mem.situation) > 50 else mem.situation,
            mem.advice[:50] + "..." if len(mem.advice) > 50 else mem.advice,
            pnl_str,
        )

    console.print(table)


def display_config(settings: Settings):
    """显示配置"""
    console.print("\n[bold]Current Configuration:[/bold]")
    console.print(f"Trading Mode: {settings.trading_mode.value}")
    console.print(f"Symbols: {', '.join(settings.symbols)}")
    console.print(f"Interval: {settings.interval}")
    console.print(f"Max Position Size: {settings.max_position_size} USDT")
    console.print(f"Max Total Position: {settings.max_total_position} USDT")
    console.print(f"Stop Loss: {settings.stop_loss_pct * 100}%")
    console.print(f"Take Profit: {settings.take_profit_pct * 100}%")
    console.print(f"Leverage: {settings.leverage}x")
    console.print(f"Debate Rounds: {settings.debate_rounds}")
    console.print(f"Memory: {'Enabled' if settings.enable_memory else 'Disabled'}")
    console.print(f"LLM Config: {settings.llm_config_name}")
    # 从 pi_ai/config 获取可用模型列表
    try:
        from pi_ai.config import get_llm_config
        llm_config = get_llm_config()
        current_model = llm_config.get_model()
        console.print(f"Current Model: {current_model.id}")
    except:
        console.print(f"Current Model: {settings.llm_config_name}")


if __name__ == "__main__":
    app()
