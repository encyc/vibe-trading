#!/usr/bin/env python
"""
Vibe Trading 全面功能测试

测试各个模块的功能是否正常工作。
"""
import asyncio
import sys
import os

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


async def test_settings():
    """测试配置模块"""
    console.print(Panel("[bold cyan]1. 测试配置模块[/bold cyan]"))

    from vibe_trading.config.settings import get_settings
    settings = get_settings()

    console.print(f"  ✓ Trading Mode: {settings.trading_mode.value}")
    console.print(f"  ✓ Symbols: {settings.symbols}")
    console.print(f"  ✓ Interval: {settings.interval}")
    console.print(f"  ✓ LLM Config: {settings.llm_config_name}")
    console.print(f"  ✓ Max Position: {settings.max_position_size} USDT")
    console.print(f"  ✓ Stop Loss: {settings.stop_loss_pct * 100}%")
    console.print()
    return True


async def test_llm_config():
    """测试 LLM 配置"""
    console.print(Panel("[bold cyan]2. 测试 LLM 配置[/bold cyan]"))

    from pi_ai.config import get_llm_config

    llm_cfg = get_llm_config()
    console.print(f"  ✓ Config loaded from: {llm_cfg._config_path}")
    console.print(f"  ✓ Current config: {llm_cfg.get_current_name()}")

    # 列出所有可用配置
    configs = llm_cfg.list_configs()
    console.print(f"  ✓ Available configs: {list(configs.keys())[:5]}... (showing 5 of {len(configs)})")

    # 获取模型
    model = llm_cfg.get_model()
    console.print(f"  ✓ Model: {model.id}")
    console.print(f"  ✓ Provider: {model.provider}")
    console.print(f"  ✓ Base URL: {model.base_url}")
    console.print()
    return True


async def test_memory_system():
    """测试记忆系统"""
    console.print(Panel("[bold cyan]3. 测试 BM25 记忆系统[/bold cyan]"))

    from vibe_trading.memory.memory import BM25Memory

    memory = BM25Memory()

    # 添加测试记忆
    memory.add_memory(
        "BTC broke $50000 resistance with high volume",
        "LONG BTC, target 52000, stop 49000",
        "outcome", 0.05
    )

    memory.add_memory(
        "ETH faced rejection at 3000",
        "Wait for confirmation, potential short at 2950",
        "outcome", -0.02
    )

    console.print(f"  ✓ Memory entries: {memory.size()}")

    # 测试检索
    results = memory.retrieve_relevant("BTC resistance breakthrough", top_k=2)
    console.print(f"  ✓ Retrieved {len(results)} memories for 'BTC resistance breakthrough'")

    for i, r in enumerate(results, 1):
        preview = r[:60] + "..." if len(r) > 60 else r
        console.print(f"    {i}. {preview}")

    console.print()
    return True


async def test_technical_indicators():
    """测试技术指标"""
    console.print(Panel("[bold cyan]4. 测试技术指标计算[/bold cyan]"))

    from vibe_trading.data_sources.technical_indicators import TechnicalIndicators

    # 模拟数据
    import numpy as np
    np.random.seed(42)

    opens = [50000 + i * 100 + np.random.randn() * 200 for i in range(100)]
    highs = [o + 50 + np.random.rand() * 100 for o in opens]
    lows = [o - 50 - np.random.rand() * 100 for o in opens]
    closes = [o + np.random.randn() * 50 for o in opens]
    volumes = [1000 + np.random.randint(-200, 200) for _ in range(100)]

    ti = TechnicalIndicators()
    ti.load_data(opens, highs, lows, closes, volumes)

    indicators = ti.get_latest_indicators()

    console.print(f"  ✓ SMA 20: {indicators.sma_20:.2f}")
    console.print(f"  ✓ RSI: {indicators.rsi:.2f}")
    console.print(f"  ✓ MACD: {indicators.macd:.4f}")
    console.print(f"  ✓ Bollinger Upper: {indicators.bollinger_upper:.2f}")
    console.print(f"  ✓ Bollinger Lower: {indicators.bollinger_lower:.2f}")

    # 测试趋势分析
    analysis = ti.get_trend_analysis()
    console.print(f"  ✓ Trend: {analysis['trend']}")
    console.print(f"  ✓ Signals: {len(analysis['signals'])}")
    console.print()
    return True


async def test_risk_manager():
    """测试风控模块"""
    console.print(Panel("[bold cyan]5. 测试风控模块[/bold cyan]"))

    from vibe_trading.execution.risk_manager import RiskManager

    rm = RiskManager()

    # 测试订单风险检查
    result = await rm.check_order_risk(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.001,
        price=50000,
        current_positions={"total_exposure": 0},
        current_balance=10000
    )

    console.print(f"  ✓ Order check: {result.result.value}")
    console.print(f"  ✓ Reason: {result.reason}")

    # 测试止损计算
    stop_loss = rm.calculate_stop_loss(50000, "LONG")
    console.print(f"  ✓ Stop Loss (LONG @ 50000): {stop_loss:.2f}")

    take_profit = rm.calculate_take_profit(50000, "LONG")
    console.print(f"  ✓ Take Profit (LONG @ 50000): {take_profit:.2f}")

    # 获取风险限制
    limits = rm.get_risk_limits()
    console.print(f"  ✓ Risk Limits: max_pos={limits['max_position_size']}, stop={limits['stop_loss_pct']}")
    console.print()
    return True


async def test_agent_initialization():
    """测试 Agent 初始化"""
    console.print(Panel("[bold cyan]6. 测试 Agent 初始化[/bold cyan]"))

    from vibe_trading.agents.analysts.technical_analyst import create_technical_analyst
    from vibe_trading.agents.agent_factory import ToolContext
    from vibe_trading.agents.researchers.researcher_agents import (
        BullResearcherAgent,
        BearResearcherAgent,
    )

    ctx = ToolContext(symbol="BTCUSDT", interval="30m")

    # 测试技术分析师
    analyst = await create_technical_analyst(ctx)
    console.print(f"  ✓ Technical Analyst initialized")
    console.print(f"    - System prompt: {len(analyst._agent.state.system_prompt)} chars")

    # 测试研究员
    bull = BullResearcherAgent()
    await bull.initialize(ctx)
    console.print(f"  ✓ Bull Researcher initialized")

    bear = BearResearcherAgent()
    await bear.initialize(ctx)
    console.print(f"  ✓ Bear Researcher initialized")

    console.print()
    return True


async def test_coordinator():
    """测试协调器初始化"""
    console.print(Panel("[bold cyan]7. 测试交易协调器[/bold cyan]"))

    from vibe_trading.coordinator.trading_coordinator import TradingCoordinator
    from vibe_trading.config.agent_config import AgentTeamConfig

    # 使用默认配置
    config = AgentTeamConfig()

    # 只启用分析师,禁用其他角色以简化测试
    config.bull_researcher.enabled = False
    config.bear_researcher.enabled = False
    config.research_manager.enabled = False
    config.aggressive_debator.enabled = False
    config.neutral_debator.enabled = False
    config.conservative_debator.enabled = False
    config.trader.enabled = False
    config.portfolio_manager.enabled = False

    coord = TradingCoordinator(
        symbol="BTCUSDT",
        interval="30m",
        memory=None,
        agent_config=config,
    )

    await coord.initialize()
    console.print(f"  ✓ TradingCoordinator initialized for BTCUSDT")
    console.print(f"  ✓ Enabled agents: {len([a for a in config.get_all_configs().values() if a.enabled])}")
    console.print()
    return True


async def test_database():
    """测试数据库模块"""
    console.print(Panel("[bold cyan]8. 测试数据库模块[/bold cyan]"))

    from vibe_trading.data_sources.kline_storage import KlineStorage
    from vibe_trading.data_sources.binance_client import Kline

    # 使用临时数据库
    storage = KlineStorage(database_url="sqlite+aiosqlite:///./test_vibe_trading.db")
    await storage.init()
    console.print(f"  ✓ Database initialized")

    # 添加测试数据
    test_kline = Kline(
        symbol="BTCUSDT",
        interval="30m",
        open_time=1700000000000,
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=1000.0,
        close_time=1700000029999,
        quote_volume=50000000.0,
        trades=5000,
        taker_buy_base=500.0,
        taker_buy_quote=25000000.0,
        is_final=True,
    )

    await storage.store_kline(test_kline)
    console.print(f"  ✓ Test kline stored")

    # 查询数据
    from vibe_trading.data_sources.kline_storage import KlineQuery
    query = KlineQuery(symbol="BTCUSDT", interval="30m", limit=1)
    klines = await storage.query_klines(query)
    console.print(f"  ✓ Retrieved {len(klines)} kline(s)")

    await storage.close()

    # 清理测试数据库
    import os
    try:
        os.remove("./test_vibe_trading.db")
        console.print(f"  ✓ Test database cleaned up")
    except:
        pass

    console.print()
    return True


async def main():
    """运行所有测试"""
    console.print()
    console.print(Panel("[bold yellow]🚀 Vibe Trading 功能测试[/bold yellow]", padding=(1, 1)))
    console.print()

    tests = [
        ("配置模块", test_settings),
        ("LLM 配置", test_llm_config),
        ("记忆系统", test_memory_system),
        ("技术指标", test_technical_indicators),
        ("风控模块", test_risk_manager),
        ("Agent 初始化", test_agent_initialization),
        ("协调器", test_coordinator),
        ("数据库", test_database),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            console.print(f"  ✗ {name} 失败: {e}")
            results.append((name, False))

    # 汇总结果
    console.print()
    console.print(Panel("[bold yellow]📊 测试结果汇总[/bold yellow]", padding=(1, 1)))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("模块", style="dim")
    table.add_column("状态", justify="center")
    table.add_column("说明", justify="left")

    passed = 0
    for name, result in results:
        if result:
            table.add_row(name, "[green]✓ PASS[/green]", "功能正常")
            passed += 1
        else:
            table.add_row(name, "[red]✗ FAIL[/red]", "需要修复")

    console.print(table)
    console.print()
    console.print(f"[bold]总计: {passed}/{len(results)} 测试通过[/bold]")

    if passed == len(results):
        console.print("[green]✅ 所有测试通过！系统已准备就绪。[/green]")
    else:
        console.print("[yellow]⚠️  部分测试失败，请检查相关模块。[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
