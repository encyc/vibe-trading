"""
Vibe Trading - 主入口

支持实盘和纸面交易模式
"""
import asyncio
import logging
import signal
import sys
from enum import Enum
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pi_logger import get_logger, configure_logging, info, success, warning

from vibe_trading.config.settings import get_settings
from vibe_trading.config.agent_config import AgentTeamConfig
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
from vibe_trading.websocket_manager import get_websocket_manager
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.memory.memory import PersistentMemory
from vibe_trading.execution.order_executor import create_executor, TradingMode

# 初始化
app = typer.Typer(help="Vibe Trading - AI驱动的量化交易系统")
console = Console()
logger = get_logger("main")


class TradingMode(str, Enum):
    """交易模式"""
    PAPER = "paper"  # 纸面交易
    LIVE = "live"    # 实盘交易


class TradingBot:
    """交易机器人"""

    def __init__(
        self,
        symbols: List[str],
        interval: str,
        mode: TradingMode,
        execute_trades: bool = False,
    ):
        self.symbols = symbols
        self.interval = interval
        self.mode = mode
        self.execute_trades = execute_trades

        # 组件
        self.coordinators: dict = {}
        self.storage: Optional[KlineStorage] = None
        self.memory: Optional[PersistentMemory] = None
        self.ws_manager = None

        # 运行状态
        self._running = False

    async def initialize(self) -> None:
        """初始化交易机器人"""
        settings = get_settings()

        # 初始化存储
        self.storage = KlineStorage()
        await self.storage.init()

        # 初始化记忆系统
        self.memory = PersistentMemory(storage_dir=settings.memory_storage_dir)
        await self.memory.init()

        # 初始化WebSocket管理器
        self.ws_manager = get_websocket_manager(
            api_key=settings.binance_api_key if self.mode == TradingMode.LIVE else None,
            api_secret=settings.binance_api_secret if self.mode == TradingMode.LIVE else None,
            testnet=self.mode == TradingMode.PAPER,
        )

        # 为每个symbol创建协调器
        agent_config = AgentTeamConfig()
        for symbol in self.symbols:
            coordinator = TradingCoordinator(
                symbol=symbol,
                interval=self.interval,
                storage=self.storage,
                memory=self.memory,
                agent_config=agent_config,
            )
            await coordinator.initialize()
            self.coordinators[symbol] = coordinator

        success(f"交易机器人初始化完成: {len(self.symbols)} 个交易对", tag="Bot")

    async def start(self) -> None:
        """启动交易机器人"""
        self._running = True

        # 显示启动信息
        self._display_startup_info()

        # 订阅K线流
        for symbol in self.symbols:
            await self.ws_manager.subscribe_kline(
                symbol=symbol,
                interval=self.interval,
                callback=self._on_kline,
            )

        # 启动WebSocket
        await self.ws_manager.start()

        success("交易机器人已启动，等待K线数据...", tag="Bot")

        # 保持运行
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            info("收到停止信号")
            await self.stop()

    async def _on_kline(self, kline) -> None:
        """新K线到达时的回调"""
        try:
            symbol = kline.symbol
            if symbol not in self.coordinators:
                return

            coordinator = self.coordinators[symbol]

            # 执行分析和决策
            await coordinator.on_new_kline(kline)

        except Exception as e:
            logger.error(f"处理K线失败: {e}", exc_info=True)

    def _display_startup_info(self) -> None:
        """显示启动信息"""
        mode_color = "green" if self.mode == TradingMode.PAPER else "red"
        mode_text = "📝 纸面交易模式" if self.mode == TradingMode.PAPER else "⚠️  实盘交易模式"

        console.print()
        console.print(Panel(
            f"[bold {mode_color}]{mode_text}[/bold {mode_color}]\n\n"
            f"交易对: {', '.join(self.symbols)}\n"
            f"K线周期: {self.interval}\n"
            f"执行交易: {'是' if self.execute_trades else '否 (仅打印)'}",
            title="[bold cyan]🤖 Vibe Trading[/bold cyan]",
            border_style="cyan",
        ))

        if self.mode == TradingMode.LIVE and not self.execute_trades:
            console.print("[yellow]⚠️  警告: 实盘模式但未启用--execute，订单将被打印但不会真正执行[/yellow]")

        console.print()

    async def stop(self) -> None:
        """停止交易机器人"""
        info("正在停止交易机器人...")
        self._running = False

        # 停止WebSocket
        if self.ws_manager:
            await self.ws_manager.stop()

        # 关闭存储
        if self.storage:
            await self.storage.close()

        # 关闭记忆系统
        if self.memory:
            await self.memory.close()

        success("交易机器人已停止")


@app.command()
def start(
    symbols: List[str] = typer.Argument(..., help="交易对符号，如 BTCUSDT ETHUSDT"),
    interval: str = typer.Option("30m", help="K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    mode: str = typer.Option("paper", help="交易模式: paper (纸面) 或 live (实盘)"),
    execute: bool = typer.Option(False, help="--execute: 实盘模式下真正执行订单"),
    log_level: str = typer.Option("INFO", help="日志级别: DEBUG, INFO, WARNING, ERROR"),
):
    """
    启动交易机器人

    订阅实时K线数据，每当新K线完成时触发Agent决策流程。

    示例:
        # 纸面交易
        python -m vibe_trading.main start BTCUSDT

        # 实盘交易 (仅打印订单)
        python -m vibe_trading.main start BTCUSDT --mode live

        # 实盘交易 (真正执行)
        python -m vibe_trading.main start BTCUSDT --mode live --execute

        # 多交易对
        python -m vibe_trading.main start BTCUSDT ETHUSDT SOLUSDT
    """
    # 配置日志
    configure_logging(log_level=log_level, json_output=False, enable_file_logging=True)

    # 验证交易模式
    trading_mode = TradingMode.PAPER
    if mode == "live":
        trading_mode = TradingMode.LIVE
        # 实盘模式二次确认
        if not execute:
            console.print("[red]⚠️  警告: 实盘交易模式 (dry-run) - 订单将被打印但不会执行[/red]")
            confirm = typer.confirm("确定要继续吗？")
            if not confirm:
                raise typer.Abort()
        else:
            console.print("[red]⚠️  警告: 实盘交易模式 (EXECUTE) - 订单将被真正执行！[/red]")
            console.print("[red]⚠️  这将使用真实资金进行交易！[/red]")
            confirm = typer.confirm("确定要继续吗？", default=False)
            if not confirm:
                raise typer.Abort()

    # 创建交易机器人
    bot = TradingBot(
        symbols=symbols,
        interval=interval,
        mode=trading_mode,
        execute_trades=execute,
    )

    # 信号处理
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 运行
    try:
        loop.run_until_complete(bot.initialize())
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        info("收到键盘中断")
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(bot.stop())
        loop.close()


@app.command()
def analyze(
    symbol: str = typer.Argument(..., help="交易对符号"),
    interval: str = typer.Option("30m", help="K线间隔"),
):
    """
    运行单次分析

    获取当前市场数据并执行一次完整的Agent决策流程
    """
    configure_logging(log_level="INFO", json_output=False)

    async def run_analysis():
        storage = KlineStorage()
        await storage.init()

        coordinator = TradingCoordinator(
            symbol=symbol,
            interval=interval,
            storage=storage,
        )
        await coordinator.initialize()

        # 获取当前价格
        from vibe_trading.tools.market_data_tools import get_current_price
        current_price = await get_current_price(symbol)

        # 执行分析
        decision = await coordinator.analyze_and_decide(
            current_price=current_price,
            account_balance=10000.0,
        )

        console.print()
        console.print(Panel(
            f"[bold]决策: {decision.decision}[/bold]\n\n{decision.rationale[:300]}...",
            title=f"[bold cyan]{symbol} 分析结果[/bold cyan]",
        ))

        await storage.close()

    asyncio.run(run_analysis())


@app.command()
def status():
    """显示系统状态"""
    settings = get_settings()

    table = Table(title="Vibe Trading 系统状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")

    table.add_row("交易模式", "纸面交易 (Paper Trading)")
    table.add_row("Binance API", "✅ 已配置" if settings.binance_api_key else "❌ 未配置")
    table.add_row("存储目录", str(settings.storage_dir))
    table.add_row("记忆目录", str(settings.memory_storage_dir))

    console.print(table)


if __name__ == "__main__":
    app()
