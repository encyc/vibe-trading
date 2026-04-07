"""
Prime Agent - 中央决策和监控系统

这是Vibe Trading的新一代架构，采用事件驱动的Hub-and-Spoke模式：
- Prime Agent作为中央决策者和监控者
- 13个Subagent完全扁平化，直接与Prime Agent通信
- Message Channel作为事件总线连接所有agent
- Harness Engineering提供多层次约束管理
"""

from vibe_trading.prime.prime_agent import PrimeAgent, PrimeAgentConfig
from vibe_trading.prime.models import PrimeConfig
from vibe_trading.prime.message_channel import MessageChannel, MessagePriority
from vibe_trading.prime.harness_manager import HarnessManager, HarnessConfig
from vibe_trading.prime.subagent_factory import SubagentFactory
from vibe_trading.prime.decision_aggregator import DecisionAggregator, SignalType

__all__ = [
    "PrimeAgent",
    "PrimeAgentConfig",
    "PrimeConfig",
    "MessageChannel",
    "MessagePriority",
    "HarnessManager",
    "HarnessConfig",
    "SubagentFactory",
    "DecisionAggregator",
    "SignalType",
]
