"""
Vibe Trading - 主入口

支持实盘和纸面交易模式，使用三线程架构:
1. Macro Judgment Thread - 每小时分析宏观环境
2. Main Trading Thread - K线触发决策流程
3. Event-Driven Thread - 监控紧急事件
"""
import asyncio
from enum import Enum
from typing import List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pi_logger import get_logger, configure, info, success, warning, error, separator

from vibe_trading.config.settings import get_settings
from vibe_trading.main.multi_thread_main import MultiThreadedTradingSystem
from vibe_trading.data_sources.kline_storage import KlineStorage
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator

# Prime Agent导入
from vibe_trading.prime import PrimeAgent, PrimeAgentConfig, PrimeConfig, HarnessConfig

# 初始化
app = typer.Typer(help="Vibe Trading - AI驱动的量化交易系统")
console = Console()
logger = get_logger("main")


class TradingMode(str, Enum):
    """交易模式"""
    PAPER = "paper"  # 纸面交易
    LIVE = "live"    # 实盘交易


async def run_web_server(port: int = 8000, symbol: str = "BTCUSDT", interval: str = "30m") -> None:
    """
    在后台运行 Web 服务器

    Args:
        port: Web 服务器端口
        symbol: 交易对符号
        interval: K线周期
    """
    import uvicorn
    from vibe_trading.web.server import app, set_initial_config

    # 在启动前设置配置
    set_initial_config(symbol, interval)

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    except asyncio.CancelledError:
        info("Web 服务器已停止", tag="WEB")
    except Exception as e:
        logger.error(f"Web 服务器错误: {e}", exc_info=True)


@app.command()
def start(
    symbols: List[str] = typer.Argument(..., help="交易对符号，如 BTCUSDT ETHUSDT"),
    interval: str = typer.Option("30m", help="K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    mode: str = typer.Option("paper", help="交易模式: paper (纸面) 或 live (实盘)"),
    execute: bool = typer.Option(False, help="--execute: 实盘模式下真正执行订单"),
    log_level: str = typer.Option("INFO", help="日志级别: DEBUG, INFO, WARNING, ERROR"),
    save_logs: bool = typer.Option(True, help="--save-logs/--no-save-logs: 是否保存日志到文件 (默认保存到 logs/ 目录)"),
    web: bool = typer.Option(False, help="--web: 启动 Web 监控界面 (默认端口 8000)"),
    web_port: int = typer.Option(8000, help="--web-port: Web 监控界面端口"),
):
    """
    启动三线程交易系统

    使用三线程架构:
    - Macro Thread: 每小时分析宏观环境
    - On Bar Thread: K线触发决策流程
    - Event Thread: 监控紧急事件并触发应急流程

    示例:
        # 纸面交易
        vibe-trade start BTCUSDT

        # 实盘交易 (仅打印订单)
        vibe-trade start BTCUSDT --mode live

        # 实盘交易 (真正执行)
        vibe-trade start BTCUSDT --mode live --execute

        # 启动 Web 监控界面
        vibe-trade start BTCUSDT --web

        # 多交易对 (使用第一个作为主symbol)
        vibe-trade start BTCUSDT ETHUSDT SOLUSDT
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

    web_status = f"✅ 启用 (http://localhost:{web_port})" if web else "❌ 未启用"

    console.print()
    console.print(Panel(
        f"[bold {mode_color}]{mode_text}[/bold {mode_color}]\n\n"
        f"交易对: {', '.join(symbols)}\n"
        f"K线周期: {interval}\n"
        f"执行交易: {'是' if execute else '否 (仅打印)'}\n"
        f"Web 监控: {web_status}\n"
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
        enable_web=web,
        web_port=web_port,
    ))


async def run_multi_thread_system(
    symbol: str,
    interval: str,
    mode: TradingMode,
    execute_trades: bool,
    save_logs: bool = True,
    enable_web: bool = False,
    web_port: int = 8000,
) -> None:
    """
    运行三线程交易系统

    Args:
        symbol: 交易对符号
        interval: K线间隔
        mode: 交易模式
        execute_trades: 是否真正执行交易
        save_logs: 是否保存日志
        enable_web: 是否启动 Web 监控界面
        web_port: Web 服务器端口
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

    # Web 服务器任务
    web_server_task = None

    try:
        # 创建多线程系统
        system = MultiThreadedTradingSystem(
            symbol=symbol,
            interval=interval,
        )

        # 设置信号处理
        system.setup_signal_handlers()

        # 启动 Web 服务器（如果启用）
        if enable_web:
            info(f"启动 Web 监控界面: http://localhost:{web_port}", tag="WEB")
            web_server_task = asyncio.create_task(run_web_server(web_port, symbol, interval))

        # 运行系统
        await system.run()

    except KeyboardInterrupt:
        info("收到键盘中断")
    except Exception as e:
        logger.error(f"系统错误: {e}", exc_info=True)
    finally:
        # 停止 Web 服务器
        if web_server_task:
            info("正在关闭 Web 服务器...", tag="WEB")
            web_server_task.cancel()
            try:
                await web_server_task
            except asyncio.CancelledError:
                pass

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
        price_result = await get_current_price(symbol)
        current_price = float(price_result.get("price", 0)) if price_result else 0.0

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
def prime(
    symbols: List[str] = typer.Argument(..., help="交易对符号，如 BTCUSDT ETHUSDT"),
    interval: str = typer.Option("30m", help="K线间隔 (1m, 5m, 15m, 30m, 1h, 4h, 1d)"),
    mode: str = typer.Option("paper", help="交易模式: paper (纸面) 或 live (实盘)"),
    execute: bool = typer.Option(False, help="--execute: 实盘模式下真正执行订单"),
    log_level: str = typer.Option("INFO", help="日志级别: DEBUG, INFO, WARNING, ERROR"),
    save_logs: bool = typer.Option(True, help="--save-logs/--no-save-logs: 是否保存日志到文件"),
    web: bool = typer.Option(False, help="--web: 启动 Web 监控界面 (默认端口 8000)"),
    web_port: int = typer.Option(8000, help="--web-port: Web 监控界面端口"),
):
    """
    启动Prime Agent监控模式（基于pi_agent_core的新架构）

    Prime Agent作为系统监控者和紧急仲裁者：
    - 运行三线程交易系统（Macro + OnBar + Event）
    - 监控系统健康状态（资金、仓位、风险）
    - 检测紧急情况（价格暴跌、风险超标）
    - 紧急情况下可覆盖决策或直接调用Subagent

    正常情况：Subagents按5阶段流程协作工作
    紧急情况：Prime Agent介入并采取保护措施

    示例:
        # 纸面交易
        vibe-trade prime BTCUSDT

        # 实盘交易 (仅打印订单)
        vibe-trade prime BTCUSDT --mode live

        # 实盘交易 (真正执行)
        vibe-trade prime BTCUSDT --mode live --execute

        # 启动 Web 监控界面
        vibe-trade prime BTCUSDT --web
    """
    # 配置日志
    configure(log_level=log_level, json_output=False, enable_file_logging=save_logs)

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
    mode_text = "📝 纸面交易模式" if trading_mode == TradingMode.PAPER else "⚠️ 实盘交易模式"

    web_status = f"✅ 启用 (http://localhost:{web_port})" if web else "❌ 未启用"

    console.print()
    console.print(Panel(
        f"[bold {mode_color}]{mode_text}[/bold {mode_color}]\n\n"
        f"交易对: {', '.join(symbols)}\n"
        f"K线周期: {interval}\n"
        f"执行交易: {'是' if execute else '否 (仅打印)'}\n"
        f"Web 监控: {web_status}\n"
        f"架构: 三线程系统 + Prime Agent监控层",
        title="[bold magenta]🤖 Vibe Trading - Prime Agent监控模式[/bold magenta]",
        border_style="magenta",
    ))

    console.print()
    info(f"启动Prime Agent系统: {symbols[0]} ({interval})", tag="START")
    separator("=", 60)

    # 运行Prime Agent系统
    asyncio.run(run_prime_system(
        symbols=symbols,
        interval=interval,
        mode=trading_mode,
        execute_trades=execute,
        save_logs=save_logs,
        enable_web=web,
        web_port=web_port,
    ))


async def run_prime_system(
    symbols: List[str],
    interval: str,
    mode: TradingMode,
    execute_trades: bool,
    save_logs: bool = True,
    enable_web: bool = False,
    web_port: int = 8000,
) -> None:
    """
    运行Prime Agent系统

    Args:
        symbols: 交易对列表
        interval: K线间隔
        mode: 交易模式
        execute_trades: 是否真正执行交易
        save_logs: 是否保存日志
        enable_web: 是否启动 Web 监控界面
        web_port: Web 服务器端口
    """
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
        log_file_path = logs_dir / f"prime_{symbols[0]}_{timestamp}.log"

        configure(log_level="INFO", json_output=False, log_file=str(log_file_path))
        info(f"日志将保存到: {log_file_path}", tag="LOG")
    else:
        configure(log_level="INFO", json_output=False)
        info("文件日志已禁用", tag="LOG")

    # Web 服务器任务
    web_server_task = None

    try:
        # 创建Prime Agent配置
        prime_config = PrimeConfig(
            symbol=symbols[0],  # 主交易对
            interval=interval,  # K线间隔
            monitoring_interval=1.0,
            max_queue_size=1000,
            max_single_trade=1000.0 if mode == TradingMode.PAPER else 100.0,  # 纸面交易可以用更大金额
            max_total_position=0.3,
            enable_emergency_override=True,
            enabled_subagents=[
                "technical_analyst",
                "bull_researcher",
                "bear_researcher",
                "research_manager",
                "aggressive_risk_analyst",
                "neutral_risk_analyst",
                "conservative_risk_analyst",
                "trader",
                "portfolio_manager",
                "macro_analyst",
            ],
        )

        harness_config = HarnessConfig(
            enable_safety_constraint=True,
            enable_operational_constraint=True,
            enable_behavioral_constraint=True,
            enable_resource_constraint=True,
        )

        config = PrimeAgentConfig(
            system_prompt=f"""你是Prime Agent，负责监控系统健康状态并在紧急情况下保护资金安全。

当前配置：
- 交易对: {symbols[0]}
- K线周期: {interval}
- 交易模式: {mode.value}

你的职责：
1. 监控系统健康状态（资金、仓位、风险指标）
2. 检测紧急情况（价格暴跌、风险超标）
3. 紧急情况下采取保护措施（平仓、减仓）
4. 正常情况下不干预三线程系统的运行

请始终以系统安全和风险控制为首要目标。""",
            prime_config=prime_config,
            harness_config=harness_config,
        )

        # 创建Prime Agent
        prime_agent = PrimeAgent(config)

        # 启动 Web 服务器（如果启用）
        if enable_web:
            info(f"启动 Web 监控界面: http://localhost:{web_port}", tag="WEB")
            web_server_task = asyncio.create_task(run_web_server(web_port))

        # 启动Prime Agent
        await prime_agent.start()

    except KeyboardInterrupt:
        info("收到键盘中断，正在关闭Prime Agent...")
    except Exception as e:
        logger.error(f"Prime Agent系统错误: {e}", exc_info=True)
    finally:
        # 停止 Web 服务器
        if web_server_task:
            info("正在关闭 Web 服务器...", tag="WEB")
            web_server_task.cancel()
            try:
                await web_server_task
            except asyncio.CancelledError:
                pass

        info("Prime Agent系统关闭完成")


@app.command()
def status():
    """显示系统状态"""
    settings = get_settings()

    table = Table(title="Vibe Trading 系统状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")

    table.add_row("可用架构", "三线程 (Macro + OnBar + Event), Prime Agent (pi_agent_core)")
    table.add_row("交易模式", settings.trading_mode.value)
    table.add_row("交易对", ", ".join(settings.symbols))
    table.add_row("K线周期", settings.interval)
    table.add_row("数据库", settings.database_url)
    table.add_row("LLM模型", settings.llm_config_name)
    table.add_row("Subagent数量", "10个可用 (3个待实现)")

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
