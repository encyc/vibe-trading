"""
Prime Agent 数据模型

定义Prime Agent架构的核心数据结构。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from vibe_trading.agents.messaging import AgentMessage, MessageType


class MessagePriority(str, Enum):
    """消息优先级"""
    LOW = "low"          # 低优先级（日志、统计等）
    NORMAL = "normal"    # 普通优先级（常规分析、建议等）
    HIGH = "high"        # 高优先级（重要事件、警告等）
    CRITICAL = "critical"  # 紧急优先级（紧急情况、风险事件等）


class DecisionPriority(str, Enum):
    """决策优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TradingAction(str, Enum):
    """交易动作"""
    HOLD = "hold"
    BUY = "buy"
    SELL = "sell"
    CLOSE_ALL = "close_all"
    REDUCE_POSITION = "reduce_position"
    INCREASE_POSITION = "increase_position"


class EmergencyType(str, Enum):
    """紧急情况类型"""
    CRASH = "crash"                   # 价格暴跌
    PUMP = "pump"                     # 价格暴涨
    RISK_LIMIT = "risk_limit"         # 风险超标
    MARGIN_CALL = "margin_call"       # 保证金不足
    SYSTEM_ERROR = "system_error"     # 系统异常
    DATA_ANOMALY = "data_anomaly"     # 数据异常
    NETWORK_ERROR = "network_error"   # 网络错误


@dataclass
class Decision:
    """Prime Agent的决策"""
    action: TradingAction
    reason: str
    symbol: str = "BTCUSDT"
    confidence: float = 0.0
    quantity: Optional[float] = None
    price: Optional[float] = None
    override: bool = False  # 是否是覆盖决策
    priority: DecisionPriority = DecisionPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintViolation:
    """约束违规记录"""
    constraint_name: str
    constraint_type: str
    message: AgentMessage
    reason: str
    severity: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SystemState:
    """系统状态"""
    current_position: float = 0.0
    account_balance: float = 10000.0
    total_pnl: float = 0.0
    active_trades: int = 0
    last_decision_time: Optional[datetime] = None
    last_emergency_time: Optional[datetime] = None
    llm_calls_today: int = 0
    cost_today: float = 0.0
    messages_processed: int = 0
    violations_today: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "current_position": self.current_position,
            "account_balance": self.account_balance,
            "total_pnl": self.total_pnl,
            "active_trades": self.active_trades,
            "last_decision_time": self.last_decision_time.isoformat() if self.last_decision_time else None,
            "last_emergency_time": self.last_emergency_time.isoformat() if self.last_emergency_time else None,
            "llm_calls_today": self.llm_calls_today,
            "cost_today": self.cost_today,
            "messages_processed": self.messages_processed,
            "violations_today": self.violations_today,
        }


@dataclass
class PrimeConfig:
    """Prime Agent配置"""
    # 交易配置
    symbol: str = "BTCUSDT"  # 交易对符号
    interval: str = "30m"  # K线间隔

    # 监控配置
    monitoring_interval: float = 1.0  # 监控循环超时（秒）
    max_queue_size: int = 1000  # 消息队列最大大小

    # 约束配置
    max_single_trade: float = 1000.0  # 单笔交易最大金额
    max_total_position: float = 0.3  # 总仓位最大比例
    max_leverage: int = 5  # 最大杠杆

    # 操作约束
    min_trade_interval: float = 60.0  # 最小交易间隔（秒）
    max_direction_changes: int = 3  # 最大方向改变次数（每小时）
    max_daily_trades: int = 20  # 每日最大交易次数

    # 资源约束
    max_llm_calls_per_day: int = 1000  # 每日最大LLM调用次数
    max_daily_cost: float = 10.0  # 每日最大成本（美元）
    max_tokens_per_message: int = 8000  # 每条消息最大token数

    # 紧急情况阈值
    crash_threshold: float = -0.05  # 暴跌阈值（-5%）
    pump_threshold: float = 0.05  # 暴涨阈值（+5%）
    var_threshold: float = 0.02  # VaR阈值（2%）
    margin_threshold: float = 0.8  # 保证金阈值（80%）

    # 启用的Subagent
    enabled_subagents: List[str] = field(default_factory=lambda: [
        "technical_analyst",
        "fundamental_analyst",
        "news_analyst",
        "sentiment_analyst",
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "aggressive_risk_analyst",
        "neutral_risk_analyst",
        "conservative_risk_analyst",
        "trader",
        "portfolio_manager",
        "macro_analyst",
    ])

    # 紧急覆盖权限
    enable_emergency_override: bool = True  # 是否启用紧急覆盖
    emergency_auto_execute: bool = False  # 紧急情况是否自动执行（不询问）


@dataclass
class HarnessConfig:
    """Harness Manager配置"""
    # 约束开关
    enable_safety_constraint: bool = True
    enable_operational_constraint: bool = True
    enable_behavioral_constraint: bool = True
    enable_resource_constraint: bool = True

    # 违规处理
    violation_action: str = "block"  # block, warn, log
    max_violations_per_day: int = 10  # 每日最大违规次数

    # 约束参数
    safe_position_ratio: float = 0.95  # 安全仓位比例（95%）
    warning_threshold: float = 0.8  # 警告阈值（80%）


@dataclass
class SubagentConfig:
    """Subagent配置"""
    agent_id: str
    agent_type: str
    enabled: bool = True
    priority: MessagePriority = MessagePriority.NORMAL
    allowed_message_types: List[MessageType] = field(default_factory=list)
    can_direct_trade: bool = False  # 是否可以直接下单
    required_for_decision: bool = True  # 是否是决策必需的


@dataclass
class PrimeAgentConfig:
    """Prime Agent完整配置"""
    # pi_agent_core配置
    system_prompt: str = """你是Prime Agent，是一个中央决策和监控系统。

职责：
1. 监控所有Subagent的消息
2. 综合分析所有信息
3. 做出最终交易决策
4. 处理紧急情况

请始终以系统安全和风险控制为首要目标。"""

    # Prime特定配置
    prime_config: PrimeConfig = field(default_factory=PrimeConfig)

    # 约束配置
    harness_config: HarnessConfig = field(default_factory=HarnessConfig)

    # Agent额外配置
    thinking_level: Optional[str] = None  # 思考级别
    enable_credit_tracking: bool = False  # 是否启用credit追踪


@dataclass
class MessageStats:
    """消息统计"""
    total_messages: int = 0
    messages_by_type: Dict[str, int] = field(default_factory=dict)
    messages_by_agent: Dict[str, int] = field(default_factory=dict)
    messages_by_priority: Dict[str, int] = field(default_factory=dict)
    average_processing_time: float = 0.0
    last_message_time: Optional[datetime] = None

    def record_message(self, message: AgentMessage, processing_time: float) -> None:
        """记录一条消息"""
        self.total_messages += 1
        self.last_message_time = datetime.now()

        # 按类型统计
        msg_type = message.message_type.value
        self.messages_by_type[msg_type] = self.messages_by_type.get(msg_type, 0) + 1

        # 按发送者统计
        sender = message.sender
        self.messages_by_agent[sender] = self.messages_by_agent.get(sender, 0) + 1

        # 按优先级统计
        priority = message.metadata.get("priority", MessagePriority.NORMAL.value)
        self.messages_by_priority[priority] = self.messages_by_priority.get(priority, 0) + 1

        # 更新平均处理时间
        if self.total_messages == 1:
            self.average_processing_time = processing_time
        else:
            alpha = 0.1  # 指数移动平均系数
            self.average_processing_time = (
                alpha * processing_time +
                (1 - alpha) * self.average_processing_time
            )
