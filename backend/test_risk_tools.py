"""
风控工具测试脚本

测试VaR计算、凯利公式、风险指标等新增风控功能。
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import asdict
import json

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vibe_trading.execution.advanced_risk_tools import (
    VaRCalculator,
    KellyCalculator,
    RiskMetricsCalculator,
    VolatilityAdjustedPositionSizer,
    CorrelationRiskChecker,
    TrailingStopLossManager,
)
from vibe_trading.execution.risk_manager import RiskManager


def print_section(title: str):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_var_calculator():
    """测试VaR计算器"""
    print_section("测试 1: VaR（风险价值）计算器")

    var_calc = VaRCalculator()

    # 模拟一些价格变化
    base_price = 50000
    import random
    random.seed(42)

    print("\n--- 模拟50个交易日的价格变化 ---")
    for i in range(50):
        change_pct = (random.random() - 0.5) * 0.04  # -2% 到 +2%
        new_price = base_price * (1 + change_pct)
        var_calc.add_price_change(base_price, new_price)
        base_price = new_price

    # 计算VaR
    position_value = 1000  # 1000 USDT的仓位
    result = var_calc.calculate_var(position_value, method="historical")

    print(f"\n仓位价值: {position_value} USDT")
    print(f"VaR 95%: {result.var_95:.2f} USDT ({result.var_95/position_value*100:.2f}%)")
    print(f"VaR 99%: {result.var_99:.2f} USDT ({result.var_99/position_value*100:.2f}%)")
    print(f"预期亏损: {result.expected_shortfall:.2f} USDT")
    print(f"波动率: {result.volatility*100:.2f}%")

    print("\n解读:")
    print(f"- 有95%的把握，单日最大损失不超过{result.var_95:.2f}USDT")
    print(f"- 有99%的把握，单日最大损失不超过{result.var_99:.2f}USDT")
    print(f"- 如果发生最坏5%的情况，平均损失{result.expected_shortfall:.2f}USDT")


def test_kelly_calculator():
    """测试凯利公式计算器"""
    print_section("测试 2: 凯利公式计算器")

    kelly_calc = KellyCalculator()

    # 模拟交易历史
    print("\n--- 模拟30笔交易 ---")
    win_rate_target = 0.55  # 目标胜率55%

    import random
    random.seed(42)

    account = 10000
    for i in range(30):
        is_win = random.random() < win_rate_target
        if is_win:
            pnl = random.uniform(50, 150)  # 平均盈利100
        else:
            pnl = -random.uniform(50, 100)  # 平均亏损75

        kelly_calc.add_trade(
            pnl=pnl,
            entry_price=50000,
            exit_price=50000 + pnl/100*50000,
            position_size=abs(pnl)/50000
        )

    # 计算凯利公式
    account_balance = 10000
    result = kelly_calc.calculate_kelly(account_balance)

    print(f"\n账户余额: {account_balance} USDT")
    print(f"历史胜率: {result.win_rate*100:.1f}%")
    print(f"平均盈利: {result.avg_win:.2f} USDT")
    print(f"平均亏损: {result.avg_loss:.2f} USDT")
    print(f"盈亏比: {result.profit_factor:.2f}")
    print(f"\n凯利公式建议:")
    print(f"- 全凯利仓位: {result.kelly_fraction*100:.2f}% ({result.kelly_fraction*account_balance:.2f}USDT)")
    print(f"- 半凯利仓位: {result.half_kelly_fraction*100:.2f}% ({result.half_kelly_fraction*account_balance:.2f}USDT) ⭐ 推荐")
    print(f"- 最优仓位: {result.optimal_position_size:.2f} USDT")

    print("\n解读:")
    print(f"- 凯利公式显示理论最优仓位是{result.kelly_fraction*100:.1f}%")
    print(f"- 实际建议使用半凯利({result.half_kelly_fraction*100:.1f}%)以降低波动率")
    print(f"- 当前盈亏比{result.profit_factor:.2f}，胜率{result.win_rate*100:.0f}%，交易策略有效")


def test_risk_metrics():
    """测试风险指标计算"""
    print_section("测试 3: 风险指标仪表板")

    metrics_calc = RiskMetricsCalculator()

    # 模拟账户历史
    print("\n--- 模拟100天的交易历史 ---")

    import random
    random.seed(42)

    balance = 10000
    equity_history = []

    for day in range(100):
        # 模拟一些盈亏
        daily_pnl = random.uniform(-200, 250)
        equity = balance + daily_pnl
        equity_history.append(equity)

        metrics_calc.update_balance(balance, equity)

        # 随机添加一些交易记录
        if random.random() < 0.3:  # 30%概率有交易
            pnl = random.uniform(-100, 150)
            metrics_calc.add_trade(
                pnl=pnl,
                entry_price=50000,
                exit_price=50000 + pnl/100*50000,
                position_size=abs(pnl)/50000,
                symbol="BTCUSDT",
                entry_time=datetime.now() - timedelta(days=1),
                exit_time=datetime.now()
            )

        balance = equity

    # 计算风险指标
    metrics = metrics_calc.calculate_metrics(
        account_balance=balance,
        total_equity=balance,
        unrealized_pnl=0,
        margin_used=balance * 0.3,
        margin_free=balance * 0.7
    )

    print(f"\n=== 基础指标 ===")
    print(f"账户余额: {metrics.account_balance:.2f} USDT")
    print(f"总权益: {metrics.total_equity:.2f} USDT")
    print(f"已实现盈亏: {metrics.realized_pnl:.2f} USDT")
    print(f"保证金使用: {metrics.margin_used:.2f} USDT ({metrics.margin_ratio*100:.1f}%)")

    print(f"\n=== 风险指标 ===")
    print(f"当前回撤: {metrics.current_drawdown*100:.2f}%")
    print(f"最大回撤: {metrics.max_drawdown*100:.2f}%")
    print(f"VaR 95%: {metrics.var_95:.2f} USDT")
    print(f"VaR 99%: {metrics.var_99:.2f} USDT")
    print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"索提诺比率: {metrics.sortino_ratio:.2f}")

    print(f"\n=== 交易统计 ===")
    print(f"总交易: {metrics.total_trades}笔")
    print(f"盈利: {metrics.winning_trades}笔 | 亏损: {metrics.losing_trades}笔")
    print(f"胜率: {metrics.win_rate*100:.1f}%")
    print(f"平均盈利: {metrics.avg_win:.2f} USDT")
    print(f"平均亏损: {metrics.avg_loss:.2f} USDT")
    print(f"盈亏比: {metrics.profit_factor:.2f}")

    print(f"\n=== 连续统计 ===")
    print(f"当前连续: {metrics.current_streak} ({'盈利' if metrics.current_streak > 0 else '亏损'})")
    print(f"最大连胜: {metrics.max_winning_streak}笔")
    print(f"最大连亏: {metrics.max_losing_streak}笔")
    print(f"当前连亏: {metrics.consecutive_losses}笔")

    print(f"\n=== 风险评估 ===")
    print(f"风险等级: {metrics.risk_level.upper()}")
    if metrics.warnings:
        print("警告:")
        for warning in metrics.warnings:
            print(f"  ⚠️  {warning}")
    else:
        print("✅ 无警告")


def test_volatility_sizer():
    """测试波动率调整仓位"""
    print_section("测试 4: 波动率自适应仓位")

    sizer = VolatilityAdjustedPositionSizer(base_risk_per_trade=0.02)

    account_balance = 10000
    entry_price = 50000
    stop_loss_price = 49000

    print(f"\n账户余额: {account_balance} USDT")
    print(f"入场价: {entry_price} USDT")
    print(f"止损价: {stop_loss_price} USDT")
    print(f"止损距离: {(entry_price - stop_loss_price) / entry_price * 100:.2f}%")

    # 正常波动率
    normal_size = sizer.calculate_adjusted_position_size(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        current_atr=None
    )

    print(f"\n--- 正常波动率 ---")
    print(f"建议仓位: {normal_size:.2f} USDT ({normal_size/account_balance*100:.1f}%)")

    # 高波动率
    for _ in range(15):
        sizer.update_atr(1500, entry_price)

    high_vol_size = sizer.calculate_adjusted_position_size(
        account_balance=account_balance,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        current_atr=1500
    )

    print(f"\n--- 高波动率 (ATR=1500) ---")
    print(f"建议仓位: {high_vol_size:.2f} USDT ({high_vol_size/account_balance*100:.1f}%)")
    print(f"调整: {(high_vol_size/normal_size - 1)*100:.0f}%")


def test_correlation_checker():
    """测试相关性检查"""
    print_section("测试 5: 相关性风险检查")

    checker = CorrelationRiskChecker()

    # 模拟价格历史
    import random
    random.seed(42)

    print("\n--- 模拟BTC和ETH价格走势 ---")

    btc_price = 50000
    eth_price = 3000

    for i in range(50):
        # BTC和ETH高度相关
        market_move = (random.random() - 0.5) * 0.02

        btc_change = market_move + (random.random() - 0.5) * 0.01
        eth_change = market_move * 1.2 + (random.random() - 0.5) * 0.015

        btc_price = btc_price * (1 + btc_change)
        eth_price = eth_price * (1 + eth_change)

        checker.update_price("BTCUSDT", btc_price)
        checker.update_price("ETHUSDT", eth_price)

    # 计算相关性
    correlation = checker.calculate_correlation("BTCUSDT", "ETHUSDT")

    print(f"\nBTC-ETH相关性: {correlation:.3f}")

    if abs(correlation) > 0.7:
        print("⚠️  高度相关！同时持有会增加风险")

    # 检查投资组合
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    high_corr = checker.check_portfolio_correlation(symbols, threshold=0.7)

    if high_corr:
        print("\n高风险相关性对:")
        for symbol, correlated in high_corr.items():
            print(f"  {symbol}: {', '.join(correlated)}")


def test_trailing_stop():
    """测试移动止损"""
    print_section("测试 6: 移动止损系统")

    manager = TrailingStopLossManager(
        activation_profit_pct=0.01,  # 1%盈利激活
        trail_distance_pct=0.02     # 2%跟踪距离
    )

    symbol = "BTCUSDT"
    entry_price = 50000
    position_side = "LONG"
    initial_stop = 49000

    print(f"\n入场价: {entry_price} USDT")
    print(f"初始止损: {initial_stop} USDT")
    print(f"激活条件: 盈利1%后激活移动止损")
    print(f"跟踪距离: 2%")

    manager.add_position(symbol, entry_price, position_side, initial_stop)

    # 模拟价格变化
    prices = [
        (50100, "小幅上涨"),
        (50200, "接近激活"),
        (50500, "激活移动止损！"),
        (50800, "止损上调"),
        (51200, "止损继续上调"),
        (51000, "价格回落"),
        (50700, "继续回落"),
        (50500, "触发止损？"),
    ]

    print("\n--- 价格走势 ---")
    for price, desc in prices:
        new_stop = manager.update_stop_loss(symbol, price)
        current_stop = manager.get_stop_loss(symbol)

        if new_stop:
            print(f"价格: {price} USDT ({desc}) → 止损调整到 {new_stop:.0f} USDT ⬆️")
        else:
            stop_status = "已激活" if manager._positions[symbol]["activated"] else "未激活"
            print(f"价格: {price} USDT ({desc}) → 止损: {current_stop:.0f} USDT ({stop_status})")

    final_stop = manager.get_stop_loss(symbol)
    print(f"\n最终止损: {final_stop:.0f} USDT")
    print(f"保护利润: {(final_stop - entry_price) / entry_price * 100:.2f}%")


async def test_risk_manager_integration():
    """测试集成风险管理器"""
    print_section("测试 7: 集成风险管理器")

    rm = RiskManager()

    # 更新市场数据
    print("\n--- 更新市场数据 ---")
    rm.update_market_data("BTCUSDT", 50000, atr=1000)

    # 检查订单风险
    print("\n--- 订单风险检查 ---")
    check = await rm.check_order_risk(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.1,
        price=50000,
        current_balance=10000
    )

    print(f"结果: {check.result.value}")
    print(f"原因: {check.reason}")

    if check.var_analysis:
        print(f"\nVaR分析:")
        print(f"  VaR 95%: {check.var_analysis['var_95']:.2f} USDT")
        print(f"  VaR比率: {check.var_analysis['var_ratio']*100:.2f}%")

    if check.warnings:
        print(f"\n警告:")
        for w in check.warnings:
            print(f"  ⚠️  {w}")

    # 整体风险评估
    print("\n--- 整体风险评估 ---")
    assessment = rm.assess_overall_risk(
        account_balance=9500,
        total_equity=9500,
        margin_used=3000,
        margin_free=6500,
        positions=[
            {"symbol": "BTCUSDT", "unrealized_profit": -200}
        ]
    )

    print(f"风险等级: {assessment['risk_level'].upper()}")
    print(f"风险分数: {assessment['score']}/{assessment['max_score']}")

    if assessment['warnings']:
        print("\n警告:")
        for w in assessment['warnings']:
            print(f"  ⚠️  {w}")

    if assessment['recommendations']:
        print("\n建议:")
        for r in assessment['recommendations']:
            print(f"  💡 {r}")


def main():
    """运行所有测试"""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  风控工具增强功能测试".center(56) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)

    try:
        test_var_calculator()
        test_kelly_calculator()
        test_risk_metrics()
        test_volatility_sizer()
        test_correlation_checker()
        test_trailing_stop()
        asyncio.run(test_risk_manager_integration())

        print_section("测试完成")
        print("✅ 所有风控工具测试通过")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
