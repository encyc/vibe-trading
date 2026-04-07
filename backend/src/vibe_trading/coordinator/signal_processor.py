"""
交易信号处理器

从Agent输出中提取明确的交易信号、置信度和原因。
对应TradeAgents的signal_processing.py功能。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pi_logger import get_logger

logger = get_logger(__name__)


class TradingSignal(str, Enum):
    """交易信号类型"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    UNKNOWN = "UNKNOWN"


class SignalStrength(str, Enum):
    """信号强度"""
    STRONG = "strong"  # 强烈建议
    MODERATE = "moderate"  # 中等建议
    WEAK = "weak"  # 弱建议
    UNCERTAIN = "uncertain"  # 不确定


@dataclass
class ProcessedSignal:
    """处理后的交易信号"""
    signal: TradingSignal
    strength: SignalStrength
    confidence: float  # 置信度 (0-1)
    reasoning: str  # 决策原因摘要
    key_factors: List[str]  # 关键因素
    price_target: Optional[float] = None  # 目标价格
    stop_loss: Optional[float] = None  # 止损价格
    position_size_pct: Optional[float] = None  # 建议仓位百分比
    time_horizon: Optional[str] = None  # 时间 horizon (short/medium/long)
    raw_decision: str = ""  # 原始决策文本
    timestamp: datetime = field(default_factory=datetime.now)


class SignalProcessor:
    """
    信号处理器

    从Agent决策文本中提取结构化交易信号。
    """

    # 信号模式（按优先级排序）
    SIGNAL_PATTERNS = {
        TradingSignal.BUY: [
            r"\bbuy\b",
            r"\blong\b",
            r"\benter long\b",
            r"\b建议买入\b",
            r"\b推荐买入\b",
            r"\bbullish\b.*\bbuy\b",
            r"\b做多\b",
            r"\b开多\b",
        ],
        TradingSignal.SELL: [
            r"\bsell\b",
            r"\bshort\b",
            r"\bexit\b",
            r"\bclose position\b",
            r"\b建议卖出\b",
            r"\b推荐卖出\b",
            r"\bbearish\b.*\bsell\b",
            r"\b做空\b",
            r"\b开空\b",
            r"\b平仓\b",
        ],
        TradingSignal.HOLD: [
            r"\bhold\b",
            r"\bwait\b",
            r"\b观察\b",
            r"\bmaintain\b",
            r"\bno action\b",
            r"\b观望\b",
            r"\b保持\b",
            r"\b不确定\b",
        ],
    }

    # 强度模式
    STRENGTH_PATTERNS = {
        SignalStrength.STRONG: [
            r"\bstrongly\b",
            r"\bstrong\b",
            r"\bhighly\b",
            r"\bdefinitely\b",
            r"\bclearly\b",
            r"\b强烈\b",
            r"\b明确\b",
        ],
        SignalStrength.MODERATE: [
            r"\bmoderately\b",
            r"\bsomewhat\b",
            r"\blikely\b",
            r"\bprobably\b",
            r"\b倾向于\b",
        ],
        SignalStrength.WEAK: [
            r"\bweakly\b",
            r"\bslightly\b",
            r"\bmay\b",
            r"\bmight\b",
            r"\bpossibly\b",
            r"\b谨慎\b",
        ],
    }

    def __init__(self, enable_llm_enhancement: bool = False):
        """
        初始化信号处理器

        Args:
            enable_llm_enhancement: 是否使用LLM增强信号提取
        """
        self.enable_llm_enhancement = enable_llm_enhancement

    def process_signal(
        self,
        decision_text: str,
        agent_name: str = "Unknown",
        context: Optional[Dict] = None,
    ) -> ProcessedSignal:
        """
        处理决策文本，提取交易信号

        Args:
            decision_text: Agent的决策文本
            agent_name: Agent名称
            context: 额外上下文信息

        Returns:
            处理后的信号
        """
        if not decision_text:
            return self._create_unknown_signal("Empty decision text")

        # 提取信号类型
        signal = self._extract_signal_type(decision_text)

        # 提取信号强度
        strength = self._extract_signal_strength(decision_text)

        # 计算置信度
        confidence = self._calculate_confidence(decision_text, signal, strength)

        # 提取原因
        reasoning = self._extract_reasoning(decision_text)

        # 提取关键因素
        key_factors = self._extract_key_factors(decision_text)

        # 提取价格目标（如果有）
        price_target = self._extract_price_target(decision_text)

        # 提取止损（如果有）
        stop_loss = self._extract_stop_loss(decision_text)

        # 提取仓位建议（如果有）
        position_size = self._extract_position_size(decision_text)

        # 提取时间horizon（如果有）
        time_horizon = self._extract_time_horizon(decision_text)

        return ProcessedSignal(
            signal=signal,
            strength=strength,
            confidence=confidence,
            reasoning=reasoning,
            key_factors=key_factors,
            price_target=price_target,
            stop_loss=stop_loss,
            position_size_pct=position_size,
            time_horizon=time_horizon,
            raw_decision=decision_text,
        )

    def _extract_signal_type(self, text: str) -> TradingSignal:
        """提取信号类型"""
        text_lower = text.lower()

        # 按优先级检查信号（BUY优先于SELL优先于HOLD）
        for signal, patterns in self.SIGNAL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return signal

        return TradingSignal.UNKNOWN

    def _extract_signal_strength(self, text: str) -> SignalStrength:
        """提取信号强度"""
        text_lower = text.lower()

        # 检查强度关键词
        for strength, patterns in self.STRENGTH_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return strength

        return SignalStrength.UNCERTAIN

    def _calculate_confidence(
        self,
        text: str,
        signal: TradingSignal,
        strength: SignalStrength,
    ) -> float:
        """
        计算置信度

        基于多个因素：
        1. 信号类型是否明确
        2. 信号强度关键词
        3. 原因陈述的详细程度
        4. 是否有数据支持
        """
        confidence = 0.5  # 基础置信度

        # 信号明确性
        if signal != TradingSignal.UNKNOWN:
            confidence += 0.2

        # 强度关键词
        if strength == SignalStrength.STRONG:
            confidence += 0.2
        elif strength == SignalStrength.MODERATE:
            confidence += 0.1
        elif strength == SignalStrength.WEAK:
            confidence -= 0.1

        # 原因详细程度（基于长度）
        if len(text) > 500:
            confidence += 0.1
        elif len(text) < 100:
            confidence -= 0.2

        # 数据支持（查找数字、百分比等）
        if re.search(r'\d+\.?\d*%?', text):
            confidence += 0.1

        # 限制范围
        return max(0.0, min(1.0, confidence))

    def _extract_reasoning(self, text: str) -> str:
        """提取决策原因摘要"""
        # 尝试提取关键词句
        sentences = re.split(r'[.!?。！？]', text)

        # 查找包含原因关键词的句子
        reason_keywords = [
            "because", "due to", "since", "as", "reason",
            "因为", "由于", "基于", "considering", "given"
        ]

        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in reason_keywords):
                # 返回前200个字符
                return sentence.strip()[:200]

        # 如果没有找到，返回前两句
        if len(sentences) >= 2:
            return " ".join(sentences[:2]).strip()[:200]
        elif sentences:
            return sentences[0].strip()[:200]

        return text[:200]

    def _extract_key_factors(self, text: str) -> List[str]:
        """提取关键因素"""
        factors = []

        # 查找列表项
        list_patterns = [
            r'^[-•]\s*(.+)$',  # - 或 • 开头
            r'^\d+[.)]\s*(.+)$',  # 数字列表
        ]

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            for pattern in list_patterns:
                match = re.match(pattern, line)
                if match:
                    factor = match.group(1).strip()
                    if len(factor) > 5 and len(factor) < 100:
                        factors.append(factor)
                    break

        # 如果没有找到列表，尝试提取包含关键词的句子
        if not factors:
            factor_keywords = [
                "support", "resistance", "trend", "momentum",
                "volume", "rsi", "macd", "breakout", "reversal",
                "支撑", "阻力", "趋势", "动量", "突破", "反转"
            ]

            for sentence in re.split(r'[.!?。！？]', text):
                sentence_lower = sentence.lower()
                if any(keyword in sentence_lower for keyword in factor_keywords):
                    factors.append(sentence.strip()[:100])

        # 限制数量
        return factors[:5]

    def _extract_price_target(self, text: str) -> Optional[float]:
        """提取目标价格"""
        # 查找目标价格模式
        patterns = [
            r"target[:\s]+\$?(\d+\.?\d*)",
            r"price target[:\s]+\$?(\d+\.?\d*)",
            r"目标价[:\s]+\$?(\d+\.?\d*)",
            r"看向[:\s]+\$?(\d+\.?\d*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def _extract_stop_loss(self, text: str) -> Optional[float]:
        """提取止损价格"""
        patterns = [
            r"stop[- ]?loss[:\s]+\$?(\d+\.?\d*)",
            r"止损[:\s]+\$?(\d+\.?\d*)",
            r"sl[:\s]+\$?(\d+\.?\d*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def _extract_position_size(self, text: str) -> Optional[float]:
        """提取仓位百分比"""
        patterns = [
            r"position[:\s]+size[:\s]+(\d+\.?\d*)%",
            r"仓位[:\s]+(\d+\.?\d*)%",
            r"(\d+\.?\d*)%\s+position",
            r"allocate[:\s]+(\d+\.?\d*)%",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    def _extract_time_horizon(self, text: str) -> Optional[str]:
        """提取时间horizon"""
        patterns = {
            r"\bshort[- ]?term\b": "short",
            r"\bmedium[- ]?term\b": "medium",
            r"\blong[- ]?term\b": "long",
            r"\b短期\b": "short",
            r"\b中期\b": "medium",
            r"\b长期\b": "long",
        }

        text_lower = text.lower()
        for pattern, horizon in patterns.items():
            if re.search(pattern, text_lower):
                return horizon

        return None

    def _create_unknown_signal(self, reason: str) -> ProcessedSignal:
        """创建未知信号"""
        return ProcessedSignal(
            signal=TradingSignal.UNKNOWN,
            strength=SignalStrength.UNCERTAIN,
            confidence=0.0,
            reasoning=reason,
            key_factors=[],
        )

    def combine_signals(
        self,
        signals: List[ProcessedSignal],
        method: str = "weighted",  # weighted, majority, unanimous
    ) -> ProcessedSignal:
        """
        合并多个信号

        Args:
            signals: 多个处理后的信号
            method: 合并方法

        Returns:
            合并后的信号
        """
        if not signals:
            return self._create_unknown_signal("No signals to combine")

        if method == "majority":
            return self._majority_vote(signals)
        elif method == "unanimous":
            return self._unanimous_check(signals)
        else:  # weighted
            return self._weighted_combine(signals)

    def _weighted_combine(self, signals: List[ProcessedSignal]) -> ProcessedSignal:
        """加权合并（基于置信度）"""
        # 按信号类型分组
        buy_weight = sum(s.confidence for s in signals if s.signal == TradingSignal.BUY)
        sell_weight = sum(s.confidence for s in signals if s.signal == TradingSignal.SELL)
        hold_weight = sum(s.confidence for s in signals if s.signal == TradingSignal.HOLD)

        # 确定最终信号
        max_weight = max(buy_weight, sell_weight, hold_weight)

        if max_weight == buy_weight:
            signal = TradingSignal.BUY
        elif max_weight == sell_weight:
            signal = TradingSignal.SELL
        else:
            signal = TradingSignal.HOLD

        # 计算平均置信度
        avg_confidence = sum(s.confidence for s in signals) / len(signals)

        # 合并原因
        reasons = [s.reasoning for s in signals if s.reasoning]
        combined_reasoning = " | ".join(reasons[:3])

        # 合并关键因素
        all_factors = []
        for s in signals:
            all_factors.extend(s.key_factors)
        combined_factors = list(set(all_factors))[:5]

        return ProcessedSignal(
            signal=signal,
            strength=self._determine_combined_strength(signals, signal),
            confidence=avg_confidence,
            reasoning=combined_reasoning,
            key_factors=combined_factors,
        )

    def _majority_vote(self, signals: List[ProcessedSignal]) -> ProcessedSignal:
        """多数投票"""
        from collections import Counter

        signal_counts = Counter(s.signal for s in signals)
        most_common = signal_counts.most_common(1)[0][0]

        # 使用该信号的第一个实例作为基础
        for s in signals:
            if s.signal == most_common:
                return s

        return self._create_unknown_signal("No majority")

    def _unanimous_check(self, signals: List[ProcessedSignal]) -> ProcessedSignal:
        """一致性检查（只有所有信号一致时才返回）"""
        if len(signals) == 0:
            return self._create_unknown_signal("No signals")

        first_signal = signals[0].signal
        if all(s.signal == first_signal for s in signals):
            return signals[0]  # 所有信号一致，返回第一个
        else:
            # 信号不一致，返回HOLD
            return ProcessedSignal(
                signal=TradingSignal.HOLD,
                strength=SignalStrength.WEAK,
                confidence=0.3,
                reasoning="信号不一致，建议观望",
                key_factors=["Agent意见分歧"],
            )

    def _determine_combined_strength(
        self,
        signals: List[ProcessedSignal],
        final_signal: TradingSignal,
    ) -> SignalStrength:
        """确定合并后的信号强度"""
        # 只考虑相同信号的强度
        same_signal_strengths = [
            s.strength for s in signals if s.signal == final_signal
        ]

        if not same_signal_strengths:
            return SignalStrength.UNCERTAIN

        # 如果有任何STRONG，则返回STRONG
        if SignalStrength.STRONG in same_signal_strengths:
            return SignalStrength.STRONG

        # 如果有任何MODERATE，则返回MODERATE
        if SignalStrength.MODERATE in same_signal_strengths:
            return SignalStrength.MODERATE

        # 否则返回WEAK
        return SignalStrength.WEAK


# ============================================================================
# 便捷函数
# ============================================================================

def extract_trading_signal(
    decision_text: str,
    agent_name: str = "Unknown",
) -> Tuple[TradingSignal, float]:
    """
    便捷函数：快速提取交易信号和置信度

    Args:
        decision_text: 决策文本
        agent_name: Agent名称

    Returns:
        (信号类型, 置信度)
    """
    processor = SignalProcessor()
    signal_obj = processor.process_signal(decision_text, agent_name)
    return signal_obj.signal, signal_obj.confidence


def process_agent_decision(
    decision_text: str,
    agent_name: str = "Unknown",
    context: Optional[Dict] = None,
) -> ProcessedSignal:
    """
    便捷函数：处理Agent决策

    Args:
        decision_text: 决策文本
        agent_name: Agent名称
        context: 上下文

    Returns:
        处理后的信号
    """
    processor = SignalProcessor()
    return processor.process_signal(decision_text, agent_name, context)
