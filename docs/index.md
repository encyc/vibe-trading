---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "Vibe Trading"
  text: "AI驱动的多Agent协作量化交易系统"
  tagline: 基于12个专业Agent的4阶段协作架构，结合大语言模型和智能风控，实现加密货币交易的智能化决策
  image:
    src: /logo.png
    alt: Vibe Trading Logo
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
    - theme: alt
      text: 系统架构
      link: /guide/architecture
    - theme: alt
      text: GitHub
      link: https://github.com/encyc/vibe-trading

features:
  - title: 🤖 12 Agent 协作
    details: 技术、基本面、新闻、情绪分析师 + 看涨/看跌研究员 + 风控团队 + 交易员 + 投资组合经理，4阶段协作决策
  - title: 🎭 智能辩论系统
    details: 看涨/看跌研究员多轮辩论，论点自动提取和量化裁决，确保决策的全面性和客观性
  - title: 🧠 BM25 记忆系统
    details: 从历史交易经验中学习，持续优化策略，通过BM25算法快速检索相关决策案例
  - title: 📊 Binance 深度集成
    details: 支持永续合约交易，实时K线订阅，23个专业工具涵盖技术分析、基本面、情绪分析等领域
  - title: 🎯 Paper Trading
    details: 模拟交易模式，零风险验证策略，支持回测系统，多参数对比分析
  - title: ⚡ 智能风控
    details: VaR计算、凯利公式、波动率调整，三视角风控评估（激进/中立/保守），全面保护资金安全
---

## 项目定位

Vibe Trading 不是简单的交易机器人，而是一个**面向量化交易的专业AI决策平台**，采用多Agent协作架构，模拟真实交易团队的决策流程。

你可以用它完成这些事情：

- **构建面向业务的量化交易系统**：基于多Agent协作的智能决策流程
- **零风险验证策略**：使用Paper Trading模式测试策略
- **深度分析市场**：23个专业工具涵盖技术、基本面、情绪分析
- **实时监控决策**：Web界面实时展示决策过程和结果
- **历史回测分析**：支持多种LLM模式（模拟/缓存/真实）的回测系统
- **持续学习优化**：基于BM25的记忆系统，从历史经验中学习

## 文档入口

- [快速开始](/guide/quick-start)：完成环境初始化、系统启动与首次交易
- [项目简介](/guide/intro)：了解整体定位、技术栈与核心能力
- [系统架构](/guide/architecture)：查看三线程架构与Agent协作流程
- [Agent团队](/guide/agents)：了解12个专业Agent的职责和功能
- [Web监控](/guide/monitoring)：配置量子指挥塔风格的实时监控界面

## 技术栈

- **后端**：Python 3.13+、FastAPI、Asyncio
- **AI/ML**：LangChain、大语言模型、BM25向量检索
- **数据源**：Binance API、实时K线订阅
- **前端**：Vue.js、GridStack.js、ECharts
- **部署**：Docker、GitHub Pages

## 下一步

- [安装依赖](/guide/quick-start#安装步骤)：配置环境和API密钥
- [运行系统](/guide/quick-start#运行系统)：启动Paper Trading模式
- [查看文档](/)：探索完整的文档和API
