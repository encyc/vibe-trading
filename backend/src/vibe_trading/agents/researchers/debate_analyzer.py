"""
研究员团队辩论分析工具

提供论点提取、评分、反驳评估和量化裁决功能。
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ArgumentCategory(str, Enum):
    """论点类别"""
    TECHNICAL = "technical"  # 技术面
    FUNDAMENTAL = "fundamental"  # 基本面
    SENTIMENT = "sentiment"  # 情绪面
    MACRO = "macro"  # 宏观经济
    ON_CHAIN = "on_chain"  # 链上数据
    FLOW = "flow"  # 资金流
    RISK = "risk"  # 风险因素
    TIMING = "timing"  # 时机


class ArgumentStrength(str, Enum):
    """论点强度"""
    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class Argument:
    """论点"""
    content: str  # 论点内容
    category: ArgumentCategory  # 类别
    strength: ArgumentStrength  # 强度
    confidence: float  # 置信度 (0-1)
    evidence_based: bool  # 是否有证据支持
    data_mentioned: List[str]  # 提到的数据指标
    key_points: List[str]  # 关键点
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "category": self.category.value,
            "strength": self.strength.value,
            "confidence": self.confidence,
            "evidence_based": self.evidence_based,
            "data_mentioned": self.data_mentioned,
            "key_points": self.key_points,
        }


@dataclass
class Rebuttal:
    """反驳"""
    original_argument: str  # 被反驳的论点
    rebuttal_content: str  # 反驳内容
    effectiveness: str  # 有效性 (effective/partial/ineffective)
    addressed_core: bool  # 是否针对核心论点
    counter_evidence: bool  # 是否提供反证
    logical_fallacy: Optional[str] = None  # 指出的逻辑谬误


@dataclass
class DebateScorecard:
    """辩论评分卡"""
    bull_score: float  # 看涨方得分
    bear_score: float  # 看跌方得分
    total_rounds: int  # 总轮数

    # 看涨方详情
    bull_arguments: List[Argument] = field(default_factory=list)
    bull_strength_count: Dict[ArgumentStrength, int] = field(default_factory=dict)

    # 看跌方详情
    bear_arguments: List[Argument] = field(default_factory=list)
    bear_strength_count: Dict[ArgumentStrength, int] = field(default_factory=dict)

    # 共识度
    consensus_level: float = 0  # 0=完全分歧, 1=完全一致
    dominant_view: str = "neutral"  # bull/bear/neutral

    # 评估维度得分
    dimension_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class InvestmentRecommendation:
    """投资建议"""
    action: str  # BUY/SELL/HOLD
    confidence: float  # 置信度 (0-1)
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str = "short"  # short/medium/long

    # 理由
    rationale: str = ""
    key_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    # 评分
    overall_score: float = 0  # -100 (强烈看跌) 到 +100 (强烈看涨)
    technical_score: float = 0
    fundamental_score: float = 0
    sentiment_score: float = 0


class ArgumentExtractor:
    """论点提取器"""

    # 关键词模式
    CATEGORY_KEYWORDS = {
        ArgumentCategory.TECHNICAL: [
            "rsi", "macd", "ema", "sma", "kdj", "布林带", "bollinger",
            "趋势", "支撑", "阻力", "突破", "背离", "超买", "超卖",
            "金叉", "死叉", "均线", "指标", "形态", "头肩", "双顶",
            "技术面", "k线", "图表", "交易量", "成交量"
        ],
        ArgumentCategory.FUNDAMENTAL: [
            "基本面", "市值", "估值", "收益", "利润", "营收",
            "用户数", "活跃度", "合作伙伴", "产品", "技术",
            "团队", "融资", "上市", " Adoption", "protocol", "whale"
        ],
        ArgumentCategory.SENTIMENT: [
            "情绪", "恐慌", "贪婪", "fear", "greed", "社交媒体",
            "新闻", "利好", "利空", "舆论", "预期", "共识",
            "fomo", "fud", "sentiment", "twitter", "reddit"
        ],
        ArgumentCategory.MACRO: [
            "宏观经济", "利率", "通胀", "cpi", "fed", "ecb",
            "政策", "监管", "法规", "gdp", "失业率", "经济",
            "宏观", "全球", "经济数据", "央行"
        ],
        ArgumentCategory.ON_CHAIN: [
            "链上", "地址", "活跃地址", "交易所", "流入", "流出",
            "hash", "gas", "nft", "defi", "whale", "大户",
            "持仓", "算力", "挖矿", "on-chain"
        ],
        ArgumentCategory.FLOW: [
            "资金", "流入", "流出", "etf", "基金", "机构",
            "散户", "持仓量", "未平仓", "资金费率", "funding",
            "买卖比", "多空", "long", "short", "position"
        ],
        ArgumentCategory.RISK: [
            "风险", "爆仓", "清算", "监管风险", "技术风险",
            "安全", "黑客", "漏洞", "下跌", "崩盘", "回调",
            "止损", "风险", "不确定性"
        ],
        ArgumentCategory.TIMING: [
            "时机", "等待", "确认", "突破", "回调",
            "进场", "出场", "入场", "短期", "中期", "长期",
            "现在", "时机", "等待确认", "谨慎"
        ],
    }

    # 数据指标模式
    DATA_PATTERNS = [
        r"\d+\.?\d*%.*?(USD|USDT|\$)",  # 百分比和价格
        r"\d{1,2},?\d{3}.*?(USD|USDT|\$)",  # 价格
        r"\d+.*?倍",  # 倍数
        r"RSI.*?\d+",  # RSI
        r"MACD",  # MACD
        r"\$[\d,]+",  # 美元价格
        r"[A-Z]{3,6}USDT",  # 交易对
    ]

    def extract_arguments(self, text: str, side: str) -> List[Argument]:
        """
        从文本中提取论点

        Args:
            text: 发言文本
            side: "bull" 或 "bear"

        Returns:
            提取的论点列表
        """
        arguments = []

        # 分割成句子/段落
        sentences = self._split_into_sentences(text)

        for sentence in sentences:
            if not self._is_substantive(sentence):
                continue

            # 识别类别
            category = self._classify_argument(sentence)

            # 评估强度
            strength = self._assess_strength(sentence, side)

            # 检查是否有证据支持
            evidence_based = self._has_evidence(sentence)

            # 提取数据指标
            data_mentioned = self._extract_data_indicators(sentence)

            # 提取关键点
            key_points = self._extract_key_points(sentence)

            # 评估置信度
            confidence = self._assess_confidence(sentence, strength, evidence_based)

            argument = Argument(
                content=sentence.strip(),
                category=category,
                strength=strength,
                confidence=confidence,
                evidence_based=evidence_based,
                data_mentioned=data_mentioned,
                key_points=key_points,
                timestamp=datetime.now()
            )

            arguments.append(argument)

        return arguments

    def _split_into_sentences(self, text: str) -> List[str]:
        """分割成句子"""
        # 按句号、问号、感叹号、分号分割
        sentences = re.split(r'[。！？.!?;；\n]', text)
        # 过滤空句子和太短的句子
        return [s for s in sentences if len(s.strip()) > 10]

    def _is_substantive(self, sentence: str) -> bool:
        """检查句子是否有实质内容"""
        # 过滤掉客套话
        filler_phrases = [
            "我认为", "我觉得", "我建议", "我的观点是",
            "总的来说", "综上所述", "因此", "所以",
            "首先", "其次", "最后", "另外", "此外"
        ]

        sentence = sentence.strip()
        for phrase in filler_phrases:
            if sentence.startswith(phrase):
                remaining = sentence[len(phrase):].strip()
                return len(remaining) > 15

        return len(sentence) > 15

    def _classify_argument(self, sentence: str) -> ArgumentCategory:
        """分类论点"""
        sentence_lower = sentence.lower()

        # 计算每个类别的匹配度
        category_scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in sentence_lower)
            if score > 0:
                category_scores[category] = score

        if not category_scores:
            return ArgumentCategory.TECHNICAL  # 默认

        # 返回得分最高的类别
        return max(category_scores.items(), key=lambda x: x[1])[0]

    def _assess_strength(self, sentence: str, side: str) -> ArgumentStrength:
        """评估论点强度"""
        sentence_lower = sentence.lower()

        # 强强度指标
        very_strong_indicators = [
            "明确", "显著", "大幅", "强烈", "确定", "肯定",
            "clearly", "strongly", "significantly", "undoubtedly",
            "突破", "暴跌", "暴涨", "历史", "新高", "新低"
        ]

        strong_indicators = [
            "已经", "确认", "显示", "表明", "数据",
            "shown", "indicates", "confirmed", "data shows"
        ]

        weak_indicators = [
            "可能", "也许", "或许", "大概", "估计",
            "possibly", "maybe", "might", "could be",
            "有待观察", "需要确认", "不确定"
        ]

        # 计算强度分数
        strength_score = 0
        for indicator in very_strong_indicators:
            if indicator in sentence_lower:
                strength_score += 3
        for indicator in strong_indicators:
            if indicator in sentence_lower:
                strength_score += 2
        for indicator in weak_indicators:
            if indicator in sentence_lower:
                strength_score -= 2

        # 检查是否有具体数字
        if re.search(r'\d+', sentence):
            strength_score += 1

        # 转换为强度等级
        if strength_score >= 4:
            return ArgumentStrength.VERY_STRONG
        elif strength_score >= 2:
            return ArgumentStrength.STRONG
        elif strength_score >= 0:
            return ArgumentStrength.MODERATE
        elif strength_score >= -2:
            return ArgumentStrength.WEAK
        else:
            return ArgumentStrength.VERY_WEAK

    def _has_evidence(self, sentence: str) -> bool:
        """检查是否有证据支持"""
        evidence_indicators = [
            "数据显示", "根据", "如图", "历史", "统计",
            "data shows", "according to", "historically",
            "图表", "指标", "报告", "研报"
        ]

        sentence_lower = sentence.lower()
        return any(indicator in sentence_lower for indicator in evidence_indicators)

    def _extract_data_indicators(self, sentence: str) -> List[str]:
        """提取数据指标"""
        indicators = []

        # 提取百分比
        percentages = re.findall(r'\d+\.?\d*%', sentence)
        indicators.extend(percentages)

        # 提取价格
        prices = re.findall(r'\$?\d{1,2},?\d{3}\.?\d*', sentence)
        indicators.extend(prices)

        # 提取技术指标
        if 'rsi' in sentence.lower():
            rsi_values = re.findall(r'rsi.*?(\d+)', sentence, re.IGNORECASE)
            indicators.extend([f"RSI={v}" for v in rsi_values])

        # 提取其他常见指标
        for keyword in ['macd', 'ema', 'sma', 'atr', 'volume']:
            if keyword in sentence.lower():
                indicators.append(keyword)

        return list(set(indicators))  # 去重

    def _extract_key_points(self, sentence: str) -> List[str]:
        """提取关键点"""
        # 分割关键词组
        # 这里简化处理，可以进一步优化
        words = sentence.split()
        key_words = []

        # 选择有意义的词（长度>=2的中文或英文）
        for word in words:
            word = word.strip('，。！？、,.!?;:()[]{}""''')
            if len(word) >= 2:
                key_words.append(word)

        # 返回前5个关键词
        return key_words[:5]

    def _assess_confidence(
        self,
        sentence: str,
        strength: ArgumentStrength,
        evidence_based: bool
    ) -> float:
        """评估置信度"""
        base_confidence = {
            ArgumentStrength.VERY_STRONG: 0.9,
            ArgumentStrength.STRONG: 0.75,
            ArgumentStrength.MODERATE: 0.5,
            ArgumentStrength.WEAK: 0.3,
            ArgumentStrength.VERY_WEAK: 0.15,
        }

        confidence = base_confidence[strength]

        # 有证据支持增加置信度
        if evidence_based:
            confidence = min(1.0, confidence + 0.15)

        # 有数据指标增加置信度
        if any(pattern in sentence for pattern in ['%', '数据', '指标', '显示']):
            confidence = min(1.0, confidence + 0.1)

        return round(confidence, 2)


class DebateEvaluator:
    """辩论评估器"""

    def __init__(self):
        self.argument_extractor = ArgumentExtractor()

    def evaluate_debate(
        self,
        bull_messages: List[str],
        bear_messages: List[str],
        market_context: Optional[Dict] = None
    ) -> DebateScorecard:
        """
        评估整场辩论

        Args:
            bull_messages: 看涨研究员的所有发言
            bear_messages: 看跌研究员的所有发言
            market_context: 市场上下文

        Returns:
            辩论评分卡
        """
        # 合并所有消息
        bull_text = "\n".join(bull_messages)
        bear_text = "\n".join(bear_messages)

        # 提取论点
        bull_arguments = self.argument_extractor.extract_arguments(bull_text, "bull")
        bear_arguments = self.argument_extractor.extract_arguments(bear_text, "bear")

        # 计算分数
        bull_score = self._calculate_side_score(bull_arguments)
        bear_score = self._calculate_side_score(bear_arguments)

        # 统计强度分布
        bull_strength_count = self._count_strengths(bull_arguments)
        bear_strength_count = self._count_strengths(bear_arguments)

        # 计算共识度
        consensus_level = self._calculate_consensus(bull_arguments, bear_arguments)

        # 确定主导观点
        if bull_score > bear_score + 10:
            dominant_view = "bull"
        elif bear_score > bull_score + 10:
            dominant_view = "bear"
        else:
            dominant_view = "neutral"

        # 评估各维度得分
        dimension_scores = self._evaluate_dimensions(bull_arguments, bear_arguments)

        return DebateScorecard(
            bull_score=bull_score,
            bear_score=bear_score,
            total_rounds=max(len(bull_messages), len(bear_messages)),
            bull_arguments=bull_arguments,
            bull_strength_count=bull_strength_count,
            bear_arguments=bear_arguments,
            bear_strength_count=bear_strength_count,
            consensus_level=consensus_level,
            dominant_view=dominant_view,
            dimension_scores=dimension_scores
        )

    def _calculate_side_score(self, arguments: List[Argument]) -> float:
        """计算一方得分"""
        if not arguments:
            return 0.0

        total_score = 0
        for arg in arguments:
            # 强度权重
            strength_weights = {
                ArgumentStrength.VERY_STRONG: 10,
                ArgumentStrength.STRONG: 7,
                ArgumentStrength.MODERATE: 4,
                ArgumentStrength.WEAK: 2,
                ArgumentStrength.VERY_WEAK: 1,
            }

            weight = strength_weights[arg.strength]

            # 置信度调整
            adjusted_weight = weight * arg.confidence

            # 有证据加成
            if arg.evidence_based:
                adjusted_weight *= 1.2

            total_score += adjusted_weight

        # 归一化到0-100
        max_possible = len(arguments) * 10 * 1.2
        normalized = min(100, (total_score / max_possible) * 100) if max_possible > 0 else 0

        return round(normalized, 2)

    def _count_strengths(self, arguments: List[Argument]) -> Dict[ArgumentStrength, int]:
        """统计强度分布"""
        counts = {strength: 0 for strength in ArgumentStrength}
        for arg in arguments:
            counts[arg.strength] += 1
        return counts

    def _calculate_consensus(
        self,
        bull_arguments: List[Argument],
        bear_arguments: List[Argument]
    ) -> float:
        """
        计算共识度

        0 = 完全分歧, 1 = 完全一致
        """
        if not bull_arguments or not bear_arguments:
            return 0.0

        # 计算类别相似度
        bull_categories = set(arg.category for arg in bull_arguments)
        bear_categories = set(arg.category for arg in bear_arguments)

        # 如果讨论完全不同的维度，共识度低
        if not bull_categories & bear_categories:
            return 0.1

        # 计算类别重叠度
        overlap = len(bull_categories & bear_categories)
        total = len(bull_categories | bear_categories)
        category_similarity = overlap / total if total > 0 else 0

        # 计算强度相似度
        bull_avg_confidence = sum(arg.confidence for arg in bull_arguments) / len(bull_arguments)
        bear_avg_confidence = sum(arg.confidence for arg in bear_arguments) / len(bear_arguments)
        confidence_similarity = 1 - abs(bull_avg_confidence - bear_avg_confidence)

        # 综合共识度
        consensus = (category_similarity + confidence_similarity) / 2

        return round(consensus, 2)

    def _evaluate_dimensions(
        self,
        bull_arguments: List[Argument],
        bear_arguments: List[Argument]
    ) -> Dict[str, Dict[str, float]]:
        """评估各维度得分"""
        dimensions = {
            "technical": {"bull": 0, "bear": 0},
            "fundamental": {"bull": 0, "bear": 0},
            "sentiment": {"bull": 0, "bear": 0},
            "macro": {"bull": 0, "bear": 0},
            "risk": {"bull": 0, "bear": 0},
        }

        # 统计各维度各方的论点强度
        for arg in bull_arguments:
            if arg.category.value in dimensions:
                strength_val = {
                    ArgumentStrength.VERY_STRONG: 10,
                    ArgumentStrength.STRONG: 7,
                    ArgumentStrength.MODERATE: 4,
                    ArgumentStrength.WEAK: 2,
                    ArgumentStrength.VERY_WEAK: 1,
                }[arg.strength]
                dimensions[arg.category.value]["bull"] += strength_val * arg.confidence

        for arg in bear_arguments:
            if arg.category.value in dimensions:
                strength_val = {
                    ArgumentStrength.VERY_STRONG: 10,
                    ArgumentStrength.STRONG: 7,
                    ArgumentStrength.MODERATE: 4,
                    ArgumentStrength.WEAK: 2,
                    ArgumentStrength.VERY_WEAK: 1,
                }[arg.strength]
                dimensions[arg.category.value]["bear"] += strength_val * arg.confidence

        # 归一化
        for dim, scores in dimensions.items():
            total = scores["bull"] + scores["bear"]
            if total > 0:
                scores["bull"] = round(scores["bull"] / total * 100, 1)
                scores["bear"] = round(scores["bear"] / total * 100, 1)

        return dimensions


class RecommendationEngine:
    """建议引擎"""

    def __init__(self):
        self.debate_evaluator = DebateEvaluator()

    def generate_recommendation(
        self,
        scorecard: DebateScorecard,
        analyst_reports: Dict[str, str],
        market_data: Optional[Dict] = None
    ) -> InvestmentRecommendation:
        """
        生成投资建议

        Args:
            scorecard: 辩论评分卡
            analyst_reports: 分析师报告
            market_data: 市场数据

        Returns:
            投资建议
        """
        # 计算总分
        score_diff = scorecard.bull_score - scorecard.bear_score

        # 转换为-100到+100的分数
        overall_score = score_diff

        # 确定行动
        if overall_score > 30:
            action = "BUY"
            confidence = min(1.0, overall_score / 100)
        elif overall_score < -30:
            action = "SELL"
            confidence = min(1.0, abs(overall_score) / 100)
        else:
            action = "HOLD"
            confidence = 0.5

        # 从维度得分中提取各分数
        dimension_scores = scorecard.dimension_scores
        technical_score = (dimension_scores.get("technical", {}).get("bull", 50) -
                           dimension_scores.get("technical", {}).get("bear", 50) - 50) * 2
        fundamental_score = (dimension_scores.get("fundamental", {}).get("bull", 50) -
                             dimension_scores.get("fundamental", {}).get("bear", 50) - 50) * 2
        sentiment_score = (dimension_scores.get("sentiment", {}).get("bull", 50) -
                            dimension_scores.get("sentiment", {}).get("bear", 50) - 50) * 2

        # 收集关键因素
        key_factors = self._extract_key_factors(scorecard, analyst_reports)
        risk_factors = self._extract_risk_factors(scorecard, analyst_reports)

        # 生成理由
        rationale = self._generate_rationale(scorecard, action, overall_score)

        return InvestmentRecommendation(
            action=action,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_factors=key_factors,
            risk_factors=risk_factors,
            overall_score=overall_score,
            technical_score=round(technical_score, 1),
            fundamental_score=round(fundamental_score, 1),
            sentiment_score=round(sentiment_score, 1),
        )

    def _extract_key_factors(
        self,
        scorecard: DebateScorecard,
        analyst_reports: Dict[str, str]
    ) -> List[str]:
        """提取关键因素"""
        factors = []

        # 从强势论点中提取
        strong_bull_args = [arg for arg in scorecard.bull_arguments
                           if arg.strength in [ArgumentStrength.STRONG, ArgumentStrength.VERY_STRONG]]
        strong_bear_args = [arg for arg in scorecard.bear_arguments
                           if arg.strength in [ArgumentStrength.STRONG, ArgumentStrength.VERY_STRONG]]

        # 看涨关键因素
        if scorecard.dominant_view in ["bull", "neutral"]:
            for arg in strong_bull_args[:3]:  # 最多3个
                factors.append(f"看涨: {arg.content[:50]}...")

        # 看跌关键因素
        if scorecard.dominant_view in ["bear", "neutral"]:
            for arg in strong_bear_args[:3]:
                factors.append(f"看跌: {arg.content[:50]}...")

        return factors

    def _extract_risk_factors(
        self,
        scorecard: DebateScorecard,
        analyst_reports: Dict[str, str]
    ) -> List[str]:
        """提取风险因素"""
        risks = []

        # 从风险类论点中提取
        risk_args = [arg for arg in scorecard.bull_arguments + scorecard.bear_arguments
                    if arg.category == ArgumentCategory.RISK]

        for arg in risk_args:
            risks.append(arg.content[:60])

        # 从共识度低的情况中提取风险
        if scorecard.consensus_level < 0.3:
            risks.append("市场观点分歧严重，不确定性较高")

        return risks

    def _generate_rationale(
        self,
        scorecard: DebateScorecard,
        action: str,
        overall_score: float
    ) -> str:
        """生成理由说明"""
        rationale_parts = []

        # 主导观点
        if scorecard.dominant_view == "bull":
            rationale_parts.append(f"看涨观点更具说服力（{scorecard.bull_score:.1f} vs {scorecard.bear_score:.1f}）")
        elif scorecard.dominant_view == "bear":
            rationale_parts.append(f"看跌观点更具说服力（{scorecard.bear_score:.1f} vs {scorecard.bull_score:.1f}）")
        else:
            rationale_parts.append(f"多空观点势均力敌（{scorecard.bull_score:.1f} vs {scorecard.bear_score:.1f}）")

        # 共识度
        if scorecard.consensus_level > 0.7:
            rationale_parts.append("双方在某些关键点上达成共识")
        elif scorecard.consensus_level < 0.3:
            rationale_parts.append("双方观点分歧较大")

        # 强势论点数量
        bull_strong = sum(1 for s in scorecard.bull_strength_count.values() if s > 0)
        bear_strong = sum(1 for s in scorecard.bear_strength_count.values() if s > 0)
        rationale_parts.append(f"看涨提供{bull_strong}类论点，看跌提供{bear_strong}类论点")

        return "；".join(rationale_parts)
