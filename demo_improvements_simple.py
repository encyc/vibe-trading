#!/usr/bin/env python3
"""
系统改进功能简化演示

只展示8项改进功能，不进行实际交易分析
"""
import asyncio
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.coordinator.state_machine import DecisionStateMachine, DecisionState
from vibe_trading.agents.messaging import create_analysis_report, get_message_broker
from vibe_trading.coordinator.parallel_executor import ParallelExecutor
from vibe_trading.config.logging_config import configure_logging, get_logger, PerformanceLogger
from vibe_trading.data_sources.rate_limiter import get_multi_endpoint_limiter
from vibe_trading.web.visualizer import visualize_decision_history, OutputFormat
from vibe_trading.data_sources.cache import get_global_cache, cached
from vibe_trading.agents.token_optimizer import get_token_optimizer

console = Console()


async def demo_all_improvements():
    """演示所有8项改进功能"""

    # 配置日志
    configure_logging(log_level="INFO", json_output=False, enable_file_logging=False)
    logger = get_logger("demo")

    console.print()
    console.print(Panel(
        "[bold yellow]🚀 Vibe Trading 系统改进功能演示[/bold yellow]",
        padding=(1, 1),
    ))

    # ========================================================================
    # 1. 状态机管理
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]1️⃣ 状态机管理[/bold cyan]",
        title="决策流程状态追踪",
        border_style="cyan",
        padding=(1, 1),
    ))

    machine = DecisionStateMachine(
        decision_id="demo_001",
        symbol="BTCUSDT",
        interval="1m"
    )

    # 状态转换
    states = [
        (DecisionState.ANALYZING, "开始分析师阶段"),
        (DecisionState.DEBATING, "开始研究员辩论"),
        (DecisionState.ASSESSING_RISK, "开始风控评估"),
        (DecisionState.PLANNING, "开始执行规划"),
    ]

    for i, (state, desc) in enumerate(states, 1):
        machine.transition_to(state, desc)
        console.print(f"  [{i}/4] {desc}")

    machine.complete({"action": "HOLD", "reason": "演示完成"})

    summary = machine.get_state_summary()
    console.print(f"\n  ✅ 状态转换: {len(summary['state_history'])}次")
    console.print(f"  ✅ 当前阶段: {summary['current_phase']}")

    # ========================================================================
    # 2. Agent消息标准化
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]2️⃣ Agent消息标准化[/bold cyan]",
        title="结构化Agent通信",
        border_style="cyan",
        padding=(1, 1),
    ))

    report = create_analysis_report(
        sender="TechnicalAnalyst",
        correlation_id="demo_001",
        analysis_type="technical",
        report={"trend": "up", "rsi": 58, "signal": "bullish"},
    )

    console.print(f"  📤 发送者: {report.sender}")
    console.print(f"  📨 类型: {report.message_type.value}")
    console.print(f"  📝 内容: {report.content}")

    broker = get_message_broker()
    stats = broker.get_statistics()
    console.print(f"\n  📊 消息统计: {stats['total_messages']}条")

    # ========================================================================
    # 3. 并行执行优化
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]3️⃣ 并行执行优化[/bold cyan]",
        title="性能提升展示",
        border_style="cyan",
        padding=(1, 1),
    ))

    import time

    # 模拟Agent
    class MockAgent:
        def __init__(self, name, delay):
            self.name = name
            self.delay = delay

        async def analyze(self, context):
            await asyncio.sleep(self.delay)
            return f"{self.name} result"

    agents = [
        MockAgent("TechnicalAnalyst", 0.1),
        MockAgent("FundamentalAnalyst", 0.1),
        MockAgent("SentimentAnalyst", 0.1),
    ]

    executor = ParallelExecutor()

    # 并行执行
    start = time.time()
    summary = await executor.run_phase_1_analysts(
        analysts=agents,
        context={"symbol": "BTCUSDT"},
        timeout_per_agent=5.0,
    )
    total_time = time.time() - start

    console.print(f"  ✅ 总耗时: {total_time:.2f}秒")
    console.print(f"  ✅ 加速比: {summary.parallel_speedup:.1f}x")
    console.print(f"  ✅ 成功: {summary.successful}/{summary.total_agents}")

    # ========================================================================
    # 4. 结构化日志
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]4️⃣ 结构化日志[/bold cyan]",
        title="结构化日志输出",
        border_style="cyan",
        padding=(1, 1),
    ))

    logger.info("这是一条信息日志", symbol="BTCUSDT", price=50000)
    logger.warning("这是一条警告日志", metric="RSI", value=68)

    console.print("  ✅ 日志已输出（结构化格式）")

    with PerformanceLogger("演示操作"):
        await asyncio.sleep(0.01)

    console.print("  ✅ 性能日志: 操作耗时已记录")

    # ========================================================================
    # 5. API限流管理
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]5️⃣ API限流管理[/bold cyan]",
        title="令牌桶算法",
        border_style="cyan",
        padding=(1, 1),
    ))

    limiter = get_multi_endpoint_limiter().get_limiter("binance_rest")

    for i in range(3):
        await limiter.acquire(tokens=1)
        remaining = limiter.get_remaining_tokens()["minute"]
        console.print(f"  📊 请求 {i+1}: 剩余令牌 {remaining}")

    stats = limiter.get_stats()
    console.print(f"\n  📈 总请求数: {stats.get('total_requests', 0)}")

    # ========================================================================
    # 6. 决策树可视化
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]6️⃣ 决策树可视化[/bold cyan]",
        title="流程图生成",
        border_style="cyan",
        padding=(1, 1),
    ))

    # 创建简单的决策历史
    decision_history = [
        {"phase": "ANALYZING", "agents": ["TechnicalAnalyst", "FundamentalAnalyst"]},
        {"phase": "DEBATING", "agents": ["BullResearcher", "BearResearcher"]},
        {"phase": "DECIDED", "decision": "HOLD"},
    ]

    ascii_viz = visualize_decision_history(decision_history, OutputFormat.ASCII)
    console.print(ascii_viz)

    # ========================================================================
    # 7. 缓存机制
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]7️⃣ 缓存机制[/bold cyan]",
        title="性能加速展示",
        border_style="cyan",
        padding=(1, 1),
    ))

    cache = get_global_cache()

    @cached(ttl=60, key_prefix="demo")
    async def expensive_operation(x: int, y: int) -> int:
        await asyncio.sleep(0.05)
        return x + y

    # 第一次调用
    start = time.time()
    result1 = await expensive_operation(1, 2)
    time1 = time.time() - start

    # 第二次调用（从缓存）
    start = time.time()
    result2 = await expensive_operation(1, 2)
    time2 = time.time() - start

    console.print(f"  📊 第一次调用: {time1*1000:.1f}ms")
    console.print(f"  📊 第二次调用: {time2*1000:.1f}ms (缓存)")
    console.print(f"  📈 加速比: {time1/time2:.1f}x")

    # ========================================================================
    # 8. Token使用优化
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold cyan]8️⃣ Token使用优化[/bold cyan]",
        title="成本控制展示",
        border_style="cyan",
        padding=(1, 1),
    ))

    optimizer = get_token_optimizer()

    long_prompt = """
# 技术分析报告

## 市场概况
- 当前价格: $50,000
- 24小时变化: +5.2%

## 技术指标
### RSI
- 当前值: 58
- 状态: 中性偏多
""" * 3

    compressed = optimizer.compress_prompt(long_prompt)
    ratio = len(compressed) / len(long_prompt)

    console.print(f"  📝 原始长度: {len(long_prompt)} 字符")
    console.print(f"  📝 压缩后: {len(compressed)} 字符")
    console.print(f"  📉 压缩比例: {ratio:.1%}")

    tokens = optimizer.estimate_tokens(compressed)
    console.print(f"  🔢 估算Token: ~{tokens} tokens")

    # ========================================================================
    # 总结
    # ========================================================================
    console.print()
    console.print(Panel(
        "[bold green]✅ 所有8项改进功能演示完成[/bold green]",
        border_style="green",
        padding=(1, 1),
    ))

    console.print()
    console.print("[dim]这些改进功能已集成到交易系统中，可显著提升：[/dim]")
    console.print("  • 系统可靠性和可维护性")
    console.print("  • 决策流程的可追踪性")
    console.print("  • API调用的安全性")
    console.print("  • 整体性能和响应速度")


if __name__ == "__main__":
    asyncio.run(demo_all_improvements())
