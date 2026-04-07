# 风险管理详解

## 概述

Vibe Trading 采用多层次风险管理策略，从资金安全、操作规范、行为边界、资源控制四个维度保护资金安全。

## 4层约束系统

### 1. 安全约束 (SafetyConstraint)

**目标**: 保护资金安全，防止单笔交易过大

**限制项**:
- `max_single_trade`: 单笔交易最大金额 (纸面: $1000, 实盘: $100)
- `max_total_position`: 总仓位最大比例 (30%)
- `max_leverage`: 最大杠杆 (5x)

**检查点**:
- 每笔交易前
- 每次开仓前
- 每次加仓前

**违规处理**: BLOCK (阻止交易)

---

### 2. 操作约束 (OperationalConstraint)

**目标**: 防止过度交易和频繁操作

**限制项**:
- `min_trade_interval`: 最小交易间隔 (60秒)
- `max_direction_changes`: 最大方向改变次数 (3次/小时)
- `max_daily_trades`: 每日最大交易次数 (20次)

**检查点**:
- 每次交易前
- 每次改变方向前

**违规处理**: WARN (警告并记录)

---

### 3. 行为约束 (BehavioralConstraint)

**目标**: 确保Agent在职责范围内工作

**规则**:
- Agent只能在自己的领域内做决策
- 禁止某些Agent直接下单 (只能提供建议)
- 决策一致性检查

**检查点**:
- 每次Agent消息
- 每次决策请求

**违规处理**: WARN (警告并记录)

---

### 4. 资源约束 (ResourceConstraint)

**目标**: 控制LLM调用成本和频率

**限制项**:
- `max_llm_calls_per_day`: 每日最大LLM调用次数 (1000次)
- `max_daily_cost`: 每日最大成本 ($10)
- `max_tokens_per_message`: 每条消息最大token数 (8000)

**检查点**:
- 每次LLM调用前
- 每日00:00重置计数器

**违规处理**: LOG (记录日志)

---

## 风险评估流程

### 1. 交易前风险检查

```python
async def pre_trade_risk_check(decision: Decision):
    # 1. 安全约束检查
    if decision.quantity > config.max_single_trade:
        raise RiskError("交易金额超过限制")
    
    if current_position + decision.quantity > max_total_position:
        raise RiskError("总仓位超过限制")
    
    # 2. 操作约束检查
    if time_since_last_trade < min_trade_interval:
        raise RiskError("交易频率过高")
    
    # 3. 行为约束检查
    if not agent.can_direct_trade:
        raise RiskError("Agent无直接交易权限")
    
    # 4. 资源约束检查
    if llm_calls_today >= max_llm_calls:
        raise ResourceError("LLM调用次数超限")
```

### 2. 仓位管理

#### 凯利公式仓位

```python
def kelly_position_size(
    win_rate: float,
    avg_win_loss_ratio: float,
    current_capital: float,
    kelly_fraction: float = 0.25  # 保守凯利
) -> float:
    """
    计算凯利公式仓位大小
    
    Args:
        win_rate: 胜率
        avg_win_loss_ratio: 平均盈亏比
        current_capital: 当前资金
        kelly_fraction: 凯利分数 (0.25为保守)
    
    Returns:
        仓位大小
    """
    win_loss_ratio = win_rate * avg_win_loss_ratio - (1 - win_rate)
    optimal_fraction = win_loss_ratio / avg_win_loss_ratio
    return current_capital * optimal_fraction * kelly_fraction
```

#### 波动率调整

```python
def adjust_for_volatility(
    base_position: float,
    current_volatility: float,
    avg_volatility: float
) -> float:
    """
    根据波动率调整仓位
    
    Args:
        base_position: 基础仓位
        current_volatility: 当前波动率
        avg_volatility: 平均波动率
    
    Returns:
        调整后的仓位
    """
    volatility_ratio = current_volatility / avg_volatility
    # 波动率越大，仓位越小
    adjusted = base_position / (volatility_ratio ** 0.5)
    return min(adjusted, base_position * 1.5)
```

### 3. 止损止盈

#### 止损策略

1. **固定百分比止损**
   - 激进风控: 3%
   - 中立风控: 2%
   - 保守风控: 1.5%

2. **ATR止损**
   ```python
   atr_stop = entry_price - (atr * 2)  # 2倍ATR
   ```

3. **追踪止损**
   ```python
   if unrealized_pnl > 0:
       # 保护部分利润
       trailing_stop = max(
           entry_price * 1.02,  # 2%追踪止损
           current_price * 0.98   # 2%保护
       )
   ```

#### 止盈策略

1. **目标价位止盈**
   ```python
   take_profit = entry_price * (1 + target_pct)
   ```

2. **分批止盈**
   ```python
   # 达到第一目标，卖出30%
   if price >= target1:
       sell(quantity * 0.3)
   # 达到第二目标，卖出30%
   if price >= target2:
       sell(quantity * 0.3)
   # 剩余仓位持有
   ```

3. **时间止盈**
   ```python
   # 如果N小时后未达到目标，平仓
   if hold_time > max_hold_time:
       sell_all()
   ```

---

## 风险指标

### VaR (Value at Risk)

**定义**: 在给定置信水平下，可能的最大损失

**计算方法**: 历史模拟法

```python
def calculate_var(
    returns: List[float],
    confidence_level: float = 0.95
) -> float:
    """
    计算VaR
    
    Args:
        returns: 历史收益率列表
        confidence_level: 置信水平 (0.95 = 95%)
    
    Returns:
        VaR值 (负数表示损失)
    """
    sorted_returns = sorted(returns)
    index = int((1 - confidence_level) * len(sorted_returns))
    return sorted_returns[index]
```

**使用**:
- 每日计算VaR
- 如果VaR超过阈值 (2%)，减少仓位

### 最大回撤 (Max Drawdown)

```python
def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """
    计算最大回撤
    
    Args:
        equity_curve: 权益曲线
    
    Returns:
        最大回撤比例
    """
    peak = equity_curve[0]
    max_dd = 0.0
    
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak
        max_dd = max(max_dd, drawdown)
    
    return max_dd
```

### 夏普比率 (Sharpe Ratio)

```python
def calculate_sharpe_ratio(
    returns: List[float],
    risk_free_rate: float = 0.02
) -> float:
    """
    计算夏普比率
    
    Args:
        returns: 历史收益率列表
        risk_free_rate: 无风险利率
    
    Returns:
        夏普比率
    """
    avg_return = np.mean(returns)
    std_return = np.std(returns)
    
    if std_return == 0:
        return 0
    
    excess_return = avg_return - risk_free_rate
    return excess_return / std_return
```

---

## 紧急风险处理

### 价格暴跌处理

**触发条件**: 价格下跌 > 5%

**处理流程**:
1. Prime Agent检测到暴跌
2. 发送CLOSE_ALL信号
3. 强制平仓所有仓位
4. 记录事件并分析

**代码**:
```python
if price_change < -0.05:
    decision = Decision(
        action=TradingAction.CLOSE_ALL,
        reason=f"价格暴跌 {price_change:.2%}, 强制平仓",
        override=True,
        priority=DecisionPriority.CRITICAL
    )
    await execute_emergency_decision(decision)
```

### 风险超标处理

**触发条件**: 保证金比例 > 80%

**处理流程**:
1. 检测到保证金比例过高
2. 计算需要减仓的数量
3. 发送REDUCE_POSITION信号
4. 执行减仓操作

**代码**:
```python
if margin_ratio > 0.8:
    reduce_amount = current_position * 0.5  # 减仓50%
    
    decision = Decision(
        action=TradingAction.REDUCE_POSITION,
        reason=f"保证金比例 {margin_ratio:.2%} 过高，减仓50%",
        quantity=reduce_amount,
        override=True
    )
```

### 连续亏损处理

**触发条件**: 连续亏损 > 5次

**处理流程**:
1. 记录连续亏损
2. 降低仓位大小
3. 暂停交易N小时
4. 分析亏损原因

**代码**:
```python
if consecutive_losses >= 5:
    # 降低仓位
    max_position_ratio = 0.1  # 最多10%仓位
    
    # 暂停交易
    await pause_trading(hours=4)
    
    # 记录事件
    logger.warning(f"连续{consecutive_losses}次亏损，暂停交易4小时")
```

---

## 风险报告

### 每日风险报告

```python
async def generate_daily_risk_report():
    report = {
        "date": datetime.now().date(),
        "var_95": calculate_var(returns, 0.95),
        "max_drawdown": calculate_max_drawdown(equity),
        "sharpe_ratio": calculate_sharpe_ratio(returns),
        "total_trades": trade_count,
        "win_rate": win_rate,
        "avg_risk_per_trade": avg_risk,
        "risk_events": risk_events
    }
    
    # 存储报告
    await store_risk_report(report)
```

### 实时风险监控

```python
async def monitor_real_time_risk():
    while True:
        # 1. 获取当前仓位
        current_position = await get_current_position()
        
        # 2. 计算未实现盈亏
        unrealized_pnl = calculate_unrealized_pnl()
        
        # 3. 检查风险指标
        if unrealized_pnl < -account_balance * 0.1:
            await send_alert("未实现亏损超过10%")
        
        # 4. 检查保证金
        margin_ratio = await get_margin_ratio()
        if margin_ratio > 0.8:
            await send_alert("保证金比例过高")
        
        await asyncio.sleep(10)  # 每10秒检查一次
```

---

## 风险参数配置

### 保守型配置

```yaml
safety:
  max_single_trade: 500      # $500
  max_total_position: 0.2    # 20%
  max_leverage: 3            # 3x

operational:
  min_trade_interval: 300    # 5分钟
  max_direction_changes: 2   # 2次/小时
  max_daily_trades: 10       # 10次

resource:
  max_llm_calls_per_day: 500
  max_daily_cost: 5.0
```

### 激进型配置

```yaml
safety:
  max_single_trade: 2000     # $2000
  max_total_position: 0.5    # 50%
  max_leverage: 10           # 10x

operational:
  min_trade_interval: 30     # 30秒
  max_direction_changes: 5   # 5次/小时
  max_daily_trades: 30       # 30次

resource:
  max_llm_calls_per_day: 2000
  max_daily_cost: 20.0
```

---

## 风险合规检查清单

在执行交易前，必须检查：

- [ ] 单笔交易金额是否在限制内？
- [ ] 总仓位是否超限？
- [ ] 杠杆是否在允许范围内？
- [ ] 交易频率是否过高？
- [ ] 是否连续亏损？
- [ ] 保证金是否充足？
- [ ] LLM调用次数是否超限？
- [ ] Agent是否有权限执行此操作？
- [ ] 决策是否符合交易策略？

---

## 风险事件记录

所有风险事件记录到数据库：

```sql
CREATE TABLE risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT,
    severity TEXT,
    description TEXT,
    action_taken TEXT,
    result TEXT
);
```

示例记录：
```json
{
    "timestamp": "2024-01-01 12:30:00",
    "event_type": "price_drop",
    "severity": "CRITICAL",
    "description": "BTC价格从68000暴跌至64000 (-5.9%)",
    "action_taken": "CLOSE_ALL",
    "result": "成功平仓，损失-$2000"
}
```
