# 回测系统

Vibe Trading 提供强大的历史数据回测系统，帮助你在不使用真实资金的情况下验证交易策略。

## 回测特性

### 支持的 LLM 模式

1. **SIMULATED（模拟模式）**
   - 使用模拟的 LLM 响应
   - 速度最快，适合快速测试
   - 不消耗 API 额度

2. **CACHED（缓存模式）**
   - 缓存真实的 LLM 响应
   - 相同输入返回相同结果
   - 适合重复测试

3. **REAL（真实模式）**
   - 调用真实的 LLM API
   - 结果最准确
   - 消耗 API 额度

### 回测指标

- 总收益率
- 夏普比率
- 最大回撤
- 胜率
- 总交易次数
- 平均盈利/亏损
- 盈亏比
- 卡玛比率

## 快速开始

### 基础回测

```bash
PYTHONPATH=backend/src uv run -- vibe-trade backtest \
  BTCUSDT \
  --start "2024-01-01" \
  --end "2024-01-31" \
  --interval "1h"
```

### 使用缓存模式

```bash
PYTHONPATH=backend/src uv run -- vibe-trade backtest \
  BTCUSDT \
  --start "2024-01-01" \
  --end "2024-01-31" \
  --llm-mode cached
```

### 生成 HTML 报告

```bash
PYTHONPATH=backend/src uv run -- vibe-trade backtest \
  BTCUSDT \
  --start "2024-01-01" \
  --end "2024-01-31" \
  --report-format html
```

### 自定义初始资金

```bash
PYTHONPATH=backend/src uv run -- vibe-trade backtest \
  BTCUSDT \
  --start "2024-01-01" \
  --end "2024-01-31" \
  --initial-balance 50000
```

## 回测配置

### 完整参数

```bash
vibe-trade backtest [OPTIONS] SYMBOL

选项:
  --start TEXT        开始日期 (YYYY-MM-DD) [必需]
  --end TEXT          结束日期 (YYYY-MM-DD) [必需]
  --interval TEXT     K线间隔 [默认: 30m]
  --llm-mode TEXT     LLM模式 (simulated/cached/real) [默认: simulated]
  --initial-balance FLOAT  初始余额 [默认: 10000.0]
  --report-format TEXT    报告格式 (text/html/json) [默认: text]
```

### Python API

```python
from datetime import datetime
from vibe_trading.backtest.engine import BacktestEngine
from vibe_trading.backtest.models import BacktestConfig, LLMMode, ReportFormat

# 创建配置
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 31),
    initial_balance=10000.0,
    llm_mode=LLMMode.CACHED,
    report_formats=[ReportFormat.HTML, ReportFormat.TEXT],
)

# 运行回测
engine = BacktestEngine(config)
result = await engine.run_backtest()

# 查看结果
if result.metrics:
    print(f"总收益率: {result.metrics.total_return:.2%}")
    print(f"夏普比率: {result.metrics.sharpe_ratio:.2f}")
    print(f"最大回撤: {result.metrics.max_drawdown:.2%}")
    print(f"胜率: {result.metrics.win_rate:.2%}")
```

## 回测报告

### 文本报告

```
==========================
    回测结果
==========================

总收益率: 15.23%
夏普比率: 1.85
最大回撤: -8.45%
胜率: 62.50%
总交易次数: 16

平均盈利: $856.50
平均亏损: -$432.30
盈亏比: 1.98

执行时间: 45.23秒
处理K线数: 744
==========================
```

### HTML 报告

HTML 报告包含：
- 交互式图表
- 详细指标表格
- 交易历史记录
- 性能分析

### JSON 报告

```json
{
  "metrics": {
    "total_return": 0.1523,
    "sharpe_ratio": 1.85,
    "max_drawdown": -0.0845,
    "win_rate": 0.625,
    "total_trades": 16
  },
  "trades": [
    {
      "timestamp": "2024-01-02T10:00:00Z",
      "action": "BUY",
      "price": 65000,
      "quantity": 0.15,
      "pnl": 856.50
    }
  ],
  "execution_time": 45.23
}
```

## 参数优化

### 单参数优化

```python
from vibe_trading.backtest.optimizer import ParameterOptimizer

optimizer = ParameterOptimizer(
    config=config,
    param_name="interval",
    param_values=["15m", "30m", "1h", "4h"]
)

results = await optimizer.optimize()

for result in results:
    print(f"{result.param}: 收益率 {result.return:.2%}")
```

### 多参数优化

```python
optimizer = ParameterOptimizer(
    config=config,
    param_grid={
        "interval": ["15m", "30m", "1h"],
        "llm_mode": [LLMMode.SIMULATED, LLMMode.CACHED]
    }
)

results = await optimizer.optimize_grid()
```

## 高级功能

### 自定义手续费

```python
config = BacktestConfig(
    symbol="BTCUSDT",
    # ... 其他配置
    trading_fees={
        "maker": 0.0002,  # 0.02%
        "taker": 0.0004   # 0.04%
    }
)
```

### 滑点模拟

```python
config = BacktestConfig(
    symbol="BTCUSDT",
    # ... 其他配置
    slippage=0.0005  # 0.05% 滑点
)
```

### 自定义初始仓位

```python
config = BacktestConfig(
    symbol="BTCUSDT",
    # ... 其他配置
    initial_position={
        "symbol": "BTCUSDT",
        "quantity": 0.1,
        "entry_price": 64000
    }
)
```

## 性能优化

### 并行回测

```python
from asyncio import gather

configs = [
    BacktestConfig(symbol="BTCUSDT", interval="15m", ...),
    BacktestConfig(symbol="BTCUSDT", interval="30m", ...),
    BacktestConfig(symbol="BTCUSDT", interval="1h", ...),
]

results = await gather(*[
    BacktestEngine(config).run_backtest()
    for config in configs
])
```

### 缓存优化

```python
# 启用数据缓存
config = BacktestConfig(
    symbol="BTCUSDT",
    # ... 其他配置
    enable_cache=True,
    cache_ttl=3600  # 缓存1小时
)
```

## 故障排除

### 回测失败

**问题**：回测执行失败

**解决方案**：
1. 检查日期格式是否正确
2. 确认指定日期有可用的K线数据
3. 检查 LLM API 配置
4. 查看详细错误日志

### 结果异常

**问题**：回测结果不符合预期

**解决方案**：
1. 使用 `--llm-mode real` 获取更准确的结果
2. 检查交易手续费配置
3. 验证滑点设置
4. 查看详细的交易记录

### 性能慢

**问题**：回测执行速度慢

**解决方案**：
1. 使用 `--llm-mode simulated` 或 `cached`
2. 减少回测时间范围
3. 增大 K线间隔
4. 启用缓存

## 最佳实践

1. **先使用模拟模式测试**
   ```bash
   --llm-mode simulated
   ```

2. **然后使用缓存模式验证**
   ```bash
   --llm-mode cached
   ```

3. **最后使用真实模式确认**
   ```bash
   --llm-mode real
   ```

4. **保存回测报告**
   ```bash
   --report-format html,json
   ```

5. **参数对比分析**
   ```bash
   # 测试不同K线周期
   for interval in 15m 30m 1h 4h; do
       vibe-trade backtest BTCUSDT --start "2024-01-01" --end "2024-01-31" --interval $interval
   done
   ```

## 示例脚本

查看 `demo_backtest.py` 了解更多使用示例。

## 下一步

- 了解 [配置说明](/guide/configuration) 自定义参数
- 学习 [记忆系统](/guide/memory) 优化策略
- 查看 [API文档](/guide/api) 集成回测功能