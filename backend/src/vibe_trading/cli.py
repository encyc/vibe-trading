"""
Vibe Trading - 主入口

支持实盘和纸面交易模式，使用三线程架构:
1. Macro Judgment Thread - 每小时分析宏观环境
2. Main Trading Thread - K线触发决策流程
3. Event-Driven Thread - 监控紧急事件
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

from pi_logger import get_logger, configure, info, success, warning, separator

from vibe_trading.config.settings import get_settings
from vibe_trading.main.multi_thread_main import MultiThreadedTradingSystem
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.memory.memory import PersistentMemory
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator

# 初始化
app = typer.Typer(help="Vibe Trading - AI驱动的量化交易系统")
console = Console()
logger = get_logger("main")


class TradingMode(str, Enum):
    """交易模式"""
    PAPER = "paper"  # 纸面交易
    LIVE = "live"    # 实盘交易


@app.command()
def start(
    symbols: List[str] = typer.Argument(..., help="交易对符号，如 BTCUSDT ETHUSDT"),
    interval: str = typer.Option("30m", help="K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    mode: str = typer.Option("paper", help="交易模式: paper (纸面) 或 live (实盘)"),
    execute: bool = typer.Option(False, help="--execute: 实盘模式下真正执行订单"),
    log_level: str = typer.Option("INFO", help="日志级别: DEBUG, INFO, WARNING, ERROR"),
    save_logs: bool = typer.Option(True, help="--save-logs/--no-save-logs: 是否保存日志到文件 (默认保存到 logs/ 目录)"),
):
    """
    启动三线程交易系统

    使用三线程架构:
    - Macro Thread: 每小时分析宏观环境
    - On Bar Thread: K线触发决策流程
    - Event Thread: 监控紧急事件并触发应急流程

    示例:
        # 纸面交易
        python -m vibe_trading.main start BTCUSDT

        # 实盘交易 (仅打印订单)
        python -m vibe_trading.main start BTCUSDT --mode live

        # 实盘交易 (真正执行)
        python -m vibe_trading.main start BTCUSDT --mode live --execute

        # 多交易对 (使用第一个作为主symbol)
        python -m vibe_trading.main start BTCUSDT ETHUSDT SOLUSDT
    """
    # 配置日志
    configure(log_level=log_level, json_output=False, enable_file_logging=True)

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

    # 显示启动信息
    mode_color = "green" if trading_mode == TradingMode.PAPER else "red"
    mode_text = "📝 纸面交易模式" if trading_mode == TradingMode.PAPER else "⚠️  实盘交易模式"

    console.print()
    console.print(Panel(
        f"[bold {mode_color}]{mode_text}[/bold {mode_color}]\n\n"
        f"交易对: {', '.join(symbols)}\n"
        f"K线周期: {interval}\n"
        f"执行交易: {'是' if execute else '否 (仅打印)'}\n"
        f"线程架构: Macro + OnBar + Event",
        title="[bold cyan]🤖 Vibe Trading - 三线程架构[/bold cyan]",
        border_style="cyan",
    ))

    if trading_mode == TradingMode.LIVE and not execute:
        console.print("[yellow]⚠️  警告: 实盘模式但未启用--execute，订单将被打印但不会真正执行[/yellow]")

    console.print()

    # 使用第一个symbol作为主symbol (可扩展为多symbol支持)
    primary_symbol = symbols[0]

    if len(symbols) > 1:
        warning(f"多交易对模式: 使用 {primary_symbol} 作为主symbol，其他symbol暂不支持", tag="INFO")

    # 运行三线程系统
    asyncio.run(run_multi_thread_system(
        symbol=primary_symbol,
        interval=interval,
        mode=trading_mode,
        execute_trades=execute,
        save_logs=save_logs,
    ))


async def run_multi_thread_system(
    symbol: str,
    interval: str,
    mode: TradingMode,
    execute_trades: bool,
    save_logs: bool = True,
) -> None:
    """
    运行三线程交易系统

    Args:
        symbol: 交易对符号
        interval: K线间隔
        mode: 交易模式
        execute_trades: 是否真正执行交易
    """
    info(f"启动三线程交易系统: {symbol} ({interval})", tag="START")
    separator("=", 60)

    # 配置文件日志
    log_file_path = None
    if save_logs:
        from pathlib import Path
        from datetime import datetime
        
        # 创建logs目录
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # 生成日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file_path = logs_dir / f"trading_{symbol}_{timestamp}.log"
        
        configure(log_level="INFO", json_output=False, log_file=str(log_file_path))
        info(f"日志将保存到: {log_file_path}", tag="LOG")
    else:
        configure(log_level="INFO", json_output=False)
        info("文件日志已禁用", tag="LOG")

    try:
        # 创建多线程系统
        system = MultiThreadedTradingSystem(
            symbol=symbol,
            interval=interval,
        )

        # 设置信号处理
        system.setup_signal_handlers()

        # 运行系统
        await system.run()

    except KeyboardInterrupt:
        info("收到键盘中断")
    except Exception as e:
        logger.error(f"系统错误: {e}", exc_info=True)
    finally:
        info("系统关闭完成")


@app.command()
def analyze(
    symbol: str = typer.Argument(..., help="交易对符号"),
    interval: str = typer.Option("30m", help="K线间隔"),
):
    """
    运行单次分析

    获取当前市场数据并执行一次完整的Agent决策流程
    """
    configure(log_level="INFO", json_output=False)

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

    table.add_row("架构", "三线程 (Macro + OnBar + Event)")
    table.add_row("交易模式", settings.trading_mode.value)
    table.add_row("交易对", ", ".join(settings.symbols))
    table.add_row("K线周期", settings.interval)
    table.add_row("数据库", settings.database_url)
    table.add_row("LLM模型", settings.llm_config_name)

    console.print(table)


@app.command()
def macro(
    symbol: str = typer.Argument("BTCUSDT", help="交易对符号"),
):
    """
    运行一次宏观分析

    执行宏观环境分析并存储结果
    """
    configure(log_level="INFO", json_output=False)

    async def run_macro_analysis():
        from vibe_trading.threads.macro_thread import MacroAnalysisThread

        info(f"运行宏观分析: {symbol}", tag="MACRO")

        macro_thread = MacroAnalysisThread(symbol=symbol)
        await macro_thread.initialize()

        result = await macro_thread.run_once()

        if result:
            success(f"宏观分析完成: {result.get('market_regime')}", tag="MACRO")
            console.print(Panel(
                f"[bold]趋势方向:[/bold] {result.get('trend_direction')}\n"
                f"[bold]市场状态:[/bold] {result.get('market_regime')}\n"
                f"[bold]整体情绪:[/bold] {result.get('overall_sentiment')}\n"
                f"[bold]信心分数:[/bold] {result.get('confidence', 0):.2f}",
                title=f"[bold cyan]宏观分析结果[/bold cyan]",
            ))
        else:
            warning("宏观分析失败", tag="MACRO")

    asyncio.run(run_macro_analysis())


@app.command()
def backtest(
    symbol: str = typer.Argument(..., help="交易对符号，如 BTCUSDT"),
    start: str = typer.Option(..., "--start", "-s", help="开始日期 (YYYY-MM-DD)"),
    end: str = typer.Option(..., "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    interval: str = typer.Option("30m", help="K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    llm_mode: str = typer.Option("simulated", "--llm-mode", help="LLM模式 (simulated/cached/real)"),
    initial_balance: float = typer.Option(10000.0, "--initial-balance", help="初始余额"),
    report_format: str = typer.Option("text", "--report-format", "-r", help="报告格式 (text/html/json)"),
):
    """
    运行回测

    示例:
        # 基本回测
        vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31"

        # 使用缓存模式
        vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --llm-mode cached

        # 生成HTML报告
        vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --report-format html
    """
    configure(log_level="INFO", json_output=False)

    from datetime import datetime
    from vibe_trading.backtest.engine import BacktestEngine
    from vibe_trading.backtest.models import BacktestConfig, LLMMode, ReportFormat

    # 解析日期
    try:
        start_time = datetime.strptime(start, "%Y-%m-%d")
        end_time = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        error(f"日期格式错误，请使用 YYYY-MM-DD 格式", tag="BACKTEST")
        raise typer.Exit(1)

    # 解析 LLM 模式
    try:
        llm_mode_enum = LLMMode(llm_mode)
    except ValueError:
        error(f"无效的 LLM 模式: {llm_mode}，可选: simulated, cached, real", tag="BACKTEST")
        raise typer.Exit(1)

    # 解析报告格式
    report_formats = []
    for fmt in report_format.split(","):
        fmt = fmt.strip().upper()
        try:
            report_formats.append(ReportFormat(fmt))
        except ValueError:
            warning(f"忽略无效的报告格式: {fmt}", tag="BACKTEST")

    if not report_formats:
        report_formats = [ReportFormat.TEXT]

    # 创建配置
    config = BacktestConfig(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        initial_balance=initial_balance,
        llm_mode=llm_mode_enum,
        report_formats=report_formats,
    )

    async def run_backtest():
        info(f"开始回测: {symbol} {interval} {start} ~ {end}", tag="BACKTEST")
        info(f"LLM模式: {llm_mode}", tag="BACKTEST")

        engine = BacktestEngine(config)
        result = await engine.run_backtest()

        if result.error_message:
            error(f"回测失败: {result.error_message}", tag="BACKTEST")
            raise typer.Exit(1)

        success(f"回测完成! 耗时: {result.execution_time:.2f}秒", tag="BACKTEST")

        # 打印关键指标
        if result.metrics:
            console.print(Panel(
                f"[bold]总收益率:[/bold] {result.metrics.total_return:.2%}\n"
                f"[bold]夏普比率:[/bold] {result.metrics.sharpe_ratio:.2f}\n"
                f"[bold]最大回撤:[/bold] {result.metrics.max_drawdown:.2%}\n"
                f"[bold]胜率:[/bold] {result.metrics.win_rate:.2%}\n"
                f"[bold]总交易:[/bold] {result.metrics.total_trades}",
                title=f"[bold cyan]回测结果[/bold cyan]",
            ))

    asyncio.run(run_backtest())


if __name__ == "__main__":
    app()
