# 12 Agent 详细分析

Vibe Trading 系统包含 12 个专业 Agent，按照 4 阶段协作架构组织。

## Phase 1: 分析师团队

### 1. 技术分析师 (TechnicalAnalystAgent)

**职责**: 技术分析，识别趋势和信号

**工具** (9个):
- `get_technical_indicators`: 获取技术指标 (RSI, MACD, 布林带等)
- `detect_trend`: 检测趋势方向
- `detect_divergence`: 检测指标背离
- `find_support_resistance`: 查找支撑阻力位
- `detect_chart_pattern`: 检测K线形态
- `analyze_volume`: 成交量分析
- `calculate_pivot_points`: 计算枢轴点
- `get_atr`: 获取ATR波动率
- `get_bollinger_bands`: 获取布林带

**输出**: 技术分析报告，包含趋势方向、关键信号、支撑阻力位

---

### 2. 基本面分析师 (FundamentalAnalystAgent)

**职责**: 基本面分析，评估项目价值

**工具** (5个):
- `get_funding_rate`: 获取资金费率
- `get_long_short_ratio`: 获取多空比
- `get_open_interest`: 获取持仓量
- `get_taker_buy_sell_volume`: 获取买卖比例
- `get_whale_long_short_ratio`: 获取大户多空比

**输出**: 基本面分析报告，包含资金流向、市场情绪

---

### 3. 新闻分析师 (NewsAnalystAgent)

**职责**: 新闻分析，跟踪宏观事件

**关注**:
- 货币政策变化
- 监管公告
- 重大交易所动态
- 宏观经济事件

**输出**: 新闻分析报告，包含潜在影响因素

---

### 4. 情绪分析师 (SentimentAnalystAgent)

**职责**: 情绪分析，评估市场情绪

**工具** (3个):
- `get_fear_greed_index`: 恐惧贪婪指数
- `get_news_sentiment`: 新闻情绪
- `get_social_sentiment`: 社交媒体情绪

**输出**: 情绪分析报告，包含市场情绪状态

## Phase 2: 研究员团队

### 5. 看涨研究员 (BullResearcherAgent)

**职责**: 从乐观视角论证投资机会

**工作方式**:
- 与看跌研究员进行多轮辩论
- 提取论点并量化
- 使用 ArgumentExtractor 工具

**输出**: 看涨论点列表，包含论点强度

---

### 6. 看跌研究员 (BearResearcherAgent)

**职责**: 从风险视角论证潜在风险

**工作方式**:
- 与看涨研究员进行多轮辩论
- 指出潜在风险点
- 使用 ArgumentExtractor 工具

**输出**: 看跌论点列表，包含风险强度

---

### 7. 研究经理 (ResearchManagerAgent)

**职责**: 综合研究员辩论，做出投资建议

**工作方式**:
- 分析双方论点
- 使用 DebateEvaluator 评估辩论质量
- 使用 RecommendationEngine 生成投资建议
- 输出 InvestmentRecommendation (投资建议/方向/置信度)

**输出**: 投资建议，包含:
- 投资方向 (LONG/SHORT/HOLD)
- 置信度
- 理由说明

## Phase 3: 风控团队

### 8. 激进风控分析师 (AggressiveRiskAnalystAgent)

**职责**: 高收益高风险视角的风险评估

**关注**:
- 最大收益潜力
- 可接受的最大风险
- 激进的仓位建议

**输出**: 风险评估报告，包含:
- 建议仓位比例 (5-30%)
- 止损百分比
- 止盈百分比
- 风险收益比评估

---

### 9. 中立风控分析师 (NeutralRiskAnalystAgent)

**职责**: 平衡风险收益视角的风险评估

**关注**:
- 风险收益平衡
- 适中的仓位建议
- 波动率调整

**输出**: 风险评估报告，包含:
- 建议仓位比例
- 止损止盈建议
- 风险收益比评估

---

### 10. 保守风控分析师 (ConservativeRiskAnalystAgent)

**职责**: 保护本金优先视角的风险评估

**关注**:
- 本金安全
- 严格的止损
- 小仓位试探

**输出**: 风险评估报告，包含:
- 建议仓位比例 (5-10%)
- 严格的止损百分比
- 保守的止盈目标

## Phase 4: 决策层

### 11. 交易员 (TraderAgent)

**职责**: 制定交易执行计划

**输入**:
- 投资方向 (LONG/SHORT)
- 投资建议
- 风险评估报告
- 当前价格
- 账户余额

**工具**:
- `PositionSizeCalculator`: 计算仓位大小
- `StopLossTakeProfitCalculator`: 计算止损止盈
- `ExecutionStrategyCalculator`: 计算执行策略

**输出**: TradingPlan (交易执行计划)，包含:
- 交易方向
- 仓位大小
- 进场价格
- 止损价格
- 止盈价格
- 执行策略 (市价/限价/分批)

---

### 12. 投资组合经理 (PortfolioManagerAgent)

**职责**: 最终决策审批

**输入**:
- 所有分析师报告
- 投资建议
- 交易计划
- 风险辩论记录

**决策框架**:
- DecisionFramework: 综合评分系统
- 决策因子权重:
  - 技术信号权重
  - 基本面权重
  - 情绪指标权重
  - 风险合规性
  - 历史表现

**输出**: 最终决策 (BUY/SELL/HOLD)，包含:
- 决策类型
- 交易数量
- 理由说明
- 置信度

## Agent 协作示例

```
新K线到达
  ↓
Phase 1: 分析师并行执行
  ├─ 技术分析师: "上升趋势，RSI=65，突破阻力位"
  ├─ 基本面分析师: "资金费率正，多头占优"
  ├─ 新闻分析师: "无重大利空"
  └─ 情绪分析师: "贪婪指数72，市场情绪积极"
  ↓
Phase 2: 研究员辩论
  ├─ 看涨研究员: "技术面和基本面都支持上涨"
  ├─ 看跌研究员: "但RSI接近超买，需警惕回调"
  └─ 研究经理: "综合评估，建议LONG，置信度75%"
  ↓
Phase 3: 风控评估
  ├─ 激进风控: "建议30%仓位，止损3%"
  ├─ 中立风控: "建议20%仓位，止损2%"
  └─ 保守风控: "建议10%仓位，止损1.5%"
  ↓
Phase 4: 决策
  ├─ 交易员: "制定计划，LONG 20%，65000入场，63500止损"
  └─ 投资组合经理: "批准执行，BUY 0.2 BTC"
```

## Agent 配置

所有Agent的配置在 `backend/src/vibe_trading/config/agent_config.py`:

```python
class AgentConfig:
    name: str
    role: AgentRole
    temperature: float  # 控制创造性
    enabled: bool = True
```

可以通过修改配置文件调整每个Agent的行为。
