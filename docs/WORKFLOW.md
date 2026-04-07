# 阶段间协作流程

## 完整决策流程

```
新K线到达
  ↓
┌─────────────────────────────────────────┐
│  Phase 1: 分析师团队（并行执行）        │
│  ┌───────────────────────────────────┐  │
│  │ 技术分析师                         │  │
│  │ - 技术指标分析                    │  │
│  │ - 趋势检测                        │  │
│  │ - 支撑阻力位                      │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ 基本面分析师                       │  │
│  │ - 资金费率                        │  │
│  │ - 多空比                          │  │
│  │ - 持仓量分析                      │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ 新闻分析师                         │  │
│  │ - 宏观新闻                        │  │
│  │ - 政策变化                        │  │
│  │ - 重大事件                        │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ 情绪分析师                         │  │
│  │ - 恐惧贪婪指数                    │  │
│  │ - 新闻情绪                         │  │
│  │ - 社交情绪                         │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Phase 2: 研究员团队（辩论）           │
│                                         │
│  看涨研究员 ───┐                     ┌──┘ 看跌研究员 │
│              │ 多轮辩论               │               │
│              │ 论点提取               │               │
│  ┌───────────┴───────────┐              │  │
│  │                           │              │  │
│  └───────────┬───────────┘              │  │
│              ↓                          │  │
│  ┌───────────────────────┐              │  │
│  │   研究经理            │              │  │
│  │   - 量化辩论质量      │              │  │
│  │   - 生成投资建议      │              │  │
│  │   - LONG/SHORT/HOLD   │              │  │
│  │   - 置信度评分         │              │  │
│  └───────────────────────┘              │  │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Phase 3: 风控团队（风险评估）         │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │   激进风控                           │  │
│  │   - 高收益高风险                     │  │
│  │   - 建议仓位: 20-30%                │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │   中立风控                           │  │
│  │   - 平衡风险收益                     │  │
│  │   - 建议仓位: 10-20%                │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │   保守风控                           │  │
│  │   - 保护本金优先                     │  │
│  │   - 建议仓位: 5-10%                 │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────┐
│  Phase 4: 决策层（执行计划）           │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │   交易员                            │  │
│  │   - 制定执行计划                     │  │
│  │   - 仓位大小计算                     │  │
│  │   - 进出场点位                       │  │
│  │   - 止损止盈                         │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │   投资组合经理                       │  │
│  │   - 最终决策审批                     │  │
│  │   - 综合评估                         │  │
│  │   - BUY/SELL/HOLD                   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
  ↓
最终决策 → 执行交易 或 观望
```

## 阶段间数据传递

### Phase 1 → Phase 2

分析师报告 → 研究员辩论

```python
# 技术分析报告
tech_report = {
    "trend": "up",
    "strength": 0.8,
    "support": 65000,
    "resistance": 68000
}

# 作为研究员的输入
bull_researcher.prompt(
    f"技术分析显示{tech_report['trend']}趋势，"
    f"强度{tech_report['strength']}，"
    f"支撑位在{tech_report['support']}"
)
```

### Phase 2 → Phase 3

投资建议 → 风控评估

```python
# 研究经理输出
recommendation = {
    "direction": "LONG",
    "confidence": 0.75,
    "reasoning": "技术面和基本面都支持上涨"
}

# 风控输入
risk_assessment = await risk_agent.assess_risk(
    investment_plan=recommendation,
    current_positions=positions,
    account_balance=balance
)
```

### Phase 3 → Phase 4

风控评估 → 交易计划

```python
# 风控输出
risk_assessment = {
    "position_size_pct": 0.20,  # 20%仓位
    "stop_loss_pct": 0.03,      # 3%止损
    "take_profit_pct": 0.06     # 6%止盈
}

# 交易员输入
trading_plan = await trader.create_trading_plan(
    direction="LONG",
    risk_assessment=risk_assessment,
    current_price=67000
)
```

### Phase 4 → 最终决策

交易计划 → 最终决策

```python
# 交易员输出
trading_plan = TradingPlan(
    direction="LONG",
    quantity=0.2,
    entry_price=67000,
    stop_loss=65010,
    take_profit=71020
)

# 投资组合经理决策
final_decision = await portfolio_manager.make_final_decision(
    analyst_reports=reports,
    investment_plan=recommendation,
    trading_plan=trading_plan,
    risk_debate=risk_debate
)
```

## 消息传递机制

### AgentMessage 结构

```python
AgentMessage(
    message_id="msg_001",
    correlation_id="corr_001",  # 关联相关消息
    sender="technical_analyst",
    receiver="bull_researcher",
    message_type=MessageType.TECHNICAL_ANALYSIS,
    content={...},
    timestamp=datetime.now()
)
```

### 消息类型映射

| 发送者 | 接收者 | 消息类型 |
|--------|--------|----------|
| 技术分析师 | 看涨/看跌研究员 | TECHNICAL_ANALYSIS |
| 基本面分析师 | 看涨/看跌研究员 | FUNDAMENTAL_ANALYSIS |
| 新闻分析师 | 看涨/看跌研究员 | NEWS_ANALYSIS |
| 情绪分析师 | 看涨/看跌研究员 | SENTIMENT_ANALYSIS |
| 看涨研究员 | 研究经理 | BULL_ARGUMENT |
| 看跌研究员 | 研究经理 | BEAR_ARGUMENT |
| 研究经理 | 交易员 | RESEARCH_RECOMMENDATION |
| 交易员 | 投资组合经理 | TRADING_PLAN |
| 投资组合经理 | 系统 | PORTFOLIO_DECISION |

## 并行执行优化

Phase 1 使用 `asyncio.gather()` 并行执行：

```python
async def run_phase_1():
    tasks = [
        technical_analyst.analyze(market_data),
        fundamental_analyst.analyze(market_data),
        news_analyst.analyze(market_data),
        sentiment_analyst.analyze(market_data)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Agent failed: {result}")
        else:
            yield result
```

## 辩论机制

### 辩论流程

```
Round 1:
  Bull: "技术面强势上涨，建议做多"
  Bear: "但RSI接近超买，需警惕回调"
  
Round 2:
  Bull: "超买可以持续，趋势未变"
  Bear: "资金费率很高，多头成本大"
  
Round 3:
  Bull: "但多头情绪占优，资金流入"
  Bear: "同意，但建议控制仓位"
  
Research Manager: "综合评估，LONG，置信度70%"
```

### 论点提取

```python
from vibe_trading.researchers.debate_analyzer import ArgumentExtractor

extractor = ArgumentExtractor()

# 从Agent响应中提取论点
arguments = extractor.extract_arguments(
    agent_response=response,
    agent_role="bull_researcher"
)

# 论点结构
{
    "argument": "技术面强势上涨",
    "category": ArgumentCategory.TECHNICAL,
    "strength": ArgumentStrength.STRONG,
    "evidence": ["RSI=65", "突破阻力位"]
}
```

### 辩论质量评估

```python
from vibe_trading.researchers.debate_analyzer import DebateEvaluator

evaluator = DebateEvaluator()

# 评估辩论质量
scorecard = evaluator.evaluate_debate(
    bull_arguments=bull_args,
    bear_arguments=bear_args,
    decision=recommendation
)

# 评分项
{
    "evidence_quality": 0.8,
    "logical_consistency": 0.75,
    "rebuttal_quality": 0.7,
    "overall_score": 0.75
}
```

## 决策聚合

### 研究经理决策

```python
from vibe_trading.researchers.debate_analyzer import RecommendationEngine

engine = RecommendationEngine()

# 生成投资建议
recommendation = engine.generate_recommendation(
    bull_arguments=bull_args,
    bear_arguments=bear_args,
    debate_scorecard=scorecard
)

# 输出
InvestmentRecommendation(
    direction=InvestmentDirection.LONG,
    confidence=0.75,
    reasoning="技术面和基本面支持上涨，...",
    risk_factors=["RSI超买", "资金费率高"],
    suggested_position_size=0.20
)
```

### 投资组合经理决策

```python
from vibe_trading.decision.decision_agents import DecisionFramework

framework = DecisionFramework()

# 综合评估
decision = framework.make_decision(
    analyst_reports=reports,
    investment_plan=recommendation,
    trading_plan=plan,
    risk_debate=risk_debate
)

# 决策因子权重
weights = {
    "technical": 0.25,
    "fundamental": 0.25,
    "sentiment": 0.20,
    "risk_compliance": 0.20,
    "historical_performance": 0.10
}

# 最终决策
final_decision = Decision(
    action=TradingAction.BUY,
    quantity=0.2,
    reason="综合评估支持做多...",
    confidence=0.78
)
```

## 错误处理

### Agent 失败处理

```python
# 并行执行时捕获异常
results = await asyncio.gather(*tasks, return_exceptions=True)

for i, result in enumerate(results):
    if isinstance(result, Exception):
        logger.error(f"{agent_names[i]} failed: {result}")
        # 使用默认值或跳过
        results[i] = None
```

### 阶段降级

如果某个阶段失败：

```python
try:
    phase1_results = await run_phase_1()
except Exception as e:
    logger.error(f"Phase 1 failed: {e}")
    # 使用默认值继续
    phase1_results = get_default_phase1_results()

# 继续执行Phase 2
phase2_results = await run_phase_2(phase1_results)
```

### 超时处理

```python
# 设置超时
try:
    result = await asyncio.wait_for(
        agent.analyze(data),
        timeout=30.0  # 30秒超时
    )
except asyncio.TimeoutError:
    logger.warning(f"{agent.name} timeout, using cached result")
    result = await cache.get(agent.name)
```
