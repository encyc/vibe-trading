# Agent 工具系统详解

## 概述

Vibe Trading 为不同 Agent 分配专门的工具集，共 23 个工具，按功能分为 5 大类。

## 工具分类

### 1. 技术分析工具 (9个)

#### get_technical_indicators

获取技术指标 (RSI, MACD, 布林带等)

**输入**: symbol, interval, storage
**输出**: Dict 包含所有技术指标

```python
{
    "rsi": 65.2,
    "macd": {"value": 120.5, "signal": "bullish"},
    "bollinger_bands": {"upper": 68000, "middle": 65000, "lower": 62000},
    "atr": 1500.0,
    "sma_20": 64500,
    "sma_50": 63000
}
```

---

#### detect_trend

检测趋势方向和强度

**输入**: symbol, interval, storage, period
**输出**: Dict 包含趋势方向和强度

```python
{
    "trend": "up",
    "strength": 0.75,  # 0-1
    "duration": 12,     # 持续K线数
    "reliability": 0.8
}
```

---

#### detect_divergence

检测指标背离 (价格与指标)

**输入**: symbol, interval, storage
**输出**: Dict 包含背离信息

```python
{
    "type": "bullish",  # bullish/bearish
    "indicator": "RSI",
    "strength": 0.7,
    "description": "价格创新高但RSI未创新高，看涨背离"
}
```

---

#### find_support_resistance

查找支撑位和阻力位

**输入**: symbol, interval, storage
**输出**: Dict 包含关键价位

```python
{
    "support_levels": [64000, 63000, 62000],
    "resistance_levels": [68000, 69000, 70000],
    "current_price": 66000
}
```

---

#### detect_chart_pattern

检测K线形态

**输入**: symbol, interval, storage
**输出**: Dict 包含形态信息

```python
{
    "pattern": "bullish_engulfing",
    "confidence": 0.85,
    "target": 68000,
    "description": "看涨吞没形态，突破概率85%"
}
```

---

#### analyze_volume

成交量分析

**输入**: symbol, interval, storage
**输出**: Dict 包含成交量分析

```python
{
    "volume": 1234567.0,
    "volume_ma": 1000000.0,
    "volume_ratio": 1.23,  # 相对于均值
    "trend": "increasing",  # increasing/decreasing
    "strength": 0.6
}
```

---

#### calculate_pivot_points

计算枢轴点 (支撑1/2, 阻力1/2/3)

**输入**: symbol, interval, storage
**输出**: Dict 包含枢轴点位

```python
{
    "pivot": 65000,
    "support1": 64500,
    "support2": 64000,
    "resistance1": 65500,
    "resistance2": 66000,
    "resistance3": 67000
}
```

---

#### get_atr

获取ATR (真实波幅)

**输入**: symbol, interval, period, storage
**输出**: ATR值

---

#### get_bollinger_bands

获取布林带

**输入**: symbol, interval, period, std_dev, storage
**输出**: Dict 包含上中下轨

---

### 2. 基本面工具 (5个)

#### get_funding_rate

获取资金费率

**输入**: symbol
**输出**: Dict 包含资金费率信息

```python
{
    "current_rate": 0.015,  # 0.015%
    "next_funding_rate": 0.018,
    "funding_time": "2024-01-01 16:00:00"
}
```

---

#### get_long_short_ratio

获取多空比

**输入**: symbol
**输出**: Dict 包含多空比信息

```python
{
    "long_short_ratio": 1.25,  # 多空比
    "long_account": 1.25B,
    "short_account": 1.00B,
    "timestamp": "2024-01-01 00:00:00"
}
```

---

#### get_open_interest

获取持仓量

**输入**: symbol
**输出**: Dict 包含持仓量信息

```python
{
    "open_interest": 2.5e9,  # 25亿USDT
    "open_interest_value": 1.65e11,  # 持仓价值
    "change_24h": 0.05,  # 24h变化
    "timestamp": "2024-01-01 00:00:00"
}
```

---

#### get_taker_buy_sell_volume

获取买卖比例

**输入**: symbol
**输出**: Dict 包含买卖量信息

```python
{
    "buy_volume": 50000,
    "sell_volume": 45000,
    "buy_sell_ratio": 1.11,
    "taker_buy_ratio": 0.53
}
```

---

#### get_whale_long_short_ratio

获取大户多空比

**输入**: symbol
**输出**: Dict 包含大户多空比

---

### 3. 情绪分析工具 (3个)

#### get_fear_greed_index

获取恐惧贪婪指数

**输入**: 无
**输出**: Dict 包含指数值

```python
{
    "value": 72,
    "classification": "greed",
    "timestamp": "2024-01-01 00:00:00"
}
```

---

#### get_news_sentiment

获取新闻情绪

**输入**: symbol, days (可选)
**输出**: Dict 包含情绪分析

```python
{
    "positive": 15,
    "negative": 3,
    "neutral": 7,
    "score": 0.68,  # -1 to 1
    "timestamp": "2024-01-01 00:00:00"
}
```

---

#### get_social_sentiment

获取社交情绪

**输入**: symbol, platform (可选)
**输出**: Dict 包含社交情绪

---

### 4. 风险数据工具 (4个)

#### get_liquidation_orders

获取清算订单

**输入**: symbol, limit (可选)
**输出**: List[Dict] 清算订单列表

---

#### get_top_trader_positions

获取大户持仓

**输入**: symbol, limit (可选)
**输出**: List[Dict] 大户持仓列表

---

#### get_market_sentiment_heatmap

获取情绪热力图

**输入**: symbol
**输出**: Dict 包含热力图数据

---

#### get_exchange_inflow_outflow

获取交易所流入流出

**输入**: exchange, symbol (可选)
**输出**: Dict 包含流入流出数据

---

### 5. 市场数据工具 (2个)

#### get_current_price

获取当前价格

**输入**: symbol
**输出**: Dict 包含当前价格信息

```python
{
    "symbol": "BTCUSDT",
    "price": 67000.50,
    "timestamp": "2024-01-01 00:00:00"
}
```

---

#### get_24hr_ticker

获取24小时行情

**输入**: symbol
**输出**: Dict 包含24h统计数据

```python
{
    "symbol": "BTCUSDT",
    "price_change": 0.025,
    "price_change_percent": 2.5,
    "high": 68500,
    "low": 65000,
    "volume": 1234567.89,
    "quote_volume": 9876543.21
}
```

---

## 工具定义方式

### 使用 @tool 装饰器

```python
from vibe_trading.tools.tool import tool

@tool
async def get_technical_indicators(
    symbol: str,
    interval: str,
    storage: KlineStorage
) -> Dict:
    """
    获取技术指标
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        storage: K线存储实例
    
    Returns:
        技术指标字典
    """
    # 实现逻辑
    ...
```

### 工具参数

- **symbol**: 交易对符号 (如 "BTCUSDT")
- **interval**: K线间隔 (如 "1m", "5m", "15m", "30m", "1h", "4h", "1d")
- **storage**: KlineStorage 实例 (用于获取历史数据)

### 工具返回值

所有工具返回 Dict，包含：
- 请求的数据
- 时间戳
- 错误信息 (如果有)

---

## 工具分配

按Agent角色分配工具：

| Agent | 分配工具 |
|-------|---------|
| 技术分析师 | 所有9个技术分析工具 |
| 基本面分析师 | 所有5个基本面工具 |
| 新闻分析师 | 无专用工具 (使用通用数据工具) |
| 情绪分析师 | 所有3个情绪分析工具 |
| 风控分析师 | 所有4个风险数据工具 |
| 交易员 | 所有市场数据工具 |
| 其他Agent | 按需分配 |

---

## 工具调用示例

### Agent 中调用工具

```python
# Agent初始化时会自动获得工具
class TechnicalAnalystAgent:
    def __init__(self):
        self._agent = None
    
    async def initialize(self, tool_context: ToolContext):
        self._agent = await create_trading_agent(
            config=AgentConfig(
                name="Technical Analyst",
                role="technical_analyst"
            ),
            tool_context=tool_context  # 工具自动分配
        )
    
    async def analyze(self, market_data: Dict) -> str:
        # Agent会自动调用工具
        prompt = "请分析BTCUSDT的技术指标"
        await self._agent.prompt(prompt)
        # Agent内部会调用get_technical_indicators等工具
```

### LLM 函数调用

```python
# Agent发送的Prompt
"""
请分析BTCUSDT的技术指标

可用工具:
- get_technical_indicators
- detect_trend
- find_support_resistance

请调用这些工具获取数据并分析。
"""

# LLM会自动调用
await agent.prompt(prompt)

# 内部流程
# 1. 解析工具描述
# 2. 生成函数调用
# 3. 执行工具
# 4. 返回结果给LLM
# 5. LLM基于结果生成回复
```

---

## 工具实现细节

### 数据获取流程

```
Agent Tool Call
    ↓
Tool Function
    ↓
Data Source (Binance API / Storage)
    ↓
Process & Format
    ↓
Return to Agent
```

### 错误处理

```python
@tool
async def get_current_price(symbol: str) -> Dict:
    try:
        # 尝试从API获取
        price = await binance_api.get_symbol_price(symbol)
        return {"price": price, "source": "api"}
    except Exception as e:
        # 回退到存储
        kline = await storage.get_latest_kline(symbol)
        if kline:
            return {"price": kline.close, "source": "storage"}
        else:
            return {"error": str(e)}
```

---

## 扩展工具

### 添加新工具

1. 在 `tools/` 中创建工具函数
2. 使用 `@tool` 装饰器
3. 在 `config/agent_config.py` 中分配给Agent

### 示例

```python
@tool
async def custom_indicator(
    symbol: str,
    interval: str,
    period: int = 14
) -> Dict:
    """自定义指标
    
    Args:
        symbol: 交易对符号
        interval: K线间隔
        period: 周期
    
    Returns:
        指标值
    """
    # 实现逻辑
    return {"value": 100, "signal": "buy"}
```

---

## 工具性能优化

### 缓存策略

```python
@tool
async def get_funding_rate(symbol: str) -> Dict:
    # 检查缓存
    cache_key = f"funding_rate_{symbol}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    # 获取数据
    data = await api.get_funding_rate(symbol)
    
    # 缓存5分钟
    await cache.set(cache_key, data, ttl=300)
    return data
```

### 并行请求

```python
async def get_multiple_indicators(symbols: List[str]) -> List[Dict]:
    tasks = [get_technical_indicators(s) for s in symbols]
    results = await asyncio.gather(*tasks)
    return results
```
