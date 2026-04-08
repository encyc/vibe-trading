---
# 首页配置
layout: home

hero:
  name: VIBE TRADING
  text: AI驱动的多Agent协作量化交易系统
  tagline: 基于12个专业Agent的4阶段协作架构，结合大语言模型和智能风控，实现加密货币交易的智能化决策
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
    - theme: alt
      text: 项目简介
      link: /guide/intro
    - theme: alt
      text: GitHub
      link: https://github.com/encyc/vibe-trading

features:
  - icon: 🤖
    title: 12 Agent 协作
    details: 技术、基本面、新闻、情绪分析师 + 看涨/看跌研究员 + 风控团队 + 交易员 + 投资组合经理，4阶段协作决策
  - icon: 🎭
    title: 智能辩论系统
    details: 看涨/看跌研究员多轮辩论，论点自动提取和量化裁决，确保决策的全面性和客观性
  - icon: 🧠
    title: BM25 记忆系统
    details: 从历史交易经验中学习，持续优化策略，通过BM25算法快速检索相关决策案例
  - icon: 📊
    title: Binance 深度集成
    details: 支持永续合约交易，实时K线订阅，23个专业工具涵盖技术分析、基本面、情绪分析等领域
  - icon: 🎯
    title: Paper Trading
    details: 模拟交易模式，零风险验证策略，支持回测系统，多参数对比分析
  - icon: ⚡
    title: 智能风控
    details: VaR计算、凯利公式、波动率调整，三视角风控评估（激进/中立/保守），全面保护资金安全
---

## 项目定位

Vibe Trading 不是简单的交易机器人，而是一个**面向量化交易的专业AI决策平台**，采用多Agent协作架构，模拟真实交易团队的决策流程。

## 核心特性

### 🤖 多Agent协作架构

系统包含12个专业Agent，按照4阶段协作流程工作：

**Phase 1 - 分析师团队**
- 技术分析师：趋势识别、指标分析、支撑阻力位
- 基本面分析师：资金费率、多空比、持仓量分析
- 新闻分析师：货币政策、监管公告、重大事件
- 情绪分析师：恐惧贪婪指数、新闻情绪、社交媒体

**Phase 2 - 研究员团队**
- 看涨研究员：从乐观视角论证投资机会
- 看跌研究员：从风险视角论证潜在风险
- 研究经理：综合辩论，做出投资建议

**Phase 3 - 风控团队**
- 激进风控：高收益高风险视角的风险评估
- 中立风控：平衡风险收益视角的风险评估
- 保守风控：保护本金优先视角的风险评估

**Phase 4 - 决策层**
- 交易员：制定交易执行计划
- 投资组合经理：最终决策审批

### 🧵 多线程架构

- **宏观线程**：每小时分析大环境（趋势、情绪、重大事件）
- **On Bar 线程**：K线触发的3阶段决策流程
- **事件驱动线程**：实时监控紧急事件，秒级响应

### 🎯 实时监控

提供量子指挥塔风格的Web监控界面，支持：
- 实时K线图表
- Agent决策过程可视化
- 可拖拽、可调整大小的仪表板
- 决策历史和统计

## 你可以用它完成这些事情

- **构建面向业务的量化交易系统**：基于多Agent协作的智能决策流程
- **零风险验证策略**：使用Paper Trading模式测试策略
- **深度分析市场**：23个专业工具涵盖技术、基本面、情绪分析
- **实时监控决策**：Web界面实时展示决策过程和结果
- **历史回测分析**：支持多种LLM模式（模拟/缓存/真实）的回测系统
- **持续学习优化**：基于BM25的记忆系统，从历史经验中学习

## 技术栈

- **后端**：Python 3.13+、FastAPI、Asyncio
- **AI/ML**：LangChain、大语言模型、BM25向量检索
- **数据源**：Binance API、实时K线订阅
- **前端**：Vue.js、GridStack.js、ECharts
- **部署**：Docker、GitHub Pages

## 路线图

- [x] 12 Agent 协作架构
- [x] 4阶段决策流程
- [x] BM25 记忆系统
- [x] Paper Trading 模式
- [x] 回测系统
- [x] Web 实时监控
- [ ] 更多交易所支持
- [ ] 更多技术指标
- [ ] 策略市场
- [ ] 社区分享

## 贡献指南

欢迎贡献代码、报告问题或提出建议！请查看 [GitHub仓库](https://github.com/encyc/vibe-trading) 了解详情。

## 许可证

本项目采用 [MIT 许可证](https://github.com/encyc/vibe-trading/blob/main/LICENSE) 发布。