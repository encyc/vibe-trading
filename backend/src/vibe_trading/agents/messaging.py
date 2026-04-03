"""
Agent消息标准化

定义Agent间通信的标准消息格式。
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import logging

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """消息类型"""
    # 分析师团队消息
    ANALYSIS_REPORT = "analysis_report"
    TECHNICAL_ANALYSIS = "technical_analysis"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    NEWS_ANALYSIS = "news_analysis"
    SENTIMENT_ANALYSIS = "sentiment_analysis"

    # 研究员团队消息
    DEBATE_SPEECH = "debate_speech"
    REBUTTAL = "rebuttal"
    BULL_ARGUMENT = "bull_argument"
    BEAR_ARGUMENT = "bear_argument"

    # 研究经理消息
    INVESTMENT_ADVICE = "investment_advice"
    RESEARCH_DECISION = "research_decision"

    # 风控团队消息
    RISK_ASSESSMENT = "risk_assessment"
    RISK_WARNING = "risk_warning"
    VAR_CALCULATION = "var_calculation"

    # 决策层消息
    EXECUTION_PLAN = "execution_plan"
    TRADING_PLAN = "trading_plan"
    FINAL_DECISION = "final_decision"
    EXECUTION_ORDER = "execution_order"

    # 系统消息
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STATUS_UPDATE = "status_update"


@dataclass
class AgentMessage:
    """
    Agent间标准消息格式

    所有Agent之间的通信都应使用此格式。
    """
    # 基本信息
    message_id: str
    correlation_id: str  # 一次完整决策流程的ID
    sender: str          # 发送者Agent名称
    receiver: str        # 接收者Agent名称（"all"表示广播）
    message_type: MessageType

    # 消息内容
    content: Dict
    timestamp: datetime
    metadata: Dict = field(default_factory=dict)

    # 状态信息
    reply_to: Optional[str] = None  # 回复的消息ID
    thread_id: Optional[str] = None  # 线程ID（用于多轮对话）

    def __post_init__(self):
        """初始化后处理"""
        if not self.message_id:
            self.message_id = str(uuid.uuid4())

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "reply_to": self.reply_to,
            "thread_id": self.thread_id,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentMessage":
        """从字典创建"""
        return cls(
            message_id=data["message_id"],
            correlation_id=data["correlation_id"],
            sender=data["sender"],
            receiver=data["receiver"],
            message_type=MessageType(data["message_type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
            reply_to=data.get("reply_to"),
            thread_id=data.get("thread_id"),
        )

    def is_broadcast(self) -> bool:
        """是否为广播消息"""
        return self.receiver == "all" or self.receiver == "*"

    def is_reply(self) -> bool:
        """是否为回复消息"""
        return self.reply_to is not None


@dataclass
class MessageThread:
    """消息线程 - 记录相关消息的对话"""
    thread_id: str
    correlation_id: str
    participants: List[str]
    messages: List[AgentMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, message: AgentMessage):
        """添加消息"""
        self.messages.append(message)
        self.updated_at = datetime.now()

        # 更新参与者列表
        if message.sender not in self.participants:
            self.participants.append(message.sender)

    def get_messages_from(self, sender: str) -> List[AgentMessage]:
        """获取来自特定发送者的消息"""
        return [m for m in self.messages if m.sender == sender]

    def get_conversation_summary(self) -> Dict:
        """获取对话摘要"""
        return {
            "thread_id": self.thread_id,
            "correlation_id": self.correlation_id,
            "participants": self.participants,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_types": [m.message_type.value for m in self.messages],
        }


class MessageBroker:
    """
    消息代理

    管理Agent之间的消息传递，支持点对点和广播消息。
    """

    def __init__(self):
        self.messages: List[AgentMessage] = []
        self.threads: Dict[str, MessageThread] = {}
        self.subscriptions: Dict[str, List[MessageType]] = {}

    def send(
        self,
        sender: str,
        receiver: str,
        message_type: MessageType,
        content: Dict,
        correlation_id: str,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> AgentMessage:
        """
        发送消息

        Args:
            sender: 发送者
            receiver: 接收者
            message_type: 消息类型
            content: 消息内容
            correlation_id: 关联ID
            reply_to: 回复的消息ID
            thread_id: 线程ID
            metadata: 元数据

        Returns:
            创建的消息对象
        """
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            correlation_id=correlation_id,
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
            reply_to=reply_to,
            thread_id=thread_id,
        )

        self.messages.append(message)

        # 添加到线程
        if thread_id and thread_id in self.threads:
            self.threads[thread_id].add_message(message)

        logger.debug(
            f"Message sent: {sender} -> {receiver} "
            f"({message_type.value}, correlation_id={correlation_id})"
        )

        return message

    def create_thread(
        self,
        correlation_id: str,
        participants: List[str],
    ) -> MessageThread:
        """创建新的消息线程"""
        thread_id = str(uuid.uuid4())
        thread = MessageThread(
            thread_id=thread_id,
            correlation_id=correlation_id,
            participants=participants,
        )
        self.threads[thread_id] = thread
        return thread

    def get_thread(self, thread_id: str) -> Optional[MessageThread]:
        """获取消息线程"""
        return self.threads.get(thread_id)

    def get_correlation_messages(self, correlation_id: str) -> List[AgentMessage]:
        """获取特定关联ID的所有消息"""
        return [m for m in self.messages if m.correlation_id == correlation_id]

    def get_messages_for_agent(self, agent_name: str) -> List[AgentMessage]:
        """获取发送给特定Agent的所有消息"""
        return [
            m for m in self.messages
            if m.receiver == agent_name or m.is_broadcast()
        ]

    def get_conversation_history(
        self,
        correlation_id: str,
        thread_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取对话历史

        Args:
            correlation_id: 关联ID
            thread_id: 线程ID（可选）

        Returns:
            对话历史列表
        """
        if thread_id:
            thread = self.threads.get(thread_id)
            if thread:
                return [m.to_dict() for m in thread.messages]
            return []

        messages = self.get_correlation_messages(correlation_id)
        return [m.to_dict() for m in messages]

    def subscribe(self, agent_name: str, message_types: List[MessageType]):
        """
        订阅消息类型

        Agent可以订阅特定类型的消息，用于过滤。
        """
        self.subscriptions[agent_name] = message_types

    def clear_history(self, older_than_hours: Optional[int] = None):
        """清理历史消息"""
        if older_than_hours is None:
            self.messages.clear()
            self.threads.clear()
            return

        cutoff = datetime.now().timestamp() - (older_than_hours * 3600)
        self.messages = [
            m for m in self.messages
            if m.timestamp.timestamp() > cutoff
        ]

        # 清理空线程
        self.threads = {
            k: v for k, v in self.threads.items()
            if v.messages
        }

    def get_statistics(self) -> Dict:
        """获取消息统计"""
        message_types = {}
        for m in self.messages:
            mt = m.message_type.value
            message_types[mt] = message_types.get(mt, 0) + 1

        return {
            "total_messages": len(self.messages),
            "total_threads": len(self.threads),
            "message_types": message_types,
            "active_subscriptions": len(self.subscriptions),
        }


# 全局单例
_message_broker = MessageBroker()


def get_message_broker() -> MessageBroker:
    """获取全局消息代理"""
    return _message_broker


# 工厂函数 - 创建常用消息类型
def create_analysis_report(
    sender: str,
    correlation_id: str,
    analysis_type: str,
    report: Dict,
    metadata: Optional[Dict] = None,
) -> AgentMessage:
    """创建分析报告消息"""
    return get_message_broker().send(
        sender=sender,
        receiver="research_team",
        message_type=MessageType.ANALYSIS_REPORT,
        content={
            "analysis_type": analysis_type,
            "report": report,
        },
        correlation_id=correlation_id,
        metadata=metadata,
    )


def create_debate_speech(
    sender: str,
    correlation_id: str,
    side: str,
    speech: str,
    round_number: int,
    reply_to: Optional[str] = None,
) -> AgentMessage:
    """创建辩论发言消息"""
    return get_message_broker().send(
        sender=sender,
        receiver="opponent",
        message_type=MessageType.DEBATE_SPEECH,
        content={
            "side": side,
            "speech": speech,
            "round_number": round_number,
        },
        correlation_id=correlation_id,
        reply_to=reply_to,
    )


def create_investment_advice(
    sender: str,
    correlation_id: str,
    action: str,
    confidence: float,
    rationale: str,
    metadata: Optional[Dict] = None,
) -> AgentMessage:
    """创建投资建议消息"""
    return get_message_broker().send(
        sender=sender,
        receiver="risk_team",
        message_type=MessageType.INVESTMENT_ADVICE,
        content={
            "action": action,
            "confidence": confidence,
            "rationale": rationale,
        },
        correlation_id=correlation_id,
        metadata=metadata,
    )


def create_risk_assessment(
    sender: str,
    correlation_id: str,
    risk_level: str,
    position_size_pct: float,
    stop_loss_pct: float,
    metadata: Optional[Dict] = None,
) -> AgentMessage:
    """创建风险评估消息"""
    return get_message_broker().send(
        sender=sender,
        receiver="decision_layer",
        message_type=MessageType.RISK_ASSESSMENT,
        content={
            "risk_level": risk_level,
            "position_size_pct": position_size_pct,
            "stop_loss_pct": stop_loss_pct,
        },
        correlation_id=correlation_id,
        metadata=metadata,
    )


def create_final_decision(
    sender: str,
    correlation_id: str,
    decision: str,
    execution_plan: Dict,
    metadata: Optional[Dict] = None,
) -> AgentMessage:
    """创建最终决策消息"""
    return get_message_broker().send(
        sender=sender,
        receiver="executor",
        message_type=MessageType.FINAL_DECISION,
        content={
            "decision": decision,
            "execution_plan": execution_plan,
        },
        correlation_id=correlation_id,
        metadata=metadata,
    )
