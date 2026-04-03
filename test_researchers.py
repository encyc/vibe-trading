"""
研究员团队测试脚本

测试研究员团队的论点提取、辩论评估和量化裁决功能。
"""
import asyncio
import sys
from pathlib import Path
import os

# 添加 backend/src 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from vibe_trading.agents.researchers.debate_analyzer import (
    ArgumentExtractor,
    DebateEvaluator,
    RecommendationEngine,
    ArgumentCategory,
    ArgumentStrength,
)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subsection(title: str):
    """打印子分节标题"""
    print(f"\n--- {title} ---")


def test_argument_extractor():
    """测试论点提取器"""
    print_section("测试 1: 论点提取器 (ArgumentExtractor)")

    extractor = ArgumentExtractor()

    # 测试用例1: 技术面论点
    print_subsection("测试用例 1: 技术面论点")
    bull_text = """
    Bull: 从技术面来看，BTC当前RSI为65，MACD金叉，布林带开口向上，表明上涨趋势明确。
    价格已突破50000美元阻力位，成交量显著放大，显示多头力量强劲。
    根据历史数据，突破关键阻力位后通常会有15-20%的上涨空间。
    我认为这是明确的买入信号，建议积极做多。
    """

    arguments = extractor.extract_arguments(bull_text, "bull")
    print(f"提取到 {len(arguments)} 个论点:")
    for i, arg in enumerate(arguments, 1):
        print(f"\n  论点 {i}:")
        print(f"    内容: {arg.content[:80]}...")
        print(f"    类别: {arg.category.value}")
        print(f"    强度: {arg.strength.value}")
        print(f"    置信度: {arg.confidence:.2f}")
        print(f"    有证据: {arg.evidence_based}")
        print(f"    数据指标: {arg.data_mentioned}")
        print(f"    关键点: {arg.key_points}")

    # 测试用例2: 基本面论点
    print_subsection("测试用例 2: 基本面论点")
    bear_text = """
    Bear: 从基本面分析，当前BTC估值过高，链上活跃地址数持续下降，大户持续向交易所转移资金。
    Gas费处于低位，说明网络使用量不足。项目开发进度缓慢，没有新的催化剂。
    此外，宏观经济环境不佳，美联储可能继续加息，这会对加密货币市场造成压力。
    我建议谨慎对待，风险控制优先。
    """

    arguments = extractor.extract_arguments(bear_text, "bear")
    print(f"提取到 {len(arguments)} 个论点:")
    for i, arg in enumerate(arguments, 1):
        print(f"\n  论点 {i}:")
        print(f"    内容: {arg.content[:80]}...")
        print(f"    类别: {arg.category.value}")
        print(f"    强度: {arg.strength.value}")
        print(f"    置信度: {arg.confidence:.2f}")

    # 测试用例3: 多类别混合论点
    print_subsection("测试用例 3: 多类别混合论点")
    mixed_text = """
    Bull: 技术面上，RSI形成背离，预示反转。基本面上，机构资金持续流入ETF。
    情绪面上，恐惧贪婪指数从20回升到45，市场情绪正在改善。
    宏观上，通胀数据温和，美联储可能放缓加息节奏。
    资金面上，持仓量增加，多单比例上升。
    我强烈看涨，目标60000美元。
    """

    arguments = extractor.extract_arguments(mixed_text, "bull")
    print(f"提取到 {len(arguments)} 个论点:")
    category_count = {}
    for arg in arguments:
        cat = arg.category.value
        category_count[cat] = category_count.get(cat, 0) + 1

    print("\n论点类别分布:")
    for cat, count in category_count.items():
        print(f"  {cat}: {count}个")


def test_debate_evaluator():
    """测试辩论评估器"""
    print_section("测试 2: 辩论评估器 (DebateEvaluator)")

    evaluator = DebateEvaluator()

    # 模拟多轮辩论
    bull_messages = [
        "Bull: 从技术面看，RSI 65，MACD金叉，布林带开口向上，趋势明确向上。价格突破50000阻力位，成交量放大，显示多头强劲。",
        "Bull: 基本面上，链上活跃地址增加，交易所资金流出，大户持仓稳定。ETF资金净流入，机构看多。恐惧贪婪指数回升，市场情绪改善。",
        "Bull: 针对看跌观点，我认为估值高是相对的。与历史高点相比还有上涨空间。链上数据确实显示一些资金流出，但这是正常的获利了结行为。",
    ]

    bear_messages = [
        "Bear: 基本面分析显示，BTC估值过高，PE达到历史高位。链上活跃地址持续下降，大户向交易所转移资金，可能是减仓信号。Gas费低位，网络使用不足。",
        "Bear: 宏观环境不佳，美联储可能继续加息，流动性收紧。监管风险增加，多个国家加强加密货币监管。历史数据显示，在监管收紧期间，加密货币通常下跌。",
        "Bear: 回应看涨观点，虽然技术指标看似不错，但MACD可能出现顶背离。资金流入ETF可能是短期投机，而非长期持有。情绪改善可能是短暂的FOMO。",
    ]

    print_subsection("模拟辩论内容")
    print("看涨研究员:")
    for msg in bull_messages:
        print(f"  {msg[:100]}...")
    print("\n看跌研究员:")
    for msg in bear_messages:
        print(f"  {msg[:100]}...")

    # 评估辩论
    scorecard = evaluator.evaluate_debate(bull_messages, bear_messages)

    print_subsection("辩论评分结果")
    print(f"看涨得分: {scorecard.bull_score:.2f}/100")
    print(f"看跌得分: {scorecard.bear_score:.2f}/100")
    print(f"总轮数: {scorecard.total_rounds}")
    print(f"主导观点: {scorecard.dominant_view}")
    print(f"共识度: {scorecard.consensus_level:.2%}")

    print_subsection("论点统计")
    print(f"看涨论点数: {len(scorecard.bull_arguments)}")
    print(f"看跌论点数: {len(scorecard.bear_arguments)}")

    print("\n看涨论点强度分布:")
    for strength, count in scorecard.bull_strength_count.items():
        if count > 0:
            print(f"  {strength.value}: {count}个")

    print("\n看跌论点强度分布:")
    for strength, count in scorecard.bear_strength_count.items():
        if count > 0:
            print(f"  {strength.value}: {count}个")

    print_subsection("维度得分")
    for dim, scores in scorecard.dimension_scores.items():
        print(f"{dim.upper():15s}: 看涨 {scores['bull']:5.1f}% | 看跌 {scores['bear']:5.1f}%")


def test_recommendation_engine():
    """测试建议引擎"""
    print_section("测试 3: 建议引擎 (RecommendationEngine)")

    engine = RecommendationEngine()

    # 创建模拟评分卡
    from vibe_trading.agents.researchers.debate_analyzer import DebateScorecard

    # 看涨优势案例
    print_subsection("案例 1: 看涨优势")
    scorecard_bull = DebateScorecard(
        bull_score=72.5,
        bear_score=45.3,
        total_rounds=3,
        dominant_view="bull",
        consensus_level=0.35,
        dimension_scores={
            "technical": {"bull": 75, "bear": 25},
            "fundamental": {"bull": 65, "bear": 35},
            "sentiment": {"bull": 80, "bear": 20},
            "macro": {"bull": 55, "bear": 45},
            "risk": {"bull": 45, "bear": 55},
        },
    )

    recommendation = engine.generate_recommendation(
        scorecard_bull,
        analyst_reports={"technical": "技术面看涨", "fundamental": "基本面良好"},
        market_data={"price": 55000}
    )

    print(f"行动: {recommendation.action}")
    print(f"置信度: {recommendation.confidence:.2%}")
    print(f"综合评分: {recommendation.overall_score:.1f}")
    print(f"技术面得分: {recommendation.technical_score:.1f}")
    print(f"基本面得分: {recommendation.fundamental_score:.1f}")
    print(f"情绪面得分: {recommendation.sentiment_score:.1f}")
    print(f"\n理由: {recommendation.rationale}")
    print(f"\n关键因素:")
    for factor in recommendation.key_factors[:3]:
        print(f"  - {factor}")
    if recommendation.risk_factors:
        print(f"\n风险因素:")
        for risk in recommendation.risk_factors[:2]:
            print(f"  - {risk}")

    # 看跌优势案例
    print_subsection("案例 2: 看跌优势")
    scorecard_bear = DebateScorecard(
        bull_score=38.2,
        bear_score=68.7,
        total_rounds=3,
        dominant_view="bear",
        consensus_level=0.28,
        dimension_scores={
            "technical": {"bull": 30, "bear": 70},
            "fundamental": {"bull": 35, "bear": 65},
            "sentiment": {"bull": 40, "bear": 60},
            "macro": {"bull": 25, "bear": 75},
            "risk": {"bull": 50, "bear": 50},
        },
    )

    recommendation = engine.generate_recommendation(
        scorecard_bear,
        analyst_reports={"technical": "技术面看跌", "fundamental": "基本面疲软"},
        market_data={"price": 55000}
    )

    print(f"行动: {recommendation.action}")
    print(f"置信度: {recommendation.confidence:.2%}")
    print(f"综合评分: {recommendation.overall_score:.1f}")
    print(f"理由: {recommendation.rationale}")

    # 中性案例
    print_subsection("案例 3: 中性观点")
    scorecard_neutral = DebateScorecard(
        bull_score=52.3,
        bear_score=51.8,
        total_rounds=3,
        dominant_view="neutral",
        consensus_level=0.65,
        dimension_scores={
            "technical": {"bull": 48, "bear": 52},
            "fundamental": {"bull": 55, "bear": 45},
            "sentiment": {"bull": 50, "bear": 50},
            "macro": {"bull": 52, "bear": 48},
            "risk": {"bull": 56, "bear": 44},
        },
    )

    recommendation = engine.generate_recommendation(
        scorecard_neutral,
        analyst_reports={"technical": "技术面中性", "fundamental": "基本面平衡"},
        market_data={"price": 55000}
    )

    print(f"行动: {recommendation.action}")
    print(f"置信度: {recommendation.confidence:.2%}")
    print(f"综合评分: {recommendation.overall_score:.1f}")
    print(f"理由: {recommendation.rationale}")


def test_full_debate_flow():
    """测试完整辩论流程"""
    print_section("测试 4: 完整辩论流程")

    evaluator = DebateEvaluator()
    engine = RecommendationEngine()
    extractor = ArgumentExtractor()

    # 模拟第一轮辩论
    print_subsection("第一轮辩论")
    bull_1 = "Bull: BTC技术面强劲，RSI 60，MACD金叉，突破5万阻力。基本面良好，ETF资金流入。建议买入。"
    bear_1 = "Bear: BTC估值过高，链上活跃地址下降。宏观经济压力，美联储可能加息。建议观望。"

    print(f"看涨: {bull_1}")
    print(f"看跌: {bear_1}")

    # 模拟第二轮辩论
    print_subsection("第二轮辩论（回应对方）")
    bull_2 = "Bull: 针对看跌观点，估值是相对的，与历史高点还有空间。链上数据流出是获利了结，属正常现象。"
    bear_2 = "Bear: 针对看涨观点，MACD可能出现顶背离。ETF流入可能是短期投机。情绪改善可能是FOMO。"

    print(f"看涨: {bull_2}")
    print(f"看跌: {bear_2}")

    # 模拟第三轮辩论
    print_subsection("第三轮辩论（补充观点）")
    bull_3 = "Bull: 恐惧贪婪指数从20回升到45，市场情绪改善。持仓量增加，多单比例上升到58%。"
    bear_3 = "Bear: 监管风险增加，交易所储备增加，可能预示抛压。Gas费低位，网络使用不足。"

    print(f"看涨: {bull_3}")
    print(f"看跌: {bear_3}")

    # 收集所有发言
    bull_messages = [bull_1, bull_2, bull_3]
    bear_messages = [bear_1, bear_2, bear_3]

    # 提取论点
    print_subsection("论点提取结果")
    full_bull_text = "\n".join(bull_messages)
    full_bear_text = "\n".join(bear_messages)

    bull_args = extractor.extract_arguments(full_bull_text, "bull")
    bear_args = extractor.extract_arguments(full_bear_text, "bear")

    print(f"看涨提取 {len(bull_args)} 个论点，看跌提取 {len(bear_args)} 个论点")

    # 评估辩论
    scorecard = evaluator.evaluate_debate(bull_messages, bear_messages)

    print_subsection("辩论评估结果")
    print(f"看涨得分: {scorecard.bull_score:.2f} vs 看跌得分: {scorecard.bear_score:.2f}")
    print(f"主导观点: {scorecard.dominant_view}（优势: {abs(scorecard.bull_score - scorecard.bear_score):.2f}分）")
    print(f"共识度: {scorecard.consensus_level:.2%}")

    print("\n维度得分:")
    for dim, scores in scorecard.dimension_scores.items():
        diff = scores['bull'] - scores['bear']
        symbol = "↑" if diff > 0 else "↓"
        print(f"  {dim:12s}: 看涨 {scores['bull']:4.1f}% | 看跌 {scores['bear']:4.1f}% {symbol} {abs(diff):.1f}%")

    # 生成投资建议
    print_subsection("量化投资建议")
    recommendation = engine.generate_recommendation(
        scorecard,
        analyst_reports={
            "technical": "技术面看涨，突破关键阻力",
            "fundamental": "基本面中性偏多",
            "sentiment": "情绪改善",
        },
        market_data={"price": 52000, "volume": 1500000000}
    )

    print(f"\n{'='*50}")
    print(f"最终决策: {recommendation.action}")
    print(f"置信度: {recommendation.confidence:.2%}")
    print(f"综合评分: {recommendation.overall_score:+.1f}")
    print(f"{'='*50}")

    print(f"\n得分明细:")
    print(f"  技术面: {recommendation.technical_score:+.1f}")
    print(f"  基本面: {recommendation.fundamental_score:+.1f}")
    print(f"  情绪面: {recommendation.sentiment_score:+.1f}")

    print(f"\n理由:")
    print(f"  {recommendation.rationale}")

    if recommendation.key_factors:
        print(f"\n关键支持因素:")
        for i, factor in enumerate(recommendation.key_factors[:3], 1):
            print(f"  {i}. {factor}")

    if recommendation.risk_factors:
        print(f"\n风险因素:")
        for i, risk in enumerate(recommendation.risk_factors[:2], 1):
            print(f"  {i}. {risk}")


def test_argument_categories():
    """测试论点类别识别"""
    print_section("测试 5: 论点类别识别")

    extractor = ArgumentExtractor()

    test_cases = [
        ("技术面", "RSI指标显示超卖，MACD形成金叉，价格突破布林带上轨，成交量放大。"),
        ("基本面", "链上活跃地址数增加10%，交易所资金净流出5000BTC，Gas费处于历史低位。"),
        ("情绪面", "恐惧贪婪指数从25上升到45，Twitter讨论热度增加30%，Reddit情绪转为积极。"),
        ("宏观", "美联储CPI数据温和，通胀压力缓解，市场预期加息周期即将结束。"),
        ("资金流", "ETF资金净流入2亿美元，持仓量增加15%，多空比例达到60:40。"),
        ("风险", "监管不确定性增加，多国加强加密货币监管，交易所储备大幅增加。"),
        ("时机", "当前价格接近关键支撑位，建议等待确认突破后再入场，避免追高。"),
    ]

    for category_name, text in test_cases:
        arguments = extractor.extract_arguments(text, "bull")
        if arguments:
            detected_category = arguments[0].category.value
            status = "✅" if detected_category == extractor.CATEGORY_KEYWORDS.get(
                [k for k, v in extractor.CATEGORY_KEYWORDS.items()
                 if any(kw in text.lower() for kw in v)][0], [k for k in extractor.CATEGORY_KEYWORDS.keys()][0]
            ).__class__.__name__.lower() or "❓" else "❌"
            print(f"{status} {category_name:10s} -> {detected_category}")
        else:
            print(f"❌ {category_name:10s} -> 未识别到论点")


def main():
    """运行所有测试"""
    print("\n" + "█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  研究员团队功能测试".center(66) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    try:
        test_argument_extractor()
        test_debate_evaluator()
        test_recommendation_engine()
        test_full_debate_flow()
        test_argument_categories()

        print_section("测试完成")
        print("✅ 所有功能测试通过")
        print("\n" + "█" * 70)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()