# 回测系统使用指南

## 快速开始

### 方式 1: 命令行（推荐）

```bash
# 基础回测
PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest \
  BTCUSDT --start "2024-01-01" --end "2024-01-31"

# 使用缓存模式
PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest \
  BTCUSDT --start "2024-01-01" --end "2024-01-31" --llm-mode cached

# 生成 HTML 报告
PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest \
  BTCUSDT --start "2024-01-01" --end "2024-01-31" --report-format html
```

### 方式 2: Python 脚本

```python
import asyncio
from datetime import datetime, timedelta
from vibe_trading.backtest.engine import BacktestEngine
from vibe_trading.backtest.models import BacktestConfig, LLMMode

async def run_backtest():
    config = BacktestConfig(
        symbol="BTCUSDT",
        interval="1h",
        start_time=datetime.now() - timedelta(days=7),
        end_time=datetime.now(),
        initial_balance=10000.0,
        llm_mode=LLMMode.SIMULATED,
    )

    engine = BacktestEngine(config)
    result = await engine.run_backtest()

    print(f"总收益率: {result.metrics.total_return:.2%}")
    print(f"夏普比率: {result.metrics.sharpe_ratio:.2f}")
    print(f"胜率: {result.metrics.win_rate:.2%}")

asyncio.run(run_backtest())
```

### 方式 3: 交互式演示

```bash
uv run python demo_backtest.py
```

## LLM 模式说明

| 模式 | 速度 | 适用场景 |
|------|------|----------|
| `SIMULATED` | ⚡⚡⚡ 最快 | 快速测试、策略验证 |
| `CACHED` | ⚡⚡ 中等 | 重复测试、参数优化 |
| `REAL` | ⚡ 较慢 | 最终验证 |

## 常用命令

```bash
# 查看帮助
PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest --help

# 测试不同 K 线周期
for interval in 15m 30m 1h 4h; do
  PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest \
    BTCUSDT --start "2024-01-01" --end "2024-01-31" --interval $interval
done

# 生成多种格式报告
PYTHONPATH=backend/src uv run --no-sync python -m vibe_trading.cli backtest \
  BTCUSDT --start "2024-01-01" --end "2024-01-31" \
  --report-format text,html,json
```

## 测试

```bash
# 运行组件测试
uv run python test_backtest_simple.py

# 运行完整系统测试
uv run python test_backtest_system.py
```

## 详细文档

查看 [BACKTEST_GUIDE.md](BACKTEST_GUIDE.md) 了解更多详细信息。
