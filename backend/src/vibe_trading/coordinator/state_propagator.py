"""
状态传播系统

管理Agent之间的状态传播，包括报告传递、辩论状态追踪、上下文构建等。
对应TradeAgents的propagation.py功能。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pi_logger import get_logger

from vibe_trading.coordinator.state_machine import DecisionContext

logger = get_logger(__name__)


# ============================================================================
# 状态定义
# ============================================================================

class DebatePhase(str, Enum):
    """辩论阶段"""
    BULL_TURN = "bull_turn"
    BEAR_TURN = "bear_turn"
    JUDGMENT = "judgment"
    COMPLETED = "completed"


class RiskDebatePhase(str, Enum):
    """风控辩论阶段"""
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"
    NEUTRAL = "neutral"
    CONSENSUS = "consensus"


@dataclass
class DebateState:
    """投资辩论状态"""
    bull_history: List[str] = field(default_factory=list)
    bear_history: List[str] = field(default_factory=list)
    current_phase: DebatePhase = DebatePhase.BULL_TURN
    round_number: int = 0
    max_rounds: int = 2
    bull_arguments: List[Dict] = field(default_factory=list)
    bear_arguments: List[Dict] = field(default_factory=list)
    judge_decision: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "bull_history": self.bull_history,
            "bear_history": self.bear_history,
            "current_phase": self.current_phase.value,
            "round_number": self.round_number,
            "max_rounds": self.max_rounds,
            "bull_arguments": self.bull_arguments,
            "bear_arguments": self.bear_arguments,
            "judge_decision": self.judge_decision,
            "confidence": self.confidence,
        }


@dataclass
class RiskDebateState:
    """风控辩论状态"""
    aggressive_history: List[str] = field(default_factory=list)
    conservative_history: List[str] = field(default_factory=list)
    neutral_history: List[str] = field(default_factory=list)
    current_phase: RiskDebatePhase = RiskDebatePhase.AGGRESSIVE
    round_number: int = 0
    max_rounds: int = 1
    risk_parameters: Dict[str, Any] = field(default_factory=dict)
    consensus_decision: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "aggressive_history": self.aggressive_history,
            "conservative_history": self.conservative_history,
            "neutral_history": self.neutral_history,
            "current_phase": self.current_phase.value,
            "round_number": self.round_number,
            "max_rounds": self.max_rounds,
            "risk_parameters": self.risk_parameters,
            "consensus_decision": self.consensus_decision,
        }


@dataclass
class AgentMessage:
    """Agent消息"""
    agent_name: str
    agent_role: str
    content: str
    timestamp: datetime
    correlation_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
        }


@dataclass
class AgentReport:
    """Agent报告"""
    agent_name: str
    agent_role: str
    report_type: str  # "market", "sentiment", "news", "fundamentals"
    content: str
    key_findings: List[str]
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "report_type": self.report_type,
            "content": self.content,
            "key_findings": self.key_findings,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "raw_data": self.raw_data,
        }


# ============================================================================
# 增强的决策上下文
# ============================================================================

@dataclass
class EnhancedDecisionContext(DecisionContext):
    """
    增强的决策上下文

    扩展自DecisionContext，添加更多状态信息。
    """
    # Agent消息
    messages: List[AgentMessage] = field(default_factory=list)

    # 分析师报告（结构化）
    analyst_reports: Dict[str, AgentReport] = field(default_factory=dict)

    # 研究员辩论状态
    debate_state: DebateState = field(default_factory=DebateState)

    # 风控辩论状态
    risk_debate_state: RiskDebateState = field(default_factory=RiskDebateState)

    # 市场数据
    market_data: Dict[str, Any] = field(default_factory=dict)

    # 宏观状态
    macro_state: Optional[Dict] = None

    # 技术指标
    technical_indicators: Dict[str, Any] = field(default_factory=dict)

    # 基本面数据
    fundamentals: Dict[str, Any] = field(default_factory=dict)

    # 情绪数据
    sentiment: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 状态传播器
# ============================================================================

class StatePropagator:
    """
    状态传播器

    管理Agent之间的状态传播，构建决策上下文。
    """

    def __init__(self):
        """初始化状态传播器"""
        self._current_context: Optional[EnhancedDecisionContext] = None

    def create_initial_state(
        self,
        symbol: str,
        interval: str,
        market_data: Optional[Dict] = None,
        macro_state: Optional[Dict] = None,
    ) -> EnhancedDecisionContext:
        """
        创建初始决策状态

        Args:
            symbol: 交易品种
            interval: K线周期
            market_data: 市场数据
            macro_state: 宏观状态

        Returns:
            增强的决策上下文
        """
        decision_id = f"{symbol}_{interval}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        context = EnhancedDecisionContext(
            decision_id=decision_id,
            symbol=symbol,
            interval=interval,
            start_time=datetime.now(),
            market_data=market_data or {},
            macro_state=macro_state,
        )

        # 初始化辩论状态
        context.debate_state = DebateState(max_rounds=2)
        context.risk_debate_state = RiskDebateState(max_rounds=1)

        self._current_context = context

        logger.info(
            f"创建初始状态: {decision_id}",
            tag="StatePropagator"
        )

        return context

    def add_analyst_report(
        self,
        context: EnhancedDecisionContext,
        report: AgentReport,
    ) -> EnhancedDecisionContext:
        """
        添加分析师报告

        Args:
            context: 决策上下文
            report: Agent报告

        Returns:
            更新后的上下文
        """
        # 存储报告
        context.analyst_reports[report.agent_name] = report

        # 添加消息
        message = AgentMessage(
            agent_name=report.agent_name,
            agent_role=report.agent_role,
            content=report.content,
            timestamp=report.timestamp,
            correlation_id=context.decision_id,
            metadata={"report_type": report.report_type},
        )
        context.messages.append(message)

        # 更新原始数据
        if report.raw_data:
            if report.report_type == "market":
                context.technical_indicators.update(report.raw_data)
            elif report.report_type == "fundamentals":
                context.fundamentals.update(report.raw_data)
            elif report.report_type == "sentiment":
                context.sentiment.update(report.raw_data)

        logger.debug(
            f"添加分析师报告: {report.agent_name}",
            tag="StatePropagator"
        )

        return context

    def update_debate_state(
        self,
        context: EnhancedDecisionContext,
        speaker: str,  # "bull" or "bear"
        content: str,
        round_number: int,
    ) -> EnhancedDecisionContext:
        """
        更新辩论状态

        Args:
            context: 决策上下文
            speaker: 发言者
            content: 发言内容
            round_number: 轮次

        Returns:
            更新后的上下文
        """
        debate_state = context.debate_state

        if speaker == "bull":
            debate_state.bull_history.append(content)
            debate_state.current_phase = DebatePhase.BEAR_TURN
        elif speaker == "bear":
            debate_state.bear_history.append(content)
            debate_state.current_phase = DebatePhase.BULL_TURN

        debate_state.round_number = round_number

        # 添加消息
        message = AgentMessage(
            agent_name=f"{speaker.title()} Researcher",
            agent_role="researcher",
            content=content,
            timestamp=datetime.now(),
            correlation_id=context.decision_id,
            metadata={"round": round_number, "speaker": speaker},
        )
        context.messages.append(message)

        logger.debug(
            f"更新辩论状态: {speaker} (轮次 {round_number})",
            tag="StatePropagator"
        )

        return context

    def set_judgment(
        self,
        context: EnhancedDecisionContext,
        decision: str,  # "BUY"/"SELL"/"HOLD"
        confidence: float,
        reasoning: str,
    ) -> EnhancedDecisionContext:
        """
        设置研究经理的裁决

        Args:
            context: 决策上下文
            decision: 投资决策
            confidence: 置信度
            reasoning: 理由

        Returns:
            更新后的上下文
        """
        debate_state = context.debate_state
        debate_state.judge_decision = decision
        debate_state.confidence = confidence
        debate_state.current_phase = DebatePhase.COMPLETED

        # 添加消息
        message = AgentMessage(
            agent_name="Research Manager",
            agent_role="manager",
            content=f"决策: {decision} (置信度: {confidence:.2f})\n理由: {reasoning}",
            timestamp=datetime.now(),
            correlation_id=context.decision_id,
            metadata={"decision": decision, "confidence": confidence},
        )
        context.messages.append(message)

        logger.info(
            f"研究经理裁决: {decision} (置信度: {confidence:.2f})",
            tag="StatePropagator"
        )

        return context

    def update_risk_debate(
        self,
        context: EnhancedDecisionContext,
        speaker: str,  # "aggressive"/"conservative"/"neutral"
        content: str,
        risk_params: Dict[str, Any],
    ) -> EnhancedDecisionContext:
        """
        更新风控辩论

        Args:
            context: 决策上下文
            speaker: 发言者
            content: 发言内容
            risk_params: 风险参数

        Returns:
            更新后的上下文
        """
        risk_state = context.risk_debate_state

        if speaker == "aggressive":
            risk_state.aggressive_history.append(content)
            risk_state.current_phase = RiskDebatePhase.CONSERVATIVE
        elif speaker == "conservative":
            risk_state.conservative_history.append(content)
            risk_state.current_phase = RiskDebatePhase.NEUTRAL
        elif speaker == "neutral":
            risk_state.neutral_history.append(content)
            risk_state.current_phase = RiskDebatePhase.CONSensus

        # 更新风险参数
        risk_state.risk_parameters.update(risk_params)

        # 添加消息
        message = AgentMessage(
            agent_name=f"{speaker.title()} Risk Analyst",
            agent_role="risk_analyst",
            content=content,
            timestamp=datetime.now(),
            correlation_id=context.decision_id,
            metadata={"speaker": speaker, "risk_params": risk_params},
        )
        context.messages.append(message)

        logger.debug(
            f"更新风控辩论: {speaker}",
            tag="StatePropagator"
        )

        return context

    def set_risk_consensus(
        self,
        context: EnhancedDecisionContext,
        consensus: str,
        final_params: Dict[str, Any],
    ) -> EnhancedDecisionContext:
        """
        设置风控共识

        Args:
            context: 决策上下文
            consensus: 共识决策
            final_params: 最终风险参数

        Returns:
            更新后的上下文
        """
        risk_state = context.risk_debate_state
        risk_state.consensus_decision = consensus
        risk_state.risk_parameters.update(final_params)
        risk_state.current_phase = RiskDebatePhase.CONSensus

        logger.info(
            f"风控共识: {consensus}",
            tag="StatePropagator"
        )

        return context

    def build_execution_context(
        self,
        context: EnhancedDecisionContext,
    ) -> Dict[str, Any]:
        """
        构建执行层所需的上下文

        Args:
            context: 决策上下文

        Returns:
            执行上下文字典
        """
        # 汇总分析师报告
        analyst_summary = {}
        for agent_name, report in context.analyst_reports.items():
            analyst_summary[agent_name] = {
                "report": report.content[:500],  # 前500字符
                "key_findings": report.key_findings,
                "confidence": report.confidence,
            }

        # 构建执行上下文
        execution_context = {
            "decision_id": context.decision_id,
            "symbol": context.symbol,
            "interval": context.interval,
            "market_data": context.market_data,
            "macro_state": context.macro_state,
            "analyst_summary": analyst_summary,
            "investment_decision": {
                "decision": context.debate_state.judge_decision,
                "confidence": context.debate_state.confidence,
                "debate_summary": {
                    "bull": context.debate_state.bull_history,
                    "bear": context.debate_state.bear_history,
                },
            },
            "risk_assessment": {
                "consensus": context.risk_debate_state.consensus_decision,
                "parameters": context.risk_debate_state.risk_parameters,
                "aggressive": context.risk_debate_state.aggressive_history,
                "conservative": context.risk_debate_state.conservative_history,
                "neutral": context.risk_debate_state.neutral_history,
            },
            "technical_indicators": context.technical_indicators,
            "fundamentals": context.fundamentals,
            "sentiment": context.sentiment,
        }

        return execution_context

    def get_message_history(
        self,
        context: EnhancedDecisionContext,
        agent_role: Optional[str] = None,
        limit: int = 10,
    ) -> List[AgentMessage]:
        """
        获取消息历史

        Args:
            context: 决策上下文
            agent_role: 过滤Agent角色（可选）
            limit: 返回数量限制

        Returns:
            消息列表
        """
        messages = context.messages

        if agent_role:
            messages = [m for m in messages if m.agent_role == agent_role]

        # 返回最近的N条消息
        return messages[-limit:]

    def export_state_snapshot(
        self,
        context: EnhancedDecisionContext,
    ) -> Dict[str, Any]:
        """
        导出状态快照（用于调试或分析）

        Args:
            context: 决策上下文

        Returns:
            状态快照字典
        """
        return {
            "decision_id": context.decision_id,
            "symbol": context.symbol,
            "interval": context.interval,
            "current_phase": context.current_phase,
            "timestamp": datetime.now().isoformat(),
            "analyst_reports": {
                name: report.to_dict()
                for name, report in context.analyst_reports.items()
            },
            "debate_state": context.debate_state.to_dict(),
            "risk_debate_state": context.risk_debate_state.to_dict(),
            "message_count": len(context.messages),
            "market_data": context.market_data,
            "macro_state": context.macro_state,
        }


# ============================================================================
# 便捷函数
# ============================================================================

def create_initial_propagator_state(
    symbol: str,
    interval: str,
    market_data: Optional[Dict] = None,
) -> EnhancedDecisionContext:
    """
    便捷函数：创建初始传播状态

    Args:
        symbol: 交易品种
        interval: K线周期
        market_data: 市场数据

    Returns:
        增强的决策上下文
    """
    propagator = StatePropagator()
    return propagator.create_initial_state(
        symbol=symbol,
        interval=interval,
        market_data=market_data,
    )


def build_debate_context(
    context: EnhancedDecisionContext,
) -> str:
    """
    便捷函数：构建辩论上下文字符串

    Args:
        context: 决策上下文

    Returns:
    辩论上下文字符串
    """
    parts = []

    # 基本信息
    parts.append(f"**{context.symbol} ({context.interval})**")

    # 分析师摘要
    if context.analyst_reports:
        parts.append("\n**分析师报告摘要:**")
        for agent_name, report in context.analyst_reports.items():
            parts.append(f"- {agent_name}: {report.content[:200]}...")

    # 辩论历史
    debate = context.debate_state
    if debate.bull_history or debate.bear_history:
        parts.append("\n**辩论历史:**")
        if debate.bull_history:
            parts.append(f"- Bull: {debate.bull_history[-1][:200]}...")
        if debate.bear_history:
            parts.append(f"- Bear: {debate.bear_history[-1][:200]}...")

    return "\n".join(parts)
