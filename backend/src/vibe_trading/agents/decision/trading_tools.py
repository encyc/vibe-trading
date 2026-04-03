"""
交易执行工具模块

专注于订单执行层面的量化工具：
- 订单类型选择（市价/限价/分批）
- 仓位大小计算
- 止损止盈设置
- 执行时机优化

注意：入场信号判断由分析师团队和研究员团队负责，
本模块只负责已确定方向后的执行细节。
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单
    ICEBERG = "iceberg"  # 冰山单（大单拆分）
    TWAP = "twap"  # 时间加权平均价格


class PositionSide(str, Enum):
    """仓位方向"""
    LONG = "long"
    SHORT = "short"


class ExecutionStyle(str, Enum):
    """执行风格"""
    IMMEDIATE = "immediate"  # 立即执行（市价单）
    AGGRESSIVE_LIMIT = "aggressive_limit"  # 激进限价（接近市价）
    PATIENT_LIMIT = "patient_limit"  # 耐心限价（等待更好价格）
    SCALED_IN = "scaled_in"  # 分批建仓
    PULLBACK = "pullback"  # 等待回调


@dataclass
class TradingPlan:
    """交易执行计划

    注意：本计划基于已确定的交易方向，
    只负责执行层面的细节。
    """
    symbol: str
    position_side: PositionSide
    direction: str  # LONG/SHORT (由前面阶段确定)
    execution_style: ExecutionStyle  # 执行风格

    # 入场计划
    entry_orders: List[Dict]  # 分批入场订单列表
    total_position_usdt: float
    total_position_coin: float
    leverage: int

    # 出场计划
    stop_loss_orders: List[Dict]  # 止损订单
    take_profit_orders: List[Dict]  # 分批止盈订单

    # 风险管理
    max_loss_usdt: float
    max_loss_pct: float
    risk_reward_ratio: float

    # 可选字段（有默认值）
    trailing_stop_config: Optional[Dict] = None
    execution_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "position_side": self.position_side.value,
            "direction": self.direction,
            "execution_style": self.execution_style.value,
            "entry_orders": self.entry_orders,
            "total_position_usdt": self.total_position_usdt,
            "total_position_coin": self.total_position_coin,
            "leverage": self.leverage,
            "stop_loss_orders": self.stop_loss_orders,
            "take_profit_orders": self.take_profit_orders,
            "max_loss_usdt": self.max_loss_usdt,
            "max_loss_pct": self.max_loss_pct,
            "risk_reward_ratio": self.risk_reward_ratio,
            "execution_notes": self.execution_notes,
        }


@dataclass
class DecisionScorecard:
    """决策评分卡

    由投资组合经理使用，综合评估所有输入后生成。
    """
    # 决策评分
    overall_score: float  # -100到+100
    confidence: float  # 0到1

    # 各维度得分
    technical_score: float  # 技术面得分
    fundamental_score: float  # 基本面得分
    sentiment_score: float  # 情绪面得分
    risk_score: float  # 风险得分

    # 决策建议
    recommended_action: str  # STRONG_BUY/BUY/WEAK_BUY/HOLD/WEAK_SELL/SELL/STRONG_SELL
    position_size_recommendation: str  # large/medium/small/none

    # 支持因素
    supporting_factors: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

    # 决策依据
    rationale: str = ""

    def to_dict(self) -> Dict:
        return {
            "overall_score": self.overall_score,
            "confidence": self.confidence,
            "technical_score": self.technical_score,
            "fundamental_score": self.fundamental_score,
            "sentiment_score": self.sentiment_score,
            "risk_score": self.risk_score,
            "recommended_action": self.recommended_action,
            "position_size_recommendation": self.position_size_recommendation,
            "supporting_factors": self.supporting_factors,
            "risk_factors": self.risk_factors,
            "rationale": self.rationale,
        }


class PositionSizeCalculator:
    """仓位计算器

    基于已确定的交易方向，计算最优仓位大小。
    """

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_preference: str = "moderate",  # conservative/moderate/aggressive
        kelly_fraction: Optional[float] = None,
        current_atr: Optional[float] = None,
    ) -> Dict:
        """
        计算仓位大小

        Args:
            account_balance: 账户余额
            entry_price: 入场价格
            stop_loss_price: 止损价格
            risk_preference: 风险偏好（来自风控团队建议）
            kelly_fraction: 凯利公式建议的仓位比例
            current_atr: 当前ATR

        Returns:
            {
                "position_size_usdt": float,
                "position_size_coin": float,
                "position_size_pct": float,
                "risk_amount_usdt": float,
                "leverage": int,
                "reasoning": str
            }
        """
        # 计算止损距离
        stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price

        # 基于风险偏好的风险百分比
        risk_premium = {
            "conservative": 0.01,  # 1%
            "moderate": 0.02,     # 2%
            "aggressive": 0.03,    # 3%
        }
        base_risk_pct = risk_premium.get(risk_preference, 0.02)

        # 方法1: 固定风险百分比
        risk_amount = account_balance * base_risk_pct

        # 方法2: 基于止损距离计算
        risk_based_size = risk_amount / stop_distance_pct if stop_distance_pct > 0 else 0

        # 方法3: 凯利公式（如果提供）
        kelly_based_size = 0
        if kelly_fraction:
            kelly_based_size = account_balance * kelly_fraction * 0.5  # 使用半凯利

        # 选择仓位大小（取最小值）
        position_size_usdt = min(risk_based_size, kelly_based_size) if kelly_based_size > 0 else risk_based_size

        # 限制最大仓位
        max_position = account_balance * 0.3  # 最大30%仓位
        position_size_usdt = min(position_size_usdt, max_position)

        # 计算杠杆
        required_margin = position_size_usdt / 5  # 假设5倍杠杆最大
        leverage = min(5, int(account_balance / required_margin)) if required_margin > 0 else 1

        # ATR调整（如果有ATR）
        if current_atr and stop_distance_pct > 0:
            atr_ratio = current_atr / entry_price
            if atr_ratio > 0.02:  # 高波动率
                position_size_usdt *= 0.8
                leverage = max(1, leverage - 1)

        position_size_coin = position_size_usdt / entry_price
        position_size_pct = position_size_usdt / account_balance

        return {
            "position_size_usdt": round(position_size_usdt, 2),
            "position_size_coin": round(position_size_coin, 6),
            "position_size_pct": round(position_size_pct * 100, 2),
            "risk_amount_usdt": round(risk_amount, 2),
            "leverage": leverage,
            "stop_distance_pct": round(stop_distance_pct * 100, 2),
            "reasoning": f"基于{risk_preference}风险偏好, 止损距离{stop_distance_pct*100:.1f}%"
        }


class StopLossTakeProfitCalculator:
    """止损止盈计算器

    基于已确定的入场方向，计算止损止盈位置。
    """

    def calculate_levels(
        self,
        entry_price: float,
        position_side: PositionSide,
        atr: Optional[float] = None,
        risk_reward_ratio: float = 2.0,
        volatility_adjusted: bool = True,
    ) -> Dict:
        """
        计算止损止盈价位

        Args:
            entry_price: 入场价格
            position_side: 仓位方向
            atr: ATR波动率
            risk_reward_ratio: 盈亏比
            volatility_adjusted: 是否根据波动率调整

        Returns:
            {
                "stop_loss_price": float,
                "take_profit_price": float,
                "partial_take_profits": List[Dict],
                "trailing_stop_config": Dict,
                "risk_reward_ratio": float,
            }
        """
        # 计算止损
        if atr and volatility_adjusted:
            # ATR-based止损 (2倍ATR)
            stop_distance = atr * 2
        else:
            # 固定百分比止损 (2%)
            stop_distance = entry_price * 0.02

        if position_side == PositionSide.LONG:
            stop_loss_price = entry_price - stop_distance
        else:
            stop_loss_price = entry_price + stop_distance

        # 计算止盈
        profit_distance = stop_distance * risk_reward_ratio

        if position_side == PositionSide.LONG:
            take_profit_price = entry_price + profit_distance
        else:
            take_profit_price = entry_price - profit_distance

        # 计算分批止盈
        partial_profits = []
        if position_side == PositionSide.LONG:
            # 30%目标 (保守止盈)
            partial_profits.append({
                "level": 1,
                "price": entry_price + profit_distance * 0.3,
                "pct": 30,
                "size_pct": 30,
            })
            # 60%目标 (主要止盈)
            partial_profits.append({
                "level": 2,
                "price": entry_price + profit_distance * 0.6,
                "pct": 30,
                "size_pct": 40,
            })
            # 100%目标 (目标止盈)
            partial_profits.append({
                "level": 3,
                "price": entry_price + profit_distance,
                "pct": 30,
                "size_pct": 30,
            })
        else:
            partial_profits.append({
                "level": 1,
                "price": entry_price - profit_distance * 0.3,
                "pct": 30,
                "size_pct": 30,
            })
            partial_profits.append({
                "level": 2,
                "price": entry_price - profit_distance * 0.6,
                "pct": 30,
                "size_pct": 40,
            })
            partial_profits.append({
                "level": 3,
                "price": entry_price - profit_distance,
                "pct": 30,
                "size_pct": 30,
            })

        # 移动止损配置
        trailing_stop_config = {
            "activation_profit": 0.01,  # 1%盈利后激活
            "trail_distance": 0.02,    # 2%跟踪距离
            "update_frequency": "tick",  # 逐tick更新
        }

        return {
            "stop_loss_price": round(stop_loss_price, 2),
            "take_profit_price": round(take_profit_price, 2),
            "partial_take_profits": partial_profits,
            "trailing_stop_config": trailing_stop_config,
            "risk_reward_ratio": risk_reward_ratio,
        }


class ExecutionStrategyCalculator:
    """执行策略计算器

    根据市场状况和交易方向，确定最优的执行策略。
    专注于"如何进场"，而非"是否进场"。
    """

    def determine_execution_style(
        self,
        direction: str,  # LONG/SHORT (由前面阶段确定)
        current_price: float,
        volatility: Optional[float] = None,  # ATR或波动率
        spread_pct: Optional[float] = None,  # 买卖价差百分比
        volume_24h: Optional[float] = None,  # 24小时成交量
        urgency_level: str = "normal",  # low/normal/high (由研究团队建议)
    ) -> Dict:
        """
        确定执行风格

        Args:
            direction: 交易方向 (由前面阶段确定)
            current_price: 当前价格
            volatility: 波动率
            spread_pct: 买卖价差
            volume_24h: 24小时成交量
            urgency_level: 紧急程度

        Returns:
            {
                "execution_style": ExecutionStyle,
                "order_type": OrderType,
                "entry_orders": List[Dict],  # 分批入场计划
                "reasoning": str
            }
        """
        entry_orders = []
        reasoning_parts = []

        # 1. 根据紧急程度决定执行风格
        if urgency_level == "high":
            # 高紧急度：立即执行
            execution_style = ExecutionStyle.IMMEDIATE
            order_type = OrderType.MARKET
            reasoning_parts.append("高紧急度，使用市价单立即入场")
            entry_orders = [{
                "type": "market",
                "pct": 100,
                "note": "立即市价单执行"
            }]

        elif urgency_level == "low":
            # 低紧急度：可以等待更好价格
            if volatility and volatility > 0.03:  # 高波动
                execution_style = ExecutionStyle.SCALED_IN
                order_type = OrderType.LIMIT
                reasoning_parts.append("低紧急度且高波动，分批建仓降低成本")
                # 分3批建仓
                entry_orders = [
                    {"type": "limit", "price_offset_pct": -0.5, "pct": 30, "note": "第一批"},
                    {"type": "limit", "price_offset_pct": -1.0, "pct": 40, "note": "第二批"},
                    {"type": "limit", "price_offset_pct": -1.5, "pct": 30, "note": "第三批"},
                ]
            else:
                execution_style = ExecutionStyle.PATIENT_LIMIT
                order_type = OrderType.LIMIT
                reasoning_parts.append("低紧急度，使用限价单等待更好价格")
                entry_orders = [{
                    "type": "limit",
                    "price_offset_pct": -0.3,  # 略低于市价
                    "pct": 100,
                    "note": "限价单等待成交"
                }]

        else:  # normal
            # 正常紧急度：根据市场状况决定
            if spread_pct and spread_pct > 0.1:  # 价差大
                execution_style = ExecutionStyle.AGGRESSIVE_LIMIT
                order_type = OrderType.LIMIT
                reasoning_parts.append("价差较大，使用激进限价单")
                entry_orders = [{
                    "type": "limit",
                    "price_offset_pct": 0.05,  # 略优于市价
                    "pct": 100,
                    "note": "激进限价单"
                }]
            elif volume_24h and volume_24h < 1000000:  # 流动性差
                execution_style = ExecutionStyle.SCALED_IN
                order_type = OrderType.LIMIT
                reasoning_parts.append("流动性较差，分批建仓减少冲击")
                entry_orders = [
                    {"type": "limit", "price_offset_pct": 0, "pct": 50, "note": "前半仓"},
                    {"type": "limit", "price_offset_pct": -0.2, "pct": 50, "note": "后半仓"},
                ]
            else:
                execution_style = ExecutionStyle.IMMEDIATE
                order_type = OrderType.MARKET
                reasoning_parts.append("市场状况良好，市价单立即执行")
                entry_orders = [{
                    "type": "market",
                    "pct": 100,
                    "note": "市价单"
                }]

        reasoning = "；".join(reasoning_parts)

        return {
            "execution_style": execution_style,
            "order_type": order_type,
            "entry_orders": entry_orders,
            "reasoning": reasoning,
        }

    def build_entry_orders(
        self,
        direction: str,
        current_price: float,
        total_size_coin: float,
        entry_plan: List[Dict],
    ) -> List[Dict]:
        """
        构建具体的入场订单

        Args:
            direction: 交易方向
            current_price: 当前价格
            total_size_coin: 总仓位大小
            entry_plan: 入场计划（从determine_execution_style返回）

        Returns:
            具体的入场订单列表
        """
        orders = []

        for plan in entry_plan:
            order_type = plan["type"]
            pct = plan["pct"]

            if order_type == "market":
                price = current_price
            else:  # limit
                offset_pct = plan.get("price_offset_pct", 0)
                if direction == "LONG":
                    price = current_price * (1 + offset_pct / 100)
                else:
                    price = current_price * (1 - offset_pct / 100)

            size_coin = total_size_coin * pct / 100
            size_usdt = size_coin * price

            orders.append({
                "order_type": order_type,
                "price": round(price, 2),
                "size_coin": round(size_coin, 6),
                "size_usdt": round(size_usdt, 2),
                "pct": pct,
                "note": plan.get("note", ""),
            })

        return orders


class DecisionFramework:
    """决策框架"""

    def __init__(self):
        self._decision_history: List[Dict] = []

    def calculate_decision_scorecard(
        self,
        analyst_reports: Dict[str, str],
        research_recommendation: Dict,
        risk_assessment: Dict[str, str],
        current_market_data: Dict,
    ) -> DecisionScorecard:
        """
        计算决策评分卡

        综合分析师、研究员、风控的所有信息
        """
        # 各维度权重
        weights = {
            "technical": 0.30,
            "fundamental": 0.25,
            "sentiment": 0.20,
            "research": 0.15,
            "risk": 0.10,
        }

        scores = {}
        supporting_factors = []
        risk_factors = []

        # 1. 技术面得分 (从分析师报告)
        tech_report = analyst_reports.get("technical", "")
        if "看涨" in tech_report:
            scores["technical"] = self._extract_score(tech_report, bullish=True)
        elif "看跌" in tech_report:
            scores["technical"] = self._extract_score(tech_report, bullish=False)
        else:
            scores["technical"] = 50

        # 2. 基本面得分
        fund_report = analyst_reports.get("fundamental", "")
        if "看涨" in fund_report:
            scores["fundamental"] = self._extract_score(fund_report, bullish=True)
        elif "看跌" in fund_report:
            scores["fundamental"] = self._extract_score(fund_report, bullish=False)
        else:
            scores["fundamental"] = 50

        # 3. 情绪面得分
        sent_report = analyst_reports.get("sentiment", "")
        if "正面" in sent_report or "贪婪" in sent_report:
            scores["sentiment"] = 60
        elif "负面" in sent_report or "恐惧" in sent_report:
            scores["sentiment"] = 40
        else:
            scores["sentiment"] = 50

        # 4. 研究员建议得分
        rec_action = research_recommendation.get("action", "").upper()
        if rec_action == "BUY":
            scores["research"] = 70
        elif rec_action == "SELL":
            scores["research"] = 30
        else:
            scores["research"] = 50

        # 5. 风险评估得分
        risk_level = risk_assessment.get("risk_level", "medium")
        if risk_level == "low":
            scores["risk"] = 90
        elif risk_level == "medium":
            scores["risk"] = 70
        elif risk_level == "high":
            scores["risk"] = 50
        elif risk_level == "critical":
            scores["risk"] = 20

        # 计算总分
        overall_score = sum(scores[k] * weights[k] for k in scores)

        # 确定推荐行动
        if overall_score >= 70:
            recommended_action = "STRONG_BUY"
            position_size = "large"
        elif overall_score >= 55:
            recommended_action = "BUY"
            position_size = "medium"
        elif overall_score >= 45:
            recommended_action = "WEAK_BUY"
            position_size = "small"
        elif overall_score >= 30:
            recommended_action = "HOLD"
            position_size = "none"
        elif overall_score >= 15:
            recommended_action = "WEAK_SELL"
            position_size = "small"
        elif overall_score < 15:
            recommended_action = "SELL"
            position_size = "medium"
        else:
            recommended_action = "STRONG_SELL"
            position_size = "large"

        # 计算置信度
        confidence = 0.5
        if overall_score >= 70 or overall_score <= 30:
            confidence = 0.8
        elif overall_score >= 55 or overall_score <= 45:
            confidence = 0.6
        else:
            confidence = 0.4

        # 提取支持因素和风险因素
        supporting_factors.extend(self._extract_factors(analyst_reports, research_recommendation))
        risk_factors.extend(self._extract_risks(risk_assessment))

        # 生成理由
        rationale = self._generate_rationale(scores, recommended_action)

        return DecisionScorecard(
            overall_score=round(overall_score, 1),
            confidence=round(confidence, 2),
            technical_score=round(scores.get("technical", 50), 1),
            fundamental_score=round(scores.get("fundamental", 50), 1),
            sentiment_score=round(scores.get("sentiment", 50), 1),
            risk_score=round(scores.get("risk", 50), 1),
            recommended_action=recommended_action,
            position_size_recommendation=position_size,
            supporting_factors=list(set(supporting_factors)),
            risk_factors=list(set(risk_factors)),
            rationale=rationale,
        )

    def _extract_score(self, text: str, bullish: bool) -> float:
        """从文本中提取分数"""
        # 简化实现：基于关键词
        score = 50  # 基础分

        strong_bullish = ["强烈看涨", "明确看涨", "强烈买入", "STRONG_BUY"]
        strong_bearish = ["强烈看跌", "明确看跌", "强烈卖出", "STRONG_SELL"]
        weak_bullish = ["看涨", "买入", "做多", "BUY"]
        weak_bearish = ["看跌", "卖出", "做空", "SELL"]

        if bullish:
            for phrase in strong_bullish:
                if phrase in text:
                    score = 75
                    break
            for phrase in weak_bullish:
                if phrase in text:
                    score = 60
                    break
        else:
            for phrase in strong_bearish:
                if phrase in text:
                    score = 25
                    break
            for phrase in weak_bearish:
                if phrase in text:
                    score = 40
                    break

        return score

    def _extract_factors(self, analyst_reports: Dict, research_recommendation: Dict) -> List[str]:
        """提取支持因素"""
        factors = []

        # 从分析师报告中提取
        for role, report in analyst_reports.items():
            if "强势" in report or "明确" in report:
                factors.append(f"{role}明确支持")
            elif "建议" in report:
                factors.append(f"{role}有积极建议")

        # 从研究建议中提取
        if research_recommendation.get("action"):
            confidence = research_recommendation.get("confidence", 0)
            if confidence > 0.7:
                factors.append(f"研究团队高置信度建议")

        return factors[:5]  # 最多5个

    def _extract_risks(self, risk_assessment: Dict) -> List[str]:
        """提取风险因素"""
        risks = []

        risk_level = risk_assessment.get("risk_level", "")
        if risk_level == "high":
            risks.append("风险等级较高")
        elif risk_level == "critical":
            risks.append("风险等级危险")

        if risk_assessment.get("warnings"):
            for warning in risk_assessment["warnings"]:
                risks.append(warning)

        return risks[:5]

    def _generate_rationale(self, scores: Dict, action: str) -> str:
        """生成决策理由"""
        parts = []

        # 优势方面
        strong_scores = [k for k, v in scores.items() if v >= 60]
        if strong_scores:
            dims = {"technical": "技术面", "fundamental": "基本面", "sentiment": "情绪面"}
            parts.append(f"{'、'.join([dims.get(k, k) for k in strong_scores])}表现强劲")

        # 劣势方面
        weak_scores = [k for k, v in scores.items() if v <= 40]
        if weak_scores:
            dims = {"technical": "技术面", "fundamental": "基本面", "sentiment": "情绪面"}
            parts.append(f"{'、'.join([dims.get(k, k) for k in weak_scores])}表现疲弱")

        if parts:
            rationale = "；".join(parts) + f"，因此建议{action}"
        else:
            rationale = f"综合考虑，建议{action}"

        return rationale

    def record_decision(
        self,
        decision: Dict,
        actual_execution: Optional[Dict] = None,
        outcome: Optional[str] = None,
    ) -> None:
        """记录决策历史"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "decision": decision,
            "actual_execution": actual_execution,
            "outcome": outcome,
        }
        self._decision_history.append(record)
        logger.info(f"Decision recorded: {decision.get('recommended_action')} for {decision.get('symbol')}")

    def get_decision_accuracy(self, days: int = 30) -> float:
        """获取决策准确率"""
        cutoff_date = datetime.now() - timedelta(days=days)

        accurate = 0
        total = 0

        for record in self._decision_history:
            record_time = datetime.fromisoformat(record["timestamp"])
            if record_time >= cutoff_date:
                total += 1
                if record.get("outcome") == "profitable":
                    accurate += 1

        return accurate / total if total > 0 else 0.5
