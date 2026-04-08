# 记忆系统

Vibe Trading 的记忆系统基于 BM25 算法，能够从历史交易经验中学习，持续优化决策策略。

## 记忆系统概述

### 核心功能

1. **决策记录**：记录所有决策及其结果
2. **经验检索**：快速检索相关的历史决策
3. **模式识别**：识别成功和失败的模式
4. **策略优化**：基于经验优化决策参数

### BM25 算法

BM25 是一种经典的文本检索算法，用于评估文档与查询的相关性：

```
BM25(D,Q) = Σ IDF(qi) × (f(qi,D) × (k1 + 1)) / (f(qi,D) + k1 × (1 - b + b × |D|/avgdl))
```

其中：
- `D`：文档（历史决策）
- `Q`：查询（当前市场情况）
- `f(qi,D)`：词项频率
- `|D|`：文档长度
- `avgdl`：平均文档长度
- `k1`, `b`：自由参数

## 使用记忆系统

### 存储决策

```python
from vibe_trading.memory.memory import PersistentMemory

memory = PersistentMemory()

# 存储决策
await memory.store_decision({
    "symbol": "BTCUSDT",
    "decision": "BUY",
    "price": 65000,
    "quantity": 0.2,
    "timestamp": "2024-01-01T12:00:00Z",
    "rationale": "技术面和基本面支持上涨",
    "market_conditions": {
        "trend": "upward",
        "rsi": 65,
        "volume": "high"
    },
    "outcome": {
        "pnl": 500,
        "return": 0.05,
        "success": True
    }
})
```

### 检索相关经验

```python
# 根据市场条件检索相关决策
query = {
    "symbol": "BTCUSDT",
    "market_conditions": {
        "trend": "upward",
        "rsi": [60, 70]  # RSI在60-70之间
    }
}

# 检索最相关的10条决策
results = await memory.retrieve_decisions(query, top_k=10)

for result in results:
    print(f"决策: {result['decision']}")
    print(f"收益率: {result['outcome']['return']:.2%}")
    print(f"相关性: {result['score']:.3f}")
```

### 学习模式

```python
# 分析成功模式
success_patterns = await memory.analyze_patterns(
    min_return=0.05,  # 收益率>5%
    outcome="success"
)

print("成功模式:")
for pattern in success_patterns:
    print(f"- {pattern}")

# 分析失败模式
failure_patterns = await memory.analyze_patterns(
    max_return=-0.02,  # 收益率<-2%
    outcome="failure"
)

print("失败模式:")
for pattern in failure_patterns:
    print(f"- {pattern}")
```

## 集成到 Agent

### 在决策中使用记忆

```python
from vibe_trading.memory.memory import PersistentMemory

class TechnicalAnalystAgent:
    def __init__(self):
        self.memory = PersistentMemory()
    
    async def analyze(self, context):
        # 分析当前市场
        current_analysis = await self._analyze_market(context)
        
        # 检索相关历史决策
        query = {
            "symbol": context.symbol,
            "market_conditions": current_analysis
        }
        similar_decisions = await self.memory.retrieve_decisions(query, top_k=5)
        
        # 根据历史经验调整分析
        adjusted_analysis = self._adjust_with_memory(
            current_analysis,
            similar_decisions
        )
        
        return adjusted_analysis
```

## 配置记忆系统

### 配置参数

```python
class MemoryConfig:
    # 存储配置
    storage_path: str = "memory/decisions.db"
    max_decisions: int = 10000  # 最大存储决策数
    
    # BM25 参数
    k1: float = 1.2  # 控制词频饱和度
    b: float = 0.75  # 控制文档长度归一化
    
    # 检索配置
    default_top_k: int = 10
    min_similarity: float = 0.5
    
    # 学习配置
    enable_learning: bool = True
    learning_rate: float = 0.1
    min_samples: int = 10  # 最小学习样本数
```

### 修改配置

```python
from vibe_trading.memory.memory import PersistentMemory, MemoryConfig

config = MemoryConfig(
    k1=1.5,  # 增加词频权重
    b=0.8,   # 增加文档长度权重
    default_top_k=20  # 检索更多相关决策
)

memory = PersistentMemory(config=config)
```

## 高级功能

### 语义相似度

```python
# 使用向量相似度
from vibe_trading.memory.semantic_memory import SemanticMemory

semantic_memory = SemanticMemory()

# 添加决策
await semantic_memory.add_decision(decision_data)

# 语义检索
similar = await semantic_memory.semantic_search(
    query="上升趋势，RSI超买",
    top_k=5
)
```

### 时间衰减

```python
# 近期决策权重更高
results = await memory.retrieve_decisions(
    query,
    top_k=10,
    time_decay=True,  # 启用时间衰减
    decay_days=30  # 30天内的决策权重更高
)
```

### 多维度检索

```python
# 综合多个维度检索
results = await memory.multi_dimensional_search({
    "symbol": "BTCUSDT",
    "trend": "upward",
    "rsi_range": [60, 70],
    "time_range": ["2024-01-01", "2024-01-31"],
    "min_return": 0.03
})
```

## 性能优化

### 索引优化

```python
# 为常用查询创建索引
await memory.create_index("symbol")
await memory.create_index("timestamp")
await memory.create_index("outcome")
```

### 批量操作

```python
# 批量存储决策
decisions = [decision1, decision2, decision3, ...]
await memory.batch_store(decisions)
```

### 缓存策略

```python
# 启用缓存
memory.enable_cache(ttl=3600)  # 缓存1小时

# 预热缓存
await memory.warmup_cache()
```

## 监控和分析

### 统计信息

```python
# 获取记忆系统统计
stats = await memory.get_statistics()

print(f"总决策数: {stats['total_decisions']}")
print(f"成功决策: {stats['successful_decisions']}")
print(f"失败决策: {stats['failed_decisions']}")
print(f"平均收益率: {stats['avg_return']:.2%}")
```

### 性能分析

```python
# 分析检索性能
perf = await memory.analyze_performance()

print(f"平均检索时间: {perf['avg_query_time']:.3f}ms")
print(f"缓存命中率: {perf['cache_hit_rate']:.2%}")
```

## 最佳实践

1. **定期清理**：删除过时的决策数据
   ```python
   await memory.cleanup(before_days=90)
   ```

2. **平衡检索**：避免过度依赖历史经验
   ```python
   # 结合当前分析和历史经验
   final_decision = blend(
       current_analysis=0.7,
       historical_experience=0.3
   )
   ```

3. **验证模式**：验证识别的模式是否有效
   ```python
   pattern_confidence = await memory.validate_pattern(pattern)
   if pattern_confidence > 0.8:
       apply_pattern(pattern)
   ```

4. **持续学习**：定期更新记忆系统
   ```python
   # 每天学习新经验
   await memory.learn_from_recent_trades(days=1)
   ```

## 故障排除

### 检索结果不相关

**问题**：检索到的决策与当前情况不相关

**解决方案**：
1. 调整 BM25 参数
2. 优化查询条件
3. 增加决策描述的详细程度

### 性能问题

**问题**：检索速度慢

**解决方案**：
1. 创建索引
2. 启用缓存
3. 减少存储的决策数量

### 记忆偏差

**问题**：过度依赖历史经验

**解决方案**：
1. 降低历史经验的权重
2. 增加随机性
3. 定期清理过时数据

## 示例应用

### 策略优化

```python
# 基于记忆优化止损止盈
from vibe_trading.memory.memory import PersistentMemory

memory = PersistentMemory()

# 分析成功交易的止损止盈设置
successful_trades = await memory.retrieve_decisions(
    {"outcome": "success"},
    top_k=100
)

# 计算最佳止损止盈比例
avg_stop_loss = calculate_avg(
    [t['stop_loss'] for t in successful_trades]
)
avg_take_profit = calculate_avg(
    [t['take_profit'] for t in successful_trades]
)

print(f"建议止损: {avg_stop_loss:.2%}")
print(f"建议止盈: {avg_take_profit:.2%}")
```

### 风险预警

```python
# 基于历史经验预警风险
query = {
    "symbol": "BTCUSDT",
    "market_conditions": current_conditions
}

similar_failures = await memory.retrieve_decisions(
    query,
    top_k=10,
    outcome="failure"
)

if len(similar_failures) > 5:
    print("警告：当前市场条件下历史失败率较高！")
    print("建议：降低仓位或暂不交易")
```

## 下一步

- 学习 [自定义Agent](/guide/custom-agent) 集成记忆系统
- 查看 [配置说明](/guide/configuration) 优化参数
- 了解 [API文档](/guide/api) 使用记忆API