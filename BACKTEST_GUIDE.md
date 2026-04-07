# Vibe Trading 回测系统使用指南

## 快速开始

### 1. 命令行使用 (推荐)

```bash
# 基本回测（使用模拟模式）
PYTHONPATH=src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31"

# 使用缓存模式（首次运行后缓存结果）
PYTHONPATH=src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --llm-mode cached

# 生成多种格式报告
PYTHONPATH=src uv run -- vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --report-format text,html,json
```

### 2. Python API 使用

```python
import asyncio
from datetime import datetime, timedelta
from vibe_trading.backtest.engine import BacktestEngine
from vibe_trading.backtest.models import BacktestConfig, LLMMode

async def run_backtest():
    # 创建配置
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval="1h",
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 31),
        initial_balance=10000.0,
        llm_mode=LLMMode.SIMULATED,  # 或 CACHED, REAL
    )

    # 运行回测
    engine = BacktestEngine(config)
    result = await engine.run_backtest()

    # 查看结果
    print(f"总收益率: {result.metrics.total_return:.2%}")
    print(f"夏普比率: {result.metrics.sharpe_ratio:.2f}")
    print(f"最大回撤: {result.metrics.max_drawdown:.2%}")
    print(f"胜率: {result.metrics.win_rate:.2%}")

asyncio.run(run_backtest())
```

## 配置选项

### BacktestConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `symbol` | str | 必填 | 交易对符号（如 BTCUSDT） |
| `interval` | str | "30m" | K线间隔（1m, 5m, 15m, 30m, 1h, 4h, 1d） |
| `start_time` | datetime | 必填 | 回测开始时间 |
| `end_time` | datetime | 必填 | 回测结束时间 |
| `initial_balance` | float | 10000.0 | 初始余额（USDT） |
| `llm_mode` | LLMMode | SIMULATED | LLM模式（SIMULATED/CACHED/REAL） |

### LLM 模式说明

| 模式 | 说明 | 适用场景 | 速度 |
|------|------|----------|------|
| `SIMULATED` | 基于历史模式模拟决策 | 快速测试、策略验证 | ⚡⚡⚡ 最快 |
| `CACHED` | 使用缓存的 LLM 响应 | 重复测试、参数优化 | ⚡⚡ 中等 |
| `REAL` | 真实 LLM 调用 | 最终验证、生产环境 | ⚡ 较慢 |

## 输出报告

### 文本报告示例

```
======================================================================
                                 回测报告
======================================================================

【基本信息】
  交易品种: BTCUSDT
  K线间隔: 1h
  回测时间: 2024-01-01 ~ 2024-01-31
  LLM模式: simulated
  初始余额: $10,000.00

【收益指标】
  总收益率: 15.2%
  总盈亏: $1,520.00
  平均每笔: $76.00
  盈利交易平均: $150.00
  亏损交易平均: $-50.00

【风险指标】
  夏普比率: 1.85
  Sortino比率: 2.10
  最大回撤: -8.5%
  VaR (95%): $200.00
  VaR (99%): $350.00
  最大连续亏损: 3 次

【交易统计】
  总交易数: 20
  盈利交易: 12
  亏损交易: 8
  胜率: 60.00%
  盈亏比: 1.50
  平均持仓时长: 12.5 小时
```

### HTML 报告

- 资金曲线图（交互式）
- 回撤图表
- 每日收益分布
- 交易明细表

### JSON 报告

```json
{
  "config": {
    "symbol": "BTCUSDT",
    "interval": "1h",
    "start_time": "2024-01-01T00:00:00",
    "end_time": "2024-01-31T23:59:59"
  },
  "metrics": {
    "total_return": 0.152,
    "win_rate": 0.60,
    "sharpe_ratio": 1.85,
    "max_drawdown": -0.085
  },
  "trades": [...]
}
```

## 高级用法

### 参数优化

```python
# 测试不同的参数组合
intervals = ["15m", "30m", "1h", "4h"]
results = {}

for interval in intervals:
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval=interval,
        start_time=datetime(2024, 1, 1),
        end_time=datetime(2024, 1, 31),
        llm_mode=LLMMode.SIMULATED,
    )
    engine = BacktestEngine(config)
    result = await engine.run_backtest()
    results[interval] = result.metrics.total_return

# 找出最佳参数
best_interval = max(results, key=results.get)
print(f"最佳K线周期: {best_interval}, 收益率: {results[best_interval]:.2%}")
```

### 自定义数据源

```python
from vibe_trading.backtest.data_loader import BacktestDataLoader, DataSource

# 使用本地存储（更快）
loader = BacktestDataLoader(default_source=DataSource.LOCAL_STORAGE)

# 使用 Binance API（完整历史数据）
loader = BacktestDataLoader(default_source=DataSource.BINANCE_API)

# 混合模式（优先本地，不足时从API补充）
loader = BacktestDataLoader(default_source=DataSource.HYBRID)
```

## 常见问题

### Q: 如何加快回测速度？

A: 使用 `SIMULATED` 模式，它不需要真实的 LLM 调用：
```python
config = BacktestConfig(
    ...,
    llm_mode=LLMMode.SIMULATED,
)
```

### Q: 如何使用历史数据避免重复下载？

A: 回测系统会自动缓存数据到本地 SQLite 数据库。首次运行后会缓存，后续运行会优先使用本地数据。

### Q: 如何只测试特定时间段？

A: 调整 `start_time` 和 `end_time`：
```python
config = BacktestConfig(
    ...,
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 15),  # 只测试半个月
)
```

### Q: 如何查看每笔交易的详细信息？

A: 检查 `result.trades`：
```python
for trade in result.trades:
    print(f"{trade.entry_time} {trade.signal.value} "
          f"@ {trade.entry_price} -> PnL: ${trade.pnl:.2f}")
```
