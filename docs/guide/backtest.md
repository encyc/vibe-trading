# 回测系统

Vibe Trading 提供强大的历史数据回测系统，帮助你在不使用真实资金的情况下验证交易策略。

## 回测特性

### 核心改进

1. **自动Lookback数据加载**
   - 系统自动计算技术指标所需的历史数据量
   - 例如：MACD(12,26,9)会自动加载35根历史K线
   - 确保回测第一天所有指标都有值

2. **Agent回测模式适配**
   - Agents在回测时自动使用历史数据
   - 支持历史资金费率、新闻、情绪等数据
   - 实时API调用自动切换为历史数据查询

3. **LLM优化器集成**
   - 决策缓存机制加速回测
   - 支持SIMULATED、CACHED、REAL三种模式
   - 实时统计LLM调用和缓存命中率

4. **检查点保存/恢复**
   - 定期保存回测进度
   - 支持从中断点继续
   - 适合长时间回测任务

5. **增强的结果导出**
   - 自动导出交易记录到CSV
   - 生成HTML、JSON、TEXT多种格式报告
   - 包含完整的元数据和统计信息

### 支持的 LLM 模式

1. **SIMULATED（模拟模式）**
   - 使用模拟的 LLM 响应
   - 速度最快，适合快速测试
   - 不消耗 API 额度

2. **CACHED（缓存模式）**
   - 缓存真实的 LLM 响应
   - 相同输入返回相同结果
   - 适合重复测试
   - 推荐用于大部分回测场景

3. **REAL（真实模式）**
   - 调用真实的 LLM API
   - 结果最准确
   - 消耗 API 额度
   - 适合最终验证

### 回测指标

- 总收益率
- 夏普比率
- 最大回撤
- 胜率
- 总交易次数
- 平均盈利/亏损
- 盈亏比
- 卡玛比率
- VaR (95%, 99%)
- 期望亏损 (ES)
- 平均持仓时间

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

### 自动Lookback数据加载

系统会自动根据技术指标配置加载额外的历史数据：

```python
# 无需手动配置，系统自动处理
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1d",
    start_time=datetime(2026, 1, 1),
    end_time=datetime(2026, 1, 31),
)

# 系统会自动：
# 1. 计算所有指标的lookback需求（如MACD需要35根K线）
# 2. 加载额外的历史数据（2025-11-27 ~ 2026-01-31）
# 3. 将lookback数据传递给技术指标计算
# 4. 只在回测期间（2026-01-01 ~ 2026-01-31）执行交易
```

### 检查点保存和恢复

长时间回测时，启用检查点功能可以从中断点继续：

```python
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    start_time=datetime(2026, 1, 1),
    end_time=datetime(2026, 12, 31),
    # 启用检查点
    save_checkpoints=True,
    checkpoint_interval=500,  # 每500根K线保存一次
    checkpoint_dir="./checkpoints",
)

# 运行回测（如果中断，可以从检查点恢复）
engine = BacktestEngine(config)
result = await engine.run_backtest()

# 从检查点恢复
config_resume = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    start_time=datetime(2026, 1, 1),
    end_time=datetime(2026, 12, 31),
    # 指定检查点文件
    resume_from_checkpoint="./checkpoints/BTCUSDT_1h_kline500_20250101_120000.json",
)
```

### 历史数据存储

系统支持多种历史数据的存储和检索：

```python
from vibe_trading.data_sources.fundamental_storage import FundamentalStorage
from vibe_trading.data_sources.news_storage import NewsStorage
from vibe_trading.data_sources.sentiment_storage import SentimentStorage

# 资金费率数据
fundamental_storage = FundamentalStorage()
await fundamental_storage.init()
await fundamental_storage.save_fundamental_data(FundamentalData(
    symbol="BTCUSDT",
    timestamp=int(datetime(2026, 1, 1).timestamp() * 1000),
    funding_rate=0.0001,
    mark_price=45000.0,
    index_price=45050.0,
    open_interest=1000000,
    open_interest_value=45000000000,
))

# 新闻数据
news_storage = NewsStorage()
await news_storage.init()
await news_storage.save_news(NewsData(
    symbol="BTCUSDT",
    timestamp=int(datetime(2026, 1, 1).timestamp() * 1000),
    title="Bitcoin reaches new high",
    content="...",
    url="https://example.com/news1",
    source="Reuters",
    sentiment="positive",
    sentiment_score=0.8,
    relevance_score=0.9,
    categories=["market", "btc"],
))

# 情绪数据
sentiment_storage = SentimentStorage()
await sentiment_storage.init()
await sentiment_storage.save_sentiment(SentimentData(
    symbol="GLOBAL",
    timestamp=int(datetime(2026, 1, 1).timestamp() * 1000),
    fear_greed_value=65,
    fear_greed_classification="Greed",
))
```

### 进度追踪

使用ProgressTracker实时追踪回测进度：

```python
from vibe_trading.backtest.progress import ProgressTracker

# 创建进度追踪器
tracker = ProgressTracker(task_id="backtest_001")

# 添加回调函数
def on_progress_update(update):
    print(f"进度: {update.progress_percentage:.1f}%")
    print(f"当前权益: {update.current_equity:.2f}")
    print(f"总交易: {update.total_trades}")
    if update.estimated_remaining_seconds:
        print(f"预计剩余时间: {update.estimated_remaining_seconds:.0f}秒")

tracker.add_callback(on_progress_update)

# 在回测中使用
async def run_backtest_with_progress():
    tracker.start(total_klines=1000)

    for i, kline in enumerate(klines):
        # 处理K线...
        tracker.update(
            current_kline=i + 1,
            current_equity=current_balance,
            total_trades=len(trades),
            open_trades=len(open_positions),
        )

    tracker.complete()
```

### 决策采样优化

通过决策采样减少LLM调用次数，加速回测：

```python
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    # 每5根K线决策一次（而不是每根）
    decision_interval=5,
    # 价格变化超过3%时触发额外决策
    significant_change_threshold=0.03,
)

# 适用场景：
# - 长时间回测（数月或数年）
# - 高频K线（1m, 5m, 15m）
# - 快速策略测试
```

### Agent回测模式配置

配置特定Agent在回测时的行为：

```python
# 禁用没有历史数据的Agent
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    # 如果没有新闻和情绪数据，禁用相关Agent
    agents={
        "news_analyst": {"enabled": False},
        "sentiment_analyst": {"enabled": False},
    },
)
```

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

## 配置文件

除了命令行参数，你还可以使用YAML配置文件：

```bash
# 使用配置文件运行回测
vibe-trade backtest --config my_backtest.yaml
```

配置文件示例：

```yaml
# 基础配置
symbol: "BTCUSDT"
interval: "1d"
start_time: "2026-01-01 00:00:00"
end_time: "2026-01-31 23:59:59"
initial_balance: 10000.0

# LLM配置
llm_mode: "cached"

# 检查点配置
save_checkpoints: true
checkpoint_interval: 100
checkpoint_dir: "./checkpoints"

# 报告配置
report_formats:
  - "text"
  - "html"
  - "json"

# 执行配置
decision_interval: 1
significant_change_threshold: 0.02

# Agent配置
agents:
  news_analyst:
    enabled: false
  sentiment_analyst:
    enabled: false
```

完整配置示例请参考：[backtest_config.example.yaml](/backtest_config.example.yaml)

## 数据准备

### K线数据

系统会自动从Binance加载K线数据，并缓存到本地SQLite数据库：

```python
# 首次运行会自动下载
config = BacktestConfig(
    symbol="BTCUSDT",
    interval="1h",
    start_time=datetime(2026, 1, 1),
    end_time=datetime(2026, 1, 31),
)
# 数据会自动缓存到 data/klines.db
```

### 历史基本面数据

准备资金费率等基本面数据：

```python
# 从Binance API获取并存储
from vibe_trading.data_sources.binance_client import BinanceClient

client = BinanceClient()
funding_rates = await client.rest.get_funding_rate_history(
    symbol="BTCUSDT",
    limit=1000,
)

# 存储到数据库
storage = FundamentalStorage()
await storage.init()
for rate in funding_rates:
    await storage.save_fundamental_data(FundamentalData(...))
```

### 历史新闻数据

从新闻API获取并存储：

```python
# 示例：从CryptoCompare API获取新闻
import requests

news_data = requests.get(
    "https://min-api.cryptocompare.com/data/v2/news/",
    params={"lang": "EN"}
).json()

storage = NewsStorage()
await storage.init()
for item in news_data["Data"]:
    await storage.save_news(NewsData(
        symbol="BTCUSDT",
        timestamp=int(item["published_on"] * 1000),
        title=item["title"],
        content=item["body"],
        url=item["url"],
        source=item["source"],
        sentiment="neutral",  # 需要情绪分析
        sentiment_score=0.0,
        relevance_score=item["score"] / 10,  # 转换为0-1范围
        categories=[],
    ))
```

## 最佳实践

1. **分阶段测试**
   ```bash
   # 阶段1：快速模拟测试
   vibe-trade backtest BTCUSDT --start "2026-01-01" --end "2026-01-07" --llm-mode simulated

   # 阶段2：缓存模式验证
   vibe-trade backtest BTCUSDT --start "2026-01-01" --end "2026-01-31" --llm-mode cached

   # 阶段3：完整回测
   vibe-trade backtest BTCUSDT --start "2026-01-01" --end "2026-12-31" --llm-mode cached --save-checkpoints
   ```

2. **使用检查点处理长时间回测**
   ```bash
   # 启用检查点
   --save-checkpoints --checkpoint-interval 1000

   # 如果中断，从检查点恢复
   --resume-from ./checkpoints/BTCUSDT_1d_kline5000_20250101.json
   ```

3. **优化决策频率**
   ```bash
   # 对于低频策略，减少决策次数
   --decision-interval 5 --significant-change-threshold 0.03
   ```

4. **准备历史数据**
   ```python
   # 提前导入数据以加速回测
   # 1. K线数据会自动缓存
   # 2. 基本面数据需要手动导入
   # 3. 新闻和情绪数据可选

   # 导入脚本示例
   python scripts/import_funding_rates.py --symbol BTCUSDT --start 2026-01-01 --end 2026-12-31
   ```

5. **参数对比分析**
   ```bash
   # 测试不同K线周期
   for interval in 15m 30m 1h 4h; do
       vibe-trade backtest BTCUSDT --start "2026-01-01" --end "2026-01-31" --interval $interval
   done

   # 测试不同LLM模式
   for mode in simulated cached real; do
       vibe-trade backtest BTCUSDT --start "2026-01-01" --end "2026-01-31" --llm-mode $mode
   done
   ```

6. **保存和对比结果**
   ```bash
   # 导出多种格式
   --report-format html,json

   # 结果会保存到：
   # - ./backtest_results/trades_*.csv
   # - ./backtest_results/report_*.html
   # - ./backtest_results/result_*.json
   ```

## 示例脚本

查看 `demo_backtest.py` 了解更多使用示例。

## 下一步

- 了解 [配置说明](/guide/configuration) 自定义参数
- 学习 [记忆系统](/guide/memory) 优化策略
- 查看 [API文档](/guide/api) 集成回测功能