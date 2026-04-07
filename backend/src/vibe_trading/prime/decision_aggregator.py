"""
决策聚合器 - 收集和整合Subagent的建议

负责从多个Subagent收集建议，并根据权重和优先级做出最终决策。
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage, MessageType
from vibe_trading.prime.models import Decision, TradingAction

logger = get_logger(__name__)


class SignalType(str, Enum):
    """信号类型"""
    BULLISH = "bullish"      # 看涨
    BEARISH = "bearish"      # 看跌
    NEUTRAL = "neutral"      # 中性
    HOLD = "hold"            # 持有


@dataclass
class SubagentSignal:
    """Subagent信号"""
    agent_id: str
    agent_type: str
    signal_type: SignalType
    confidence: float  # 0-1
    reasoning: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def weight(self) -> float:
        """信号权重（基于agent类型）"""
        # 决策层的权重最高
        if self.agent_type == "decision":
            return 1.0
        # 研究员次之
        elif self.agent_type == "researcher":
            return 0.8
        # 风控再次
        elif self.agent_type == "risk":
            return 0.7
        # 分析师基础权重
        elif self.agent_type == "analyst":
            return 0.6
        # 宏观分析权重较高
        elif self.agent_type == "macro":
            return 0.9
        return 0.5


class DecisionAggregator:
    """
    决策聚合器

    功能：
    1. 收集所有Subagent的信号
    2. 按类型分组信号
    3. 计算加权共识
    4. 生成最终决策
    """

    def __init__(self, min_signals: int = 3):
        """
        初始化决策聚合器

        Args:
            min_signals: 最少信号数量（低于此数量不做决策）
        """
        self.min_signals = min_signals
        self.signals: List[SubagentSignal] = []
        self.signal_history: List[Dict] = []

    def add_signal(self, message: AgentMessage) -> Optional[SubagentSignal]:
        """
        从AgentMessage中提取并添加信号

        Args:
            message: Agent消息

        Returns:
            提取的信号或None
        """
        signal = self._extract_signal(message)
        if signal:
            self.signals.append(signal)
            logger.debug(
                f"Added signal from {signal.agent_id}: {signal.signal_type.value} (confidence={signal.confidence:.2f})",
                tag="AGGREGATOR",
            )
        return signal

    def _extract_signal(self, message: AgentMessage) -> Optional[SubagentSignal]:
        """
        从AgentMessage中提取信号

        Args:
            message: Agent消息

        Returns:
            提取的信号或None
        """
        content = message.content
        sender = message.sender

        # 获取agent类型
        agent_type = self._get_agent_type(sender)
        if not agent_type:
            return None

        # 提取信号类型和置信度
        signal_type, confidence, reasoning = self._parse_content(content, message.message_type)

        if signal_type is None:
            return None

        return SubagentSignal(
            agent_id=sender,
            agent_type=agent_type,
            signal_type=signal_type,
            confidence=confidence,
            reasoning=reasoning,
            timestamp=message.timestamp,
            metadata={"message_type": message.message_type.value},
        )

    def _get_agent_type(self, agent_id: str) -> Optional[str]:
        """获取agent类型"""
        # 根据agent_id判断类型
        if "analyst" in agent_id:
            return "analyst"
        elif "researcher" in agent_id or "research_manager" in agent_id:
            return "researcher"
        elif "risk" in agent_id:
            return "risk"
        elif "trader" in agent_id or "portfolio" in agent_id:
            return "decision"
        elif "macro" in agent_id:
            return "macro"
        return None

    def _parse_content(self, content: Dict, message_type: MessageType) -> tuple:
        """
        解析内容，提取信号类型、置信度和理由

        Returns:
            (signal_type, confidence, reasoning)
        """
        # 默认值
        signal_type = SignalType.NEUTRAL
        confidence = 0.5
        reasoning = ""

        # 从content中提取信息
        if "confidence" in content:
            confidence = float(content["confidence"])

        # 根据message_type和content判断信号类型
        if message_type == MessageType.BUY_SIGNAL:
            signal_type = SignalType.BULLISH
        elif message_type == MessageType.SELL_SIGNAL:
            signal_type = SignalType.BEARISH
        elif message_type == MessageType.HOLD_SIGNAL:
            signal_type = SignalType.HOLD
        else:
            # 从内容中分析
            signal_type = self._analyze_sentiment(content)

        # 提取理由
        reasoning = content.get("reason", "")
        if not reasoning:
            reasoning = content.get("analysis", "")
        if not reasoning:
            reasoning = content.get("recommendation", "")

        # 确保置信度在0-1范围
        confidence = max(0.0, min(1.0, confidence))

        return signal_type, confidence, reasoning

    def _analyze_sentiment(self, content: Dict) -> SignalType:
        """分析内容情感"""
        text = str(content).lower()

        # 看涨关键词
        bullish_keywords = ["buy", "bullish", "up", "long", "buy", "买入", "做多", "看涨", "上涨"]
        # 看跌关键词
        bearish_keywords = ["sell", "bearish", "down", "short", "卖出", "做空", "看跌", "下跌"]
        # 中性关键词
        neutral_keywords = ["hold", "neutral", "wait", "持有", "中性", "观望"]

        bullish_score = sum(1 for kw in bullish_keywords if kw in text)
        bearish_score = sum(1 for kw in bearish_keywords if kw in text)
        neutral_score = sum(1 for kw in neutral_keywords if kw in text)

        if bullish_score > bearish_score and bullish_score > neutral_score:
            return SignalType.BULLISH
        elif bearish_score > bullish_score and bearish_score > neutral_score:
            return SignalType.BEARISH
        elif neutral_score > 0:
            return SignalType.HOLD
        else:
            return SignalType.NEUTRAL

    def aggregate(self) -> Optional[Decision]:
        """
        聚合所有信号并做出决策

        Returns:
            最终决策或None（信号不足）
        """
        if len(self.signals) < self.min_signals:
            logger.warning(
                f"Insufficient signals: {len(self.signals)} < {self.min_signals}",
                tag="AGGREGATOR",
            )
            return None

        # 按类型分组
        signals_by_type = defaultdict(list)
        for signal in self.signals:
            signals_by_type[signal.agent_type].append(signal)

        # 计算加权得分
        scores = self._calculate_weighted_scores(signals_by_type)

        # 生成决策
        decision = self._make_decision(scores)

        # 记录历史
        self._record_aggregation(decision, scores)

        # 清空信号（为下一次聚合做准备）
        self.signals.clear()

        return decision

    def _calculate_weighted_scores(self, signals_by_type: Dict[str, List[SubagentSignal]]) -> Dict[str, float]:
        """
        计算加权得分

        Returns:
            {signal_type: weighted_score}
        """
        scores = {
            SignalType.BULLISH.value: 0.0,
            SignalType.BEARISH.value: 0.0,
            SignalType.NEUTRAL.value: 0.0,
            SignalType.HOLD.value: 0.0,
        }

        total_weight = 0.0

        for agent_type, signals in signals_by_type.items():
            for signal in signals:
                weight = signal.weight
                confidence = signal.confidence

                # 加权得分 = 权重 × 置信度
                scores[signal.signal_type.value] += weight * confidence
                total_weight += weight

        # 归一化
        if total_weight > 0:
            for signal_type in scores:
                scores[signal_type] /= total_weight

        return scores

    def _make_decision(self, scores: Dict[str, float]) -> Decision:
        """
        根据得分做出决策

        Args:
            scores: 各信号类型的加权得分

        Returns:
            决策
        """
        # 找出最高分
        max_score = max(scores.values())
        max_signal_type = max(scores, key=scores.get)

        # 构建理由
        reasoning = f"基于{len(self.signal_history) + 1}个Subagent的信号聚合："
        for signal_type, score in scores.items():
            if score > 0.1:  # 只显示显著的信号
                reasoning += f" {signal_type}={score:.2f},"

        reasoning = reasoning.rstrip(",")

        # 确定交易动作
        if max_signal_type == SignalType.BULLISH.value and max_score > 0.4:
            action = TradingAction.BUY
        elif max_signal_type == SignalType.BEARISH.value and max_score > 0.4:
            action = TradingAction.SELL
        else:
            action = TradingAction.HOLD

        return Decision(
            action=action,
            reason=reasoning,
            confidence=max_score,
            metadata={
                "aggregation_method": "weighted_voting",
                "scores": scores,
                "signal_count": len(self.signal_history) + 1,
            },
        )

    def _record_aggregation(self, decision: Optional[Decision], scores: Dict[str, float]) -> None:
        """记录聚合历史"""
        self.signal_history.append({
            "timestamp": datetime.now().isoformat(),
            "signal_count": len(self.signals),
            "scores": scores.copy(),
            "decision": decision.action.value if decision else None,
            "confidence": decision.confidence if decision else None,
        })

        # 只保留最近100条
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]

    def get_status(self) -> Dict[str, Any]:
        """获取聚合器状态"""
        return {
            "current_signals": len(self.signals),
            "min_signals": self.min_signals,
            "history_count": len(self.signal_history),
            "recent_scores": self.signal_history[-5:] if self.signal_history else [],
        }

    def reset(self) -> None:
        """重置聚合器"""
        self.signals.clear()
        logger.info("Decision aggregator reset", tag="AGGREGATOR")
