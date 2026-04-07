"""
交易反思系统

从交易结果中学习，更新各Agent的记忆。
对应TradeAgents的reflection.py功能。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pi_logger import get_logger

from vibe_trading.memory.memory import PersistentMemory
from pi_ai import stream_simple

logger = get_logger(__name__)


class ReflectionOutcome(str, Enum):
    """反思结果"""
    CORRECT = "correct"  # 决策正确
    INCORRECT = "incorrect"  # 决策错误
    PARTIAL = "partial"  # 部分正确
    UNCERTAIN = "uncertain"  # 无法确定


@dataclass
class Reflection:
    """反思内容"""
    agent_name: str
    situation: str  # 当时的情况描述
    decision: str  # 当时的决策
    actual_outcome: str  # 实际结果
    outcome_type: ReflectionOutcome
    key_factors: List[str]  # 关键因素
    lessons_learned: List[str]  # 经验教训
    confidence: float  # 反思置信度 (0-1)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeResult:
    """交易结果"""
    symbol: str
    decision: str  # "BUY"/"SELL"/"HOLD"
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    pnl_percentage: float
    hold_duration_hours: float
    market_condition: str  # "trending"/"ranging"/"volatile"
    timestamp: datetime = field(default_factory=datetime.now)


class TradeReflector:
    """
    交易反思器

    分析交易结果，生成反思，更新各Agent的记忆。
    """

    def __init__(
        self,
        memory: PersistentMemory,
        llm_model: Optional[Any] = None,
        enable_auto_reflection: bool = True,
    ):
        """
        初始化反思器

        Args:
            memory: 持久化记忆系统
            llm_model: LLM模型（用于生成反思）
            enable_auto_reflection: 是否启用自动反思
        """
        self.memory = memory
        self.llm_model = llm_model
        self.enable_auto_reflection = enable_auto_reflection

        # 存储待处理的反思
        self._pending_reflections: List[Reflection] = []

    async def reflect_on_trade(
        self,
        trade_result: TradeResult,
        agent_reports: Dict[str, str],
        decision_context: Dict[str, Any],
    ) -> List[Reflection]:
        """
        对一笔交易进行完整反思

        Args:
            trade_result: 交易结果
            agent_reports: 各Agent的报告
            decision_context: 决策上下文

        Returns:
            生成的反思列表
        """
        logger.info(
            f"开始反思交易: {trade_result.symbol} {trade_result.decision} "
            f"PnL: {trade_result.pnl_percentage:.2f}%",
            tag="Reflection"
        )

        reflections = []

        # 1. 评估整体决策结果
        outcome = self._evaluate_outcome(trade_result)

        # 2. 反思各个Agent的表现
        for agent_name, report in agent_reports.items():
            reflection = await self._reflect_agent(
                agent_name=agent_name,
                report=report,
                trade_result=trade_result,
                outcome=outcome,
                decision_context=decision_context,
            )
            reflections.append(reflection)

        # 3. 生成整体反思
        overall_reflection = await self._reflect_overall(
            trade_result=trade_result,
            agent_reports=agent_reports,
            outcome=outcome,
        )
        reflections.append(overall_reflection)

        # 4. 更新记忆
        await self._update_memory_from_reflections(reflections)

        logger.info(
            f"反思完成: 生成了 {len(reflections)} 条反思",
            tag="Reflection"
        )

        return reflections

    def _evaluate_outcome(self, trade_result: TradeResult) -> ReflectionOutcome:
        """评估交易结果"""
        pnl_pct = trade_result.pnl_percentage

        if pnl_pct > 2:  # 盈利超过2%
            return ReflectionOutcome.CORRECT
        elif pnl_pct < -2:  # 亏损超过2%
            return ReflectionOutcome.INCORRECT
        elif abs(pnl_pct) < 0.5:  # 盈亏小于0.5%
            return ReflectionOutcome.PARTIAL
        else:
            return ReflectionOutcome.UNCERTAIN

    async def _reflect_agent(
        self,
        agent_name: str,
        report: str,
        trade_result: TradeResult,
        outcome: ReflectionOutcome,
        decision_context: Dict[str, Any],
    ) -> Reflection:
        """
        反思单个Agent的表现

        Args:
            agent_name: Agent名称
            report: Agent的报告
            trade_result: 交易结果
            outcome: 结果类型
            decision_context: 决策上下文

        Returns:
            反思内容
        """
        # 构建反思提示
        reflection_prompt = self._build_reflection_prompt(
            agent_name=agent_name,
            report=report,
            trade_result=trade_result,
            outcome=outcome,
            decision_context=decision_context,
        )

        # 使用LLM生成反思（如果可用）
        if self.llm_model and self.enable_auto_reflection:
            reflection_content = await self._generate_reflection_with_llm(
                agent_name, reflection_prompt
            )
        else:
            # 使用规则生成反思
            reflection_content = self._generate_reflection_with_rules(
                agent_name, report, trade_result, outcome
            )

        # 构建情况描述（用于记忆检索）
        situation = self._build_situation_description(
            trade_result, decision_context
        )

        return Reflection(
            agent_name=agent_name,
            situation=situation,
            decision=trade_result.decision,
            actual_outcome=f"PnL: {trade_result.pnl_percentage:.2f}%",
            outcome_type=outcome,
            key_factors=reflection_content.get("key_factors", []),
            lessons_learned=reflection_content.get("lessons", []),
            confidence=reflection_content.get("confidence", 0.5),
        )

    def _build_reflection_prompt(
        self,
        agent_name: str,
        report: str,
        trade_result: TradeResult,
        outcome: ReflectionOutcome,
        decision_context: Dict[str, Any],
    ) -> str:
        """构建反思提示"""
        return f"""作为{agent_name}的反思专家，分析这次交易表现：

**交易结果**:
- 交易对: {trade_result.symbol}
- 决策: {trade_result.decision}
- 入场价: {trade_result.entry_price}
- 出场价: {trade_result.exit_price}
- 盈亏: {trade_result.pnl_percentage:.2f}%
- 持仓时长: {trade_result.hold_duration_hours:.1f}小时
- 市场状态: {trade_result.market_condition}

**你的报告**:
{report[:2000]}

**请分析**:
1. 这个预测是正确还是错误？为什么？
2. 哪些因素导致了这个结果？
3. 有什么重要的经验教训？
4. 未来遇到类似情况应该怎么做？

**输出格式** (JSON):
{{
    "correct": true/false,
    "key_factors": ["因素1", "因素2", ...],
    "lessons": ["教训1", "教训2", ...],
    "confidence": 0.0-1.0
}}
"""

    async def _generate_reflection_with_llm(
        self,
        agent_name: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """使用LLM生成反思"""
        try:
            response = await stream_simple(
                self.llm_model,
                {"system_prompt": "你是交易反思专家。", "messages": [{"role": "user", "content": prompt}]},
            )

            # 等待响应完成
            message = await response.result()
            content = str(message.content)

            # 解析JSON（简化版，实际应该用json.loads）
            return self._parse_reflection_content(content)

        except Exception as e:
            logger.warning(f"LLM反思失败，使用规则生成: {e}", tag="Reflection")
            return {}

    def _generate_reflection_with_rules(
        self,
        agent_name: str,
        report: str,
        trade_result: TradeResult,
        outcome: ReflectionOutcome,
    ) -> Dict[str, Any]:
        """使用规则生成反思"""
        factors = []
        lessons = []

        # 基于盈亏判断
        if outcome == ReflectionOutcome.CORRECT:
            factors.append("盈利交易")
            lessons.append(f"{agent_name}的分析在此情况下有效")
        elif outcome == ReflectionOutcome.INCORRECT:
            factors.append("亏损交易")
            lessons.append(f"{agent_name}需要改进在此类情况下的分析")

        # 基于市场状态
        if "trending" in trade_result.market_condition:
            factors.append("趋势市场")
            lessons.append("注意趋势跟随策略")
        elif "ranging" in trade_result.market_condition:
            factors.append("震荡市场")
            lessons.append("震荡市场应谨慎")

        return {
            "key_factors": factors,
            "lessons": lessons,
            "confidence": 0.6,
        }

    def _parse_reflection_content(self, content: str) -> Dict[str, Any]:
        """解析反思内容"""
        # 简化版解析，实际应该更robust
        import json
        import re

        try:
            # 尝试提取JSON
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError):
            pass

        return {"key_factors": [], "lessons": [], "confidence": 0.5}

    def _build_situation_description(
        self,
        trade_result: TradeResult,
        decision_context: Dict[str, Any],
    ) -> str:
        """构建情况描述"""
        return (
            f"{trade_result.symbol} {trade_result.decision} "
            f"价格:{trade_result.entry_price}->{trade_result.exit_price} "
            f"市场:{trade_result.market_condition}"
        )

    async def _reflect_overall(
        self,
        trade_result: TradeResult,
        agent_reports: Dict[str, str],
        outcome: ReflectionOutcome,
    ) -> Reflection:
        """生成整体反思"""
        # 分析哪些Agent预测正确
        correct_agents = []
        incorrect_agents = []

        for agent_name, report in agent_reports.items():
            # 简化判断：根据报告中的关键词
            if "buy" in report.lower() and trade_result.decision == "BUY":
                if outcome == ReflectionOutcome.CORRECT:
                    correct_agents.append(agent_name)
                else:
                    incorrect_agents.append(agent_name)
            elif "sell" in report.lower() and trade_result.decision == "SELL":
                if outcome == ReflectionOutcome.CORRECT:
                    correct_agents.append(agent_name)
                else:
                    incorrect_agents.append(agent_name)

        return Reflection(
            agent_name="Overall",
            situation=self._build_situation_description(trade_result, {}),
            decision=trade_result.decision,
            actual_outcome=f"PnL: {trade_result.pnl_percentage:.2f}%",
            outcome_type=outcome,
            key_factors=[
                f"正确的Agent: {', '.join(correct_agents)}",
                f"错误的Agent: {', '.join(incorrect_agents)}",
            ],
            lessons_learned=[
                f"应更多听取{'正确Agent的意见' if correct_agents else '多方意见'}",
            ],
            confidence=0.7,
        )

    async def _update_memory_from_reflections(self, reflections: List[Reflection]):
        """从反思更新记忆"""
        for reflection in reflections:
            # 构建记忆条目
            memory_entry = {
                "situation": reflection.situation,
                "decision": reflection.decision,
                "outcome": reflection.actual_outcome,
                "lessons": "; ".join(reflection.lessons_learned),
                "timestamp": reflection.timestamp.isoformat(),
            }

            # 存储到记忆（按agent分类）
            collection = f"reflections_{reflection.agent_name}"
            await self.memory.add(
                query=reflection.situation,
                content=memory_entry,
                collection=collection,
            )

            logger.debug(
                f"已更新{reflection.agent_name}的记忆: {reflection.situation}",
                tag="Memory"
            )

    async def get_relevant_reflections(
        self,
        agent_name: str,
        current_situation: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        获取相关的历史反思

        Args:
            agent_name: Agent名称
            current_situation: 当前情况描述
            top_k: 返回数量

        Returns:
            相关的反思列表
        """
        collection = f"reflections_{agent_name}"
        results = await self.memory.search(
            query=current_situation,
            collection=collection,
            limit=top_k,
        )

        return results


# ============================================================================
# 便捷函数
# ============================================================================

async def reflect_on_completed_trade(
    symbol: str,
    decision: str,
    entry_price: float,
    exit_price: float,
    position_size: float,
    agent_reports: Dict[str, str],
    decision_context: Dict[str, Any],
    memory: PersistentMemory,
    llm_model: Optional[Any] = None,
) -> List[Reflection]:
    """
    便捷函数：对已完成的交易进行反思

    Args:
        symbol: 交易对
        decision: 决策方向
        entry_price: 入场价格
        exit_price: 出场价格
        position_size: 仓位大小
        agent_reports: 各Agent报告
        decision_context: 决策上下文
        memory: 记忆系统
        llm_model: LLM模型（可选）

    Returns:
        生成的反思列表
    """
    reflector = TradeReflector(memory=memory, llm_model=llm_model)

    # 构建交易结果
    pnl = (exit_price - entry_price) * position_size
    if decision == "SELL":
        pnl = -pnl
    pnl_percentage = (pnl / (entry_price * position_size)) * 100

    trade_result = TradeResult(
        symbol=symbol,
        decision=decision,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        pnl=pnl,
        pnl_percentage=pnl_percentage,
        hold_duration_hours=decision_context.get("hold_duration_hours", 1.0),
        market_condition=decision_context.get("market_condition", "unknown"),
    )

    return await reflector.reflect_on_trade(
        trade_result=trade_result,
        agent_reports=agent_reports,
        decision_context=decision_context,
    )
