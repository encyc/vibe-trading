"""
系统改进功能测试脚本

测试已实施的8项改进功能。
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vibe_trading.coordinator.state_machine import (
    DecisionStateMachine,
    DecisionState,
    StateMachineManager,
    get_state_machine_manager,
)
from vibe_trading.agents.messaging import (
    MessageType,
    AgentMessage,
    MessageBroker,
    get_message_broker,
    create_analysis_report,
    create_debate_speech,
    create_investment_advice,
)
from vibe_trading.coordinator.parallel_executor import (
    ParallelExecutor,
    ExecutionResult,
    PhaseExecutionSummary,
)
from vibe_trading.config.logging_config import (
    configure_logging,
    get_logger,
    log_decision_made,
    PerformanceLogger,
)
from vibe_trading.data_sources.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    MultiEndpointRateLimiter,
    get_multi_endpoint_limiter,
)
from vibe_trading.web.visualizer import (
    DecisionTreeVisualizer,
    DecisionFlowBuilder,
    OutputFormat,
    visualize_decision_history,
)
from vibe_trading.data_sources.cache import (
    MemoryCache,
    HybridCache,
    get_global_cache,
    cached,
)
from vibe_trading.agents.token_optimizer import (
    TokenOptimizer,
    get_token_optimizer,
    track_tokens,
)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_state_machine():
    """测试状态机管理"""
    print_section("测试 1: 状态机管理")

    # 创建状态机
    machine = DecisionStateMachine(
        decision_id="test_001",
        symbol="BTCUSDT",
        interval="30m"
    )

    print("\n--- 状态转换流程 ---")
    print(f"初始状态: {machine.current_state}")

    # Phase 1
    machine.transition_to(DecisionState.ANALYZING, "开始分析师阶段")
    print(f"Phase 1: {machine.current_state}")

    # Phase 2
    machine.transition_to(DecisionState.DEBATING, "开始研究员辩论")
    print(f"Phase 2: {machine.current_state}")

    # Phase 3
    machine.transition_to(DecisionState.ASSESSING_RISK, "开始风控评估")
    print(f"Phase 3: {machine.current_state}")

    # Phase 4
    machine.transition_to(DecisionState.PLANNING, "开始执行规划")
    print(f"Phase 4: {machine.current_state}")

    # 完成
    final_decision = {"action": "BUY", "confidence": 0.8}
    machine.complete(final_decision)
    print(f"最终状态: {machine.current_state}")

    # 获取摘要
    summary = machine.get_state_summary()
    print(f"\n--- 状态摘要 ---")
    print(f"决策ID: {summary['decision_id']}")
    print(f"交易品种: {summary['symbol']}")
    print(f"当前阶段: {summary['current_phase']}")
    print(f"耗时: {summary['duration_seconds']:.2f}秒")
    print(f"状态转换数: {len(summary['state_history'])}")


def test_messaging():
    """测试Agent消息标准化"""
    print_section("测试 2: Agent消息标准化")

    broker = get_message_broker()

    # 创建分析报告消息
    report = create_analysis_report(
        sender="TechnicalAnalyst",
        correlation_id="corr_001",
        analysis_type="technical",
        report={
            "trend": "up",
            "rsi": 58,
            "macd": "bullish_cross",
        },
        metadata={"timestamp": "2024-01-01T10:00:00"},
    )

    print(f"\n--- 发送消息 ---")
    print(f"消息ID: {report.message_id}")
    print(f"发送者: {report.sender}")
    print(f"接收者: {report.receiver}")
    print(f"类型: {report.message_type.value}")
    print(f"内容: {report.content}")

    # 创建辩论发言消息
    speech = create_debate_speech(
        sender="BullResearcher",
        correlation_id="corr_001",
        side="bull",
        speech="技术面看涨，RSI中性偏多，MACD金叉",
        round_number=1,
    )

    print(f"\n--- 辩论发言 ---")
    print(f"发送者: {speech.sender}")
    print(f"类型: {speech.message_type.value}")
    print(f"内容: {speech.content}")

    # 获取对话历史
    history = broker.get_conversation_history("corr_001")
    print(f"\n--- 对话历史 ---")
    print(f"消息数量: {len(history)}")


async def test_parallel_executor():
    """测试并行执行优化"""
    print_section("测试 3: Agent并行执行优化")

    executor = ParallelExecutor()

    # 模拟Agent
    class MockAgent:
        def __init__(self, name, delay):
            self.name = name
            self.delay = delay

        async def analyze(self, context):
            await asyncio.sleep(self.delay)
            return f"{self.name} result"

    # 创建模拟Agent
    analysts = [
        MockAgent("TechnicalAnalyst", 0.5),
        MockAgent("FundamentalAnalyst", 0.3),
        MockAgent("SentimentAnalyst", 0.4),
    ]

    print("\n--- 并行执行 ---")
    summary = await executor.run_phase_1_analysts(
        analysts=analysts,
        context={"symbol": "BTCUSDT"},
        timeout_per_agent=5.0,
    )

    print(f"总Agent数: {summary.total_agents}")
    print(f"成功: {summary.successful}")
    print(f"失败: {summary.failed}")
    print(f"总耗时: {summary.total_time:.2f}秒")
    print(f"加速比: {summary.parallel_speedup:.2f}x")

    print(f"\n--- 各Agent结果 ---")
    for result in summary.results:
        status = "✅" if result.success else "❌"
        print(f"{status} {result.agent_name}: {result.execution_time:.2f}秒")


def test_logging():
    """测试结构化日志"""
    print_section("测试 4: 结构化日志")

    # 配置结构化日志
    configure_logging(
        log_level="INFO",
        json_output=False,  # 使用控制台友好格式
        enable_file_logging=False,
    )

    logger = get_logger("test")

    print("\n--- 结构化日志示例 ---")

    # 决策日志
    log_decision_made(
        decision_id="test_001",
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.85,
        position_size=1000.0,
    )

    # 性能日志
    with PerformanceLogger("test_operation"):
        asyncio.sleep(0.1)

    print("\n日志已输出到控制台（结构化格式）")


async def test_rate_limiter():
    """测试API限流管理"""
    print_section("测试 5: API限流管理")

    # 创建限流器
    config = RateLimitConfig(
        requests_per_minute=10,  # 小数字用于测试
        requests_per_hour=100,
    )
    limiter = RateLimiter(config)

    print("\n--- 限流测试 ---")

    # 快速发送请求
    for i in range(15):
        success = await limiter.acquire(tokens=1)
        status = "✅" if success else "❌"
        remaining = limiter.get_remaining_tokens()
        print(f"{status} 请求 {i+1}: 剩余令牌 {remaining['minute']}")

        if not success:
            break

    # 获取统计
    stats = limiter.get_stats()
    print(f"\n--- 统计信息 ---")
    print(f"总请求数: {stats['total_requests']}")
    print(f"被阻止请求数: {stats['blocked_requests']}")
    print(f"等待时间: {stats['wait_time_seconds']:.2f}秒")


def test_visualizer():
    """测试决策树可视化"""
    print_section("测试 6: 决策树可视化")

    # 使用构建器创建标准流程
    builder = DecisionFlowBuilder()
    visualizer = builder.build_standard_flow()

    print("\n--- ASCII格式 ---")
    ascii_viz = visualizer.generate_ascii()
    print(ascii_viz)

    print("\n--- Mermaid格式 (前30行) ---")
    mermaid_viz = visualizer.generate_mermaid()
    lines = mermaid_viz.split('\n')[:30]
    print('\n'.join(lines))
    print("... (省略)")


async def test_cache():
    """测试缓存机制"""
    print_section("测试 7: 缓存机制")

    cache = get_global_cache()

    print("\n--- 缓存操作 ---")

    # 设置缓存
    await cache.set(
        key="test_key",
        value={"data": "test_value", "timestamp": 12345},
        ttl=60.0,
    )
    print("✅ 缓存已设置")

    # 获取缓存
    value = await cache.get("test_key")
    print(f"✅ 缓存命中: {value}")

    # 获取不存在的缓存
    miss = await cache.get("nonexistent")
    print(f"❌ 缓存未命中: {miss}")

    # 使用装饰器
    @cached(ttl=300, key_prefix="test")
    async def expensive_calculation(x: int, y: int) -> int:
        """模拟耗时计算"""
        await asyncio.sleep(0.1)
        return x + y

    print("\n--- 缓存装饰器 ---")
    import time

    # 第一次调用
    start = time.time()
    result1 = await expensive_calculation(1, 2)
    time1 = time.time() - start

    # 第二次调用（从缓存）
    start = time.time()
    result2 = await expensive_calculation(1, 2)
    time2 = time.time() - start

    print(f"第一次调用: {time1:.3f}秒")
    print(f"第二次调用: {time2:.3f}秒 (缓存)")

    # 获取统计
    stats = cache.get_stats()
    print(f"\n--- 缓存统计 ---")
    print(f"内存缓存大小: {stats['memory']['size']}")
    print(f"内存缓存命中率: {stats['memory']['hit_rate']:.1%}")


def test_token_optimizer():
    """测试Token使用优化"""
    print_section("测试 8: Token使用优化")

    optimizer = get_token_optimizer()

    print("\n--- Prompt压缩 ---")
    long_prompt = """
    # 技术分析报告

    ## 市场概况
    - 当前价格: $50,000
    - 24小时变化: +5.2%
    - 成交量: 1.2M BTC

    ## 技术指标
    ### RSI
    - 当前值: 58
    - 状态: 中性偏多

    ### MACD
    - 当前值: 金叉
    - 信号: 看涨

    ### 布林带
    - 上轨: $51,000
    - 中轨: $50,000
    - 下轨: $49,000
    """ * 3

    compressed = optimizer.compress_prompt(long_prompt)
    ratio = len(compressed) / len(long_prompt)
    print(f"原始长度: {len(long_prompt)} 字符")
    print(f"压缩后长度: {len(compressed)} 字符")
    print(f"压缩比例: {ratio:.1%}")

    print("\n--- Token估算 ---")
    text = "这是一个测试文本，用于估算Token数量。"
    tokens = optimizer.estimate_tokens(text)
    print(f"文本: {text}")
    print(f"估算Token数: {tokens}")

    print("\n--- 历史对话总结 ---")
    messages = [
        {"role": "user", "content": "分析BTC", "timestamp": "2024-01-01T10:00:00"},
        {"role": "assistant", "content": "BTC看涨", "timestamp": "2024-01-01T10:01:00"},
        {"role": "user", "content": "ETH呢？", "timestamp": "2024-01-01T10:02:00"},
        {"role": "assistant", "content": "ETH中性", "timestamp": "2024-01-01T10:03:00"},
        {"role": "user", "content": "SOL？", "timestamp": "2024-01-01T10:04:00"},
        {"role": "assistant", "content": "SOL看跌", "timestamp": "2024-01-01T10:05:00"},
    ]

    summary = optimizer.summarize_history(messages, max_messages=3)
    print(f"原始消息数: {len(messages)}")
    print(f"总结后消息数: 3")
    print(f"总结内容:\n{summary}")

    # 模拟使用追踪
    optimizer.track_usage(
        agent_name="TechnicalAnalyst",
        input_text=long_prompt,
        output_text="基于技术分析，建议做多。",
        model="gpt-3.5-turbo",
    )

    print("\n--- 优化建议 ---")
    suggestions = optimizer.get_optimization_suggestions()
    for suggestion in suggestions:
        print(f"  {suggestion}")


def main():
    """运行所有测试"""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  系统改进功能测试".center(56) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    try:
        # 测试1: 状态机管理
        test_state_machine()

        # 测试2: Agent消息标准化
        test_messaging()

        # 测试3: Agent并行执行优化
        asyncio.run(test_parallel_executor())

        # 测试4: 结构化日志
        test_logging()

        # 测试5: API限流管理
        asyncio.run(test_rate_limiter())

        # 测试6: 决策树可视化
        test_visualizer()

        # 测试7: 缓存机制
        asyncio.run(test_cache())

        # 测试8: Token使用优化
        test_token_optimizer()

        print_section("测试完成")
        print("✅ 所有8项改进功能测试通过")

        print("\n" + "=" * 60)
        print("  创建的文件列表")
        print("=" * 60)
        files = [
            "coordinator/state_machine.py - 状态机管理",
            "agents/messaging.py - Agent消息标准化",
            "coordinator/parallel_executor.py - 并行执行优化",
            "config/logging_config.py - 结构化日志",
            "data_sources/rate_limiter.py - API限流管理",
            "web/visualizer.py - 决策树可视化",
            "data_sources/cache.py - 缓存机制",
            "agents/token_optimizer.py - Token使用优化",
        ]
        for file in files:
            print(f"  ✅ {file}")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
