"""
研究员团队辩论分析测试脚本

测试论点提取、辩论评分、量化裁决等功能。
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vibe_trading.agents.researchers.debate_analyzer import (
    ArgumentExtractor,
    DebateEvaluator,
    RecommendationEngine,
    ArgumentCategory,
    ArgumentStrength,
)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_argument_extractor():
    """测试论点提取器"""
    print_section("测试 1: 论点提取器")

    extractor = ArgumentExtractor()

    # 看涨发言示例
    bull_speech = """
    Bull: 技术面显示强烈的上涨信号。RSI为55，处于中性偏多区域，MACD刚刚形成金叉，
    这是一个非常明确的看涨信号。布林带方面，价格已经突破中轨并向中轨上方运行。
    从成交量来看，最近三天成交量明显放大，说明资金在持续流入。
    基本面方面，该项目的活跃地址数在过去一个月增长了20%，这表明用户采用率在快速提升。
    此外，该项目即将推出主网上线，这通常是一个强大的催化剂。
    """

    # 看跌发言示例
    bear_speech = """
    Bear: 技术指标显示明显的超买信号。RSI已经达到68，处于严重超买区域，
    MACD虽然金叉但出现了顶背离，这通常是趋势反转的前兆。
    从价格走势来看，虽然在上升通道中，但已经接近关键阻力位53000 USDT，
    前两次在此位置都出现了大幅回调。
    基本面方面，虽然用户增长不错，但估值已经非常高昂，
    市值排名前5，但实际收入和利润远不如排名靠前的项目。
    情绪方面，Fear & Greed指数达到75（贪婪），散户FOMO情绪严重，
    Twitter上全是暴富故事，这是典型的顶部信号。
    """

    print("\n--- 分析看涨发言 ---")
    bull_args = extractor.extract_arguments(bull_speech, "bull")
    print(f"提取到 {len(bull_args)} 个论点:")
    for i, arg in enumerate(bull_args, 1):
        print(f"\n  论点 {i}:")
        print(f"    内容: {arg.content[:60]}...")
        print(f"    类别: {arg.category.value}")
        print(f"    强度: {arg.strength.value}")
        print(f"    置信度: {arg.confidence:.2f}")
        print(f"    有证据: {'是' if arg.evidence_based else '否'}")
        if arg.data_mentioned:
            print(f"    数据: {', '.join(arg.data_mentioned)}")

    print("\n--- 分析看跌发言 ---")
    bear_args = extractor.extract_arguments(bear_speech, "bear")
    print(f"提取到 {len(bear_args)} 个论点:")
    for i, arg in enumerate(bear_args, 1):
        print(f"\n  论点 {i}:")
        print(f"    内容: {arg.content[:60]}...")
        print(f"    类别: {arg.category.value}")
        print(f"    强度: {arg.strength.value}")
        print(f"    置信度: {arg.confidence:.2f}")

    # 统计论点分布
    print("\n--- 论点分布统计 ---")
    bull_summary = {
        "total": len(bull_args),
        "by_category": {},
        "by_strength": {},
    }
    for arg in bull_args:
        bull_summary["by_category"][arg.category.value] = bull_summary["by_category"].get(arg.category.value, 0) + 1
        bull_summary["by_strength"][arg.strength.value] = bull_summary["by_strength"].get(arg.strength.value, 0) + 1

    print(f"看涨论点总数: {bull_summary['total']}")
    print(f"按类别: {bull_summary['by_category']}")
    print(f"按强度: {bull_summary['by_strength']}")


def test_debate_evaluator():
    """测试辩论评估器"""
    print_section("测试 2: 辩论评估器")

    evaluator = DebateEvaluator()

    # 模拟多轮辩论
    bull_messages = [
        "Bull: 技术面显示RSI为55，MACD金叉，这是强烈的看涨信号。",
        "Bull: 成交量持续放大，资金流入明显。",
        "Bull: 基本面强劲，活跃地址增长20%，主网上线在即。",
        "Bull: 针对Bear提到的估值问题，实际上相比收入增速，估值并不算高。",
        "Bull: Fear & Greed指数75确实偏高，但这是牛市初期的典型特征。",
    ]

    bear_messages = [
        "Bear: RSI达到68严重超买，MACD顶背离是反转信号。",
        "Bear: 价格接近关键阻力位53000，前两次在此都大幅回调。",
        "Bear: 估值过高，市值前5但收入远不如排名靠前的项目。",
        "Bull提到的技术指标都是滞后指标，不能预测未来。",
        "Bear: 情绪贪婪指数75，散户FOMO严重，这是顶部信号。",
    ]

    print("\n--- 执行辩论评估 ---")
    scorecard = evaluator.evaluate_debate(
        bull_messages=bull_messages,
        bear_messages=bear_messages,
        market_context={"symbol": "BTCUSDT", "price": 52000}
    )

    print(f"\n=== 辩论结果 ===")
    print(f"看涨得分: {scorecard.bull_score:.1f}/100")
    print(f"看跌得分: {scorecard.bear_score:.1f}/100")
    print(f"主导观点: {scorecard.dominant_view}")
    print(f"共识度: {scorecard.consensus_level:.1%}")

    print(f"\n--- 看涨论点统计 ---")
    print(f"论点数量: {len(scorecard.bull_arguments)}")
    print(f"按强度分布: {scorecard.bull_strength_count}")

    print(f"\n--- 看跌论点统计 ---")
    print(f"论点数量: {len(scorecard.bear_arguments)}")
    print(f"按强度分布: {scorecard.bear_strength_count}")

    print(f"\n--- 维度得分 ---")
    for dim, scores in scorecard.dimension_scores.items():
        print(f"{dim.upper()}: 看涨 {scores['bull']:.1f}% vs 看跌 {scores['bear']:.1f}%")


def test_recommendation_engine():
    """测试建议引擎"""
    print_section("测试 3: 投资建议引擎")

    # 创建一个模拟评分卡
    from vibe_trading.agents.researchers.debate_analyzer import DebateScorecard

    scorecard = DebateScorecard(
        bull_score=65.5,
        bear_score=42.3,
        total_rounds=3,
        bull_arguments=[],
        bear_arguments=[],
        consensus_level=0.35,
        dominant_view="bull",
        dimension_scores={
            "technical": {"bull": 60, "bear": 40},
            "fundamental": {"bull": 70, "bear": 30},
            "sentiment": {"bull": 55, "bear": 45},
            "macro": {"bull": 50, "bear": 50},
            "risk": {"bull": 40, "bear": 60},
        }
    )

    analyst_reports = {
        "technical": "技术分析师: 看涨，金叉形态",
        "fundamental": "基本面分析师: 看涨，用户增长强劲",
        "sentiment": "情绪分析师: 中性，情绪偏多",
    }

    engine = RecommendationEngine()

    print("\n--- 生成投资建议 ---")
    recommendation = engine.generate_recommendation(
        scorecard=scorecard,
        analyst_reports=analyst_reports,
        market_data={"symbol": "BTCUSDT", "price": 52000}
    )

    print(f"\n=== 投资建议 ===")
    print(f"行动: {recommendation.action}")
    print(f"置信度: {recommendation.confidence:.1%}")
    print(f"总分: {recommendation.overall_score:.1f} (-100=强烈看跌, +100=强烈看涨)")
    print(f"\n--- 分项得分 ---")
    print(f"技术面: {recommendation.technical_score:.1f}")
    print(f"基本面: {recommendation.fundamental_score:.1f}")
    print(f"情绪面: {recommendation.sentiment_score:.1f}")

    print(f"\n--- 理由 ---")
    print(f"{recommendation.rationale}")

    if recommendation.key_factors:
        print(f"\n--- 关键因素 ---")
        for factor in recommendation.key_factors:
            print(f"  * {factor}")

    if recommendation.risk_factors:
        print(f"\n--- 风险因素 ---")
        for risk in recommendation.risk_factors:
            print(f"  ! {risk}")


def test_full_debate_simulation():
    """测试完整辩论模拟"""
    print_section("测试 4: 完整辩论模拟")

    from vibe_trading.agents.researchers.debate_analyzer import DebateEvaluator, RecommendationEngine

    # 模拟一个真实的多空辩论场景
    context = """
    当前市场环境: BTCUSDT
    当前价格: 52,000 USDT
    时间周期: 4小时图
    市场状态: 近期从48,000上涨至52,000

    技术指标:
    - RSI(14): 58
    - MACD: 金叉，但出现轻微顶背离
    - 布林带: 价格运行在中轨附近
    - 成交量: 上涨放量，下跌缩量

    基本面:
    - 活跃地址: 30天增长15%
    - 交易所流入: 7天净流入5,000 BTC
    - 期权OI: 看涨期权占比65%

    情绪指标:
    - Fear & Greed: 65 (贪婪)
    - 社交媒体: 多数情绪积极
    - 新闻情绪: 正面新闻占60%
    """

    # 看涨研究员发言
    bull_speeches = [
        """
        Bull: 技术面上，虽然MACD有轻微背离，但整体趋势依然向上。RSI为58处于健康区域，
        没有超买迹象。更重要的是，价格已经站稳在50,000 USDT这个关键支撑位之上，
        这是一个非常积极的信号。

        从成交量分析，我们观察到上涨时明显放量，而回调时缩量，
        这表明机构在吸筹，散户在获利了结，这是典型的建仓模式。
        """,

        """
        Bull: 基本面非常强劲。活跃地址在30天内增长了15%，这表明用户实际使用
        在快速增长，而不仅仅是投机。交易所数据显示过去7天净流入5,000 BTC，
        这代表长期持有者在积累。

        期权市场也给出明确信号，看涨期权占比高达65%，这说明大资金
        对后市看好。历史上当这个比例超过60%时，后续往往会继续上涨。

        针对Bear提到的顶背离，我认为这是正常的技术性回调。在强劲的上涨
        趋势中，出现短期的背离是正常现象，只要不跌破关键支撑，趋势就会延续。
        """,
    ]

    # 看跌研究员发言
    bear_speeches = [
        """
        Bear: 我必须指出技术面上的风险。虽然RSI为58看似健康，但需要注意到
        MACD确实出现了顶背离，这是趋势减弱的早期信号。历史上多次出现这种背离后，
        价格都在随后的1-2周内出现了显著回调。

        更重要的是，价格已经逼近52,000-53,000 USDT这个强阻力区域。
        在过去三个月中，价格三次尝试突破这个区域都失败了，并且每次都出现了
        5-8%的快速回调。这是一个非常关键的风险信号。

        从情绪面看，Fear & Greed指数达到65，虽然还没到极度贪婪，但已经
        进入贪婪区域。散户FOMO情绪开始出现，社交媒体上充斥着暴富故事，
        这通常是阶段顶部的特征。
        """,

        """
        Bear: 基本面上，虽然用户增长数据不错，但我认为市场已经充分甚至过度
        定价了这个增长。15%的增长虽然可观，但考虑到当前的市值，这个增长率
        很难支撑进一步的估值扩张。

        我还要强调的是，宏观经济环境正在变化。美联储暗示可能继续加息，
        这对风险资产整体不利。如果流动性收紧，加密货币将是首当其冲受影响
        的板块。

        针对Bull提到的交易所流入，我需要指出，这可能是短期的投机资金，
        而不是长期投资。过去几次流入高峰后，都很快出现了流出和价格回调。
        """,
    ]

    print("\n--- 辩论开始 ---")
    print("=" * 60)

    # 显示辩论过程
    for i, (bull_msg, bear_msg) in enumerate(zip(bull_speeches, bear_speeches), 1):
        print(f"\n【第 {i} 轮】")
        print("\n看涨研究员:")
        print(bull_msg.strip()[:200] + "...")
        print("\n看跌研究员:")
        print(bear_msg.strip()[:200] + "...")

    # 评估辩论
    evaluator = DebateEvaluator()
    scorecard = evaluator.evaluate_debate(
        bull_messages=bull_speeches,
        bear_messages=bear_speeches,
        market_context={"symbol": "BTCUSDT", "price": 52000}
    )

    # 生成建议
    analyst_reports = {
        "technical": "技术分析师: 中性偏多，趋势向上但需警惕阻力",
        "fundamental": "基本面分析师: 看涨，用户增长强劲",
        "sentiment": "情绪分析师: 贪婪偏多，需警惕",
    }

    engine = RecommendationEngine()
    recommendation = engine.generate_recommendation(
        scorecard=scorecard,
        analyst_reports=analyst_reports,
        market_data={"symbol": "BTCUSDT", "price": 52000}
    )

    print("\n\n" + "=" * 60)
    print("  研究经理最终裁决")
    print("=" * 60)

    print(f"\n辩论总结:")
    print(f"  看涨得分: {scorecard.bull_score:.1f}/100")
    print(f"  看跌得分: {scorecard.bear_score:.1f}/100")
    print(f"  主导观点: {scorecard.dominant_view}")
    print(f"  共识度: {scorecard.consensus_level:.1%}")

    print(f"\n各维度得分:")
    for dim, scores in scorecard.dimension_scores.items():
        dominant = "看涨" if scores['bull'] > scores['bear'] else "看跌"
        margin = abs(scores['bull'] - scores['bear'])
        print(f"  {dim.upper()}: {scores['bull']:.1f}% vs {scores['bear']:.1f}% ({dominant}领先{margin:.1f}%)")

    print(f"\n最终建议:")
    print(f"  行动: {recommendation.action}")
    print(f"  置信度: {recommendation.confidence:.1%}")
    print(f"  综合评分: {recommendation.overall_score:.1f}/100")

    print(f"\n分项评分:")
    print(f"  技术面: {recommendation.technical_score:+.1f}")
    print(f"  基本面: {recommendation.fundamental_score:+.1f}")
    print(f"  情绪面: {recommendation.sentiment_score:+.1f}")

    print(f"\n决策理由:")
    print(f"  {recommendation.rationale}")

    if recommendation.key_factors:
        print(f"\n支持因素:")
        for i, factor in enumerate(recommendation.key_factors, 1):
            print(f"  {i}. {factor}")

    if recommendation.risk_factors:
        print(f"\n风险提示:")
        for i, risk in enumerate(recommendation.risk_factors, 1):
            print(f"  {i}. {risk}")

    print(f"\n投资计划:")
    if recommendation.action == "BUY":
        print(f"  方向: 做多")
        print(f"  建议入场: 51,500 - 52,000 USDT 区间")
        print(f"  目标价位: 54,500 USDT (+4.8%)")
        print(f"  止损价位: 50,500 USDT (-2.9%)")
        print(f"  盈亏比: 1.6:1")
    elif recommendation.action == "SELL":
        print(f"  方向: 做空")
        print(f"  建议入场: 51,500 - 52,000 USDT 区间")
        print(f"  目标价位: 50,000 USDT (-3.8%)")
        print(f"  止损价位: 53,500 USDT (+2.9%)")
        print(f"  盈亏比: 1.3:1")
    else:
        print(f"  方向: 观望")
        print(f"  建议: 等待市场突破关键阻力/支撑后再做决策")


def main():
    """运行所有测试"""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  研究员团队辩论分析测试".center(56) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    try:
        test_argument_extractor()
        test_debate_evaluator()
        test_recommendation_engine()
        test_full_debate_simulation()

        print_section("测试完成")
        print("✅ 所有研究员团队功能测试通过")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
