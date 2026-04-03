"""
决策层测试脚本

测试交易员和投资组合经理的执行计划功能。
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vibe_trading.agents.decision.trading_tools import (
    PositionSizeCalculator,
    StopLossTakeProfitCalculator,
    ExecutionStrategyCalculator,
    DecisionFramework,
    TradingPlan,
    DecisionScorecard,
    OrderType,
    PositionSide,
    ExecutionStyle,
)


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_position_size_calculator():
    """测试仓位计算器"""
    print_section("测试 1: 仓位计算器")

    calc = PositionSizeCalculator()

    # 测试场景
    account_balance = 10000.0
    entry_price = 50000.0
    stop_loss_price = 49000.0  # 2%止损

    print(f"\n账户余额: {account_balance} USDT")
    print(f"入场价格: {entry_price} USDT")
    print(f"止损价格: {stop_loss_price} USDT")
    print(f"止损距离: {abs(entry_price - stop_loss_price) / entry_price * 100:.2f}%")

    # 不同风险偏好
    for risk_pref in ["conservative", "moderate", "aggressive"]:
        result = calc.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_preference=risk_pref,
        )

        print(f"\n--- {risk_pref.upper()} 风险偏好 ---")
        print(f"仓位大小: {result['position_size_usdt']} USDT ({result['position_size_pct']}%)")
        print(f"币数量: {result['position_size_coin']:.6f} BTC")
        print(f"风险金额: {result['risk_amount_usdt']} USDT")
        print(f"杠杆: {result['leverage']}x")
        print(f"理由: {result['reasoning']}")


def test_stop_loss_take_profit_calculator():
    """测试止损止盈计算器"""
    print_section("测试 2: 止损止盈计算器")

    calc = StopLossTakeProfitCalculator()

    entry_price = 50000.0
    atr = 800.0  # ATR波动率

    print(f"\n入场价格: {entry_price} USDT")
    print(f"ATR波动率: {atr} USDT ({atr/entry_price*100:.2f}%)")

    # 做多场景
    print("\n--- 做多 (LONG) ---")
    long_result = calc.calculate_levels(
        entry_price=entry_price,
        position_side=PositionSide.LONG,
        atr=atr,
        risk_reward_ratio=2.0,
    )

    print(f"止损: {long_result['stop_loss_price']} USDT")
    print(f"止盈: {long_result['take_profit_price']} USDT")
    print(f"盈亏比: {long_result['risk_reward_ratio']}:1")

    print("\n分批止盈:")
    for tp in long_result["partial_take_profits"]:
        print(f"  第{tp['level']}批: {tp['price']} USDT ({tp['size_pct']}%)")

    print(f"\n移动止损配置: {long_result['trailing_stop_config']}")

    # 做空场景
    print("\n--- 做空 (SHORT) ---")
    short_result = calc.calculate_levels(
        entry_price=entry_price,
        position_side=PositionSide.SHORT,
        atr=atr,
        risk_reward_ratio=2.0,
    )

    print(f"止损: {short_result['stop_loss_price']} USDT")
    print(f"止盈: {short_result['take_profit_price']} USDT")
    print(f"盈亏比: {short_result['risk_reward_ratio']}:1")


def test_execution_strategy_calculator():
    """测试执行策略计算器"""
    print_section("测试 3: 执行策略计算器")

    calc = ExecutionStrategyCalculator()

    current_price = 50000.0
    atr = 800.0

    print(f"\n当前价格: {current_price} USDT")
    print(f"ATR波动率: {atr} USDT ({atr/current_price*100:.2f}%)")

    # 不同紧急程度
    scenarios = [
        ("高紧急度", "high", None, 0.05, 50000000),
        ("正常紧急度", "normal", 0.02, 0.05, 50000000),
        ("低紧急度", "low", 0.02, 0.05, 50000000),
        ("低紧急度+高波动", "low", 0.05, 0.15, 1000000),  # 流动性差
    ]

    for scenario_name, urgency, vol, spread, volume in scenarios:
        print(f"\n--- {scenario_name} ---")
        result = calc.determine_execution_style(
            direction="LONG",
            current_price=current_price,
            volatility=vol,
            spread_pct=spread,
            volume_24h=volume,
            urgency_level=urgency,
        )

        print(f"执行风格: {result['execution_style'].value}")
        print(f"订单类型: {result['order_type'].value}")
        print(f"理由: {result['reasoning']}")

        print("入场计划:")
        for order in result["entry_orders"]:
            if order["type"] == "market":
                print(f"  - 市价单 {order['pct']}% {order['note']}")
            else:
                offset = order.get("price_offset_pct", 0)
                price = current_price * (1 + offset / 100)
                print(f"  - 限价单 {price:.2f} USDT ({offset:+.1f}%) {order['pct']}% {order['note']}")


def test_decision_framework():
    """测试决策框架"""
    print_section("测试 4: 决策框架")

    framework = DecisionFramework()

    # 模拟输入
    analyst_reports = {
        "technical": "技术分析师: 看涨，MACD金叉，RSI中性偏多",
        "fundamental": "基本面分析师: 看涨，活跃地址增长15%",
        "sentiment": "情绪分析师: 中性偏多，Fear & Greed指数65",
    }

    research_recommendation = {
        "action": "BUY",
        "confidence": 0.75,
    }

    risk_assessment = {
        "aggressive": "激进风控: 风险可控，可以正常仓位",
        "neutral": "中立风控: 建议2%风险敞口",
        "conservative": "保守风控: 建议1%风险敞口，设置紧止损",
    }

    print("\n--- 输入信息 ---")
    print("分析师报告:")
    for role, report in analyst_reports.items():
        print(f"  {role}: {report[:50]}...")
    print(f"\n研究建议: {research_recommendation['action']} (置信度: {research_recommendation['confidence']})")
    print("风险评估:")
    for role, assessment in risk_assessment.items():
        print(f"  {role}: {assessment[:40]}...")

    # 计算决策评分卡
    scorecard = framework.calculate_decision_scorecard(
        analyst_reports=analyst_reports,
        research_recommendation=research_recommendation,
        risk_assessment=risk_assessment,
        current_market_data={"price": 50000, "balance": 10000},
    )

    print("\n--- 决策评分卡 ---")
    print(f"总分: {scorecard.overall_score}/100")
    print(f"置信度: {scorecard.confidence:.1%}")
    print(f"推荐行动: {scorecard.recommended_action}")
    print(f"仓位建议: {scorecard.position_size_recommendation}")

    print("\n各维度得分:")
    print(f"  技术面: {scorecard.technical_score}/100")
    print(f"  基本面: {scorecard.fundamental_score}/100")
    print(f"  情绪面: {scorecard.sentiment_score}/100")
    print(f"  风险: {scorecard.risk_score}/100")

    if scorecard.supporting_factors:
        print("\n支持因素:")
        for factor in scorecard.supporting_factors:
            print(f"  + {factor}")

    if scorecard.risk_factors:
        print("\n风险因素:")
        for risk in scorecard.risk_factors:
            print(f"  - {risk}")

    print(f"\n决策理由: {scorecard.rationale}")


def test_full_trading_plan():
    """测试完整交易计划生成"""
    print_section("测试 5: 完整交易计划")

    # 初始化计算器
    pos_calc = PositionSizeCalculator()
    sltp_calc = StopLossTakeProfitCalculator()
    exec_calc = ExecutionStrategyCalculator()

    # 模拟输入
    direction = "LONG"  # 由前面阶段确定
    current_price = 50000.0
    account_balance = 10000.0
    atr = 800.0
    kelly_fraction = 0.15

    print(f"\n=== 交易计划输入 ===")
    print(f"交易方向: {direction} (已由前面阶段确定)")
    print(f"当前价格: {current_price} USDT")
    print(f"账户余额: {account_balance} USDT")
    print(f"ATR: {atr} USDT")
    print(f"凯利建议: {kelly_fraction:.1%}")

    # 1. 计算止损止盈
    sltp_result = sltp_calc.calculate_levels(
        entry_price=current_price,
        position_side=PositionSide.LONG,
        atr=atr,
        risk_reward_ratio=2.0,
    )

    # 2. 计算仓位大小
    pos_result = pos_calc.calculate_position_size(
        account_balance=account_balance,
        entry_price=current_price,
        stop_loss_price=sltp_result["stop_loss_price"],
        risk_preference="moderate",
        kelly_fraction=kelly_fraction,
        current_atr=atr,
    )

    # 3. 确定执行策略
    exec_result = exec_calc.determine_execution_style(
        direction=direction,
        current_price=current_price,
        volatility=atr / current_price,
        spread_pct=0.05,
        volume_24h=50000000,
        urgency_level="normal",
    )

    # 4. 构建入场订单
    entry_orders = exec_calc.build_entry_orders(
        direction=direction,
        current_price=current_price,
        total_size_coin=pos_result["position_size_coin"],
        entry_plan=exec_result["entry_orders"],
    )

    # 5. 构建止损订单
    stop_loss_orders = [{
        "order_type": "stop_market",
        "trigger_price": sltp_result["stop_loss_price"],
        "size_coin": pos_result["position_size_coin"],
        "note": "止损单",
    }]

    # 6. 构建止盈订单
    take_profit_orders = []
    for tp in sltp_result["partial_take_profits"]:
        take_profit_orders.append({
            "order_type": "limit",
            "price": tp["price"],
            "size_coin": pos_result["position_size_coin"] * tp["size_pct"] / 100,
            "pct": tp["size_pct"],
            "note": f"第{tp['level']}批止盈",
        })

    # 7. 生成交易计划
    trading_plan = TradingPlan(
        symbol="BTCUSDT",
        position_side=PositionSide.LONG,
        direction=direction,
        execution_style=exec_result["execution_style"],
        entry_orders=entry_orders,
        total_position_usdt=pos_result["position_size_usdt"],
        total_position_coin=pos_result["position_size_coin"],
        leverage=pos_result["leverage"],
        stop_loss_orders=stop_loss_orders,
        take_profit_orders=take_profit_orders,
        trailing_stop_config=sltp_result["trailing_stop_config"],
        max_loss_usdt=pos_result["risk_amount_usdt"],
        max_loss_pct=pos_result["stop_distance_pct"],
        risk_reward_ratio=sltp_result["risk_reward_ratio"],
        execution_notes=[
            f"执行风格: {exec_result['execution_style'].value}",
            f"执行理由: {exec_result['reasoning']}",
        ],
    )

    print(f"\n=== 交易执行计划 ===")
    print(f"方向: {trading_plan.direction}")
    print(f"执行风格: {trading_plan.execution_style.value}")
    print(f"总仓位: {trading_plan.total_position_usdt} USDT ({trading_plan.total_position_coin:.6f} BTC)")
    print(f"杠杆: {trading_plan.leverage}x")

    print(f"\n入场订单:")
    for order in trading_plan.entry_orders:
        print(f"  {order['order_type']} @ {order['price']:.2f} USDT ({order['pct']}%) - {order['note']}")

    print(f"\n止损订单:")
    for order in trading_plan.stop_loss_orders:
        print(f"  {order['order_type']} @ {order['trigger_price']:.2f} USDT ({order['size_coin']:.6f} BTC) - {order['note']}")

    print(f"\n止盈订单:")
    for order in trading_plan.take_profit_orders:
        print(f"  {order['order_type']} @ {order['price']:.2f} USDT ({order['pct']}%) - {order['note']}")

    print(f"\n风险管理:")
    print(f"  最大亏损: {trading_plan.max_loss_usdt} USDT ({trading_plan.max_loss_pct:.2f}%)")
    print(f"  盈亏比: {trading_plan.risk_reward_ratio}:1")

    if trading_plan.trailing_stop_config:
        print(f"  移动止损: 激活阈值{trading_plan.trailing_stop_config['activation_profit']*100}%, 跟踪距离{trading_plan.trailing_stop_config['trail_distance']*100}%")

    print(f"\n执行说明:")
    for note in trading_plan.execution_notes:
        print(f"  - {note}")


def main():
    """运行所有测试"""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  决策层测试".center(56) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    try:
        test_position_size_calculator()
        test_stop_loss_take_profit_calculator()
        test_execution_strategy_calculator()
        test_decision_framework()
        test_full_trading_plan()

        print_section("测试完成")
        print("所有决策层功能测试通过")

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
