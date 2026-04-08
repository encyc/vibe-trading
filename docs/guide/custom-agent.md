# 自定义 Agent

本文档介绍如何为 Vibe Trading 系统创建自定义 Agent。

## Agent 基础

### Agent 类结构

```python
from vibe_trading.agents.base_analyst import BaseAgent
from vibe_trading.agents.agent_factory import ToolContext

class CustomAgent(BaseAgent):
    """自定义 Agent 示例"""
    
    def __init__(self):
        super().__init__()
        self.name = "CustomAgent"
        self.role = "custom"
        self.temperature = 0.7
    
    async def initialize(self, context: ToolContext, **kwargs):
        """初始化 Agent"""
        self.context = context
        self.symbol = context.symbol
        self.interval = context.interval
        # 其他初始化逻辑...
    
    async def analyze(self, data: dict) -> dict:
        """分析数据并返回结果"""
        # 实现分析逻辑
        result = {
            "analysis": "分析结果",
            "confidence": 0.8,
            "recommendation": "HOLD"
        }
        return result
```

## 创建不同类型的 Agent

### 1. 分析师 Agent

分析师 Agent 负责分析特定方面的市场数据。

```python
from vibe_trading.agents.base_analyst import BaseAnalyst
from vibe_trading.tools.market_data_tools import get_current_price

class VolumeAnalystAgent(BaseAnalyst):
    """成交量分析 Agent"""
    
    def __init__(self):
        super().__init__()
        self.name = "VolumeAnalyst"
        self.description = "分析成交量变化和市场活跃度"
    
    async def analyze(self, klines: list, indicators: dict) -> dict:
        # 计算成交量指标
        current_volume = klines[-1]['volume']
        avg_volume = sum(k['volume'] for k in klines[-20:]) / 20
        volume_ratio = current_volume / avg_volume
        
        # 分析成交量趋势
        if volume_ratio > 2.0:
            trend = "放量"
            signal = "strong"
        elif volume_ratio > 1.5:
            trend = "温和放量"
            signal = "moderate"
        elif volume_ratio < 0.5:
            trend = "缩量"
            signal = "weak"
        else:
            trend = "正常"
            signal = "neutral"
        
        return {
            "volume_ratio": volume_ratio,
            "trend": trend,
            "signal": signal,
            "strength": min(volume_ratio, 3.0) / 3.0,
            "analysis": f"成交量{trend}，当前量为平均量的{volume_ratio:.1f}倍"
        }
```

### 2. 研究员 Agent

研究员 Agent 负责研究和论证投资观点。

```python
from vibe_trading.agents.researchers.researcher_agents import BaseResearcher

class CustomResearcher(BaseResearcher):
    """自定义研究员 Agent"""
    
    def __init__(self, perspective: str = "bullish"):
        super().__init__()
        self.perspective = perspective  # bullish 或 bearish
        self.name = f"{perspective.capitalize()}Researcher"
    
    async def present_case(self, analyst_reports: dict) -> dict:
        """呈现投资观点"""
        arguments = []
        
        # 根据视角提取论点
        if self.perspective == "bullish":
            if analyst_reports['technical']['trend'] == "upward":
                arguments.append({
                    "point": "技术面显示上升趋势",
                    "strength": 0.8
                })
            if analyst_reports['fundamental']['sentiment'] == "bullish":
                arguments.append({
                    "point": "基本面支持看涨",
                    "strength": 0.7
                })
        else:
            if analyst_reports['technical']['rsi'] > 70:
                arguments.append({
                    "point": "RSI超买，存在回调风险",
                    "strength": 0.6
                })
        
        return {
            "perspective": self.perspective,
            "arguments": arguments,
            "overall_confidence": calculate_confidence(arguments)
        }
```

### 3. 风控 Agent

风控 Agent 负责风险评估和控制。

```python
from vibe_trading.agents.risk_mgmt.risk_agents import BaseRiskAnalyst

class CustomRiskAnalyst(BaseRiskAnalyst):
    """自定义风控 Agent"""
    
    def __init__(self, risk_profile: str = "moderate"):
        super().__init__()
        self.risk_profile = risk_profile  # aggressive | moderate | conservative
    
    async def assess(self, recommendation: dict, market_data: dict) -> dict:
        """评估风险"""
        # 根据风险 profile 调整参数
        if self.risk_profile == "aggressive":
            position_size = 0.3
            stop_loss = 0.03
            take_profit = 0.10
        elif self.risk_profile == "moderate":
            position_size = 0.2
            stop_loss = 0.02
            take_profit = 0.08
        else:  # conservative
            position_size = 0.1
            stop_loss = 0.015
            take_profit = 0.05
        
        # 计算 VaR
        var_value = calculate_var(
            position_size,
            confidence_level=0.95
        )
        
        return {
            "profile": self.risk_profile,
            "position_size": position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "var_value": var_value,
            "risk_reward_ratio": take_profit / stop_loss
        }
```

## 创建自定义工具

### 工具基础结构

```python
from vibe_trading.tools.base_tool import BaseTool
from typing import Dict, Any

class CustomTool(BaseTool):
    """自定义工具"""
    
    def __init__(self):
        super().__init__()
        self.name = "custom_tool"
        self.description = "自定义工具描述"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        # 实现工具逻辑
        result = {
            "success": True,
            "data": "工具执行结果"
        }
        return result
```

### 示例：自定义技术指标工具

```python
class CustomIndicatorTool(BaseTool):
    """自定义技术指标工具"""
    
    def __init__(self):
        super().__init__()
        self.name = "custom_indicator"
        self.description = "计算自定义技术指标"
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        klines = params['klines']
        period = params.get('period', 14)
        
        # 计算自定义指标
        values = []
        for i in range(period - 1, len(klines)):
            # 示例：计算动量指标
            momentum = (klines[i]['close'] - klines[i - period]['close']) / klines[i - period]['close']
            values.append(momentum)
        
        return {
            "indicator": "momentum",
            "values": values,
            "current": values[-1] if values else 0
        }
```

## 注册自定义 Agent

### 在 AgentFactory 中注册

```python
from vibe_trading.agents.agent_factory import AgentFactory

# 注册自定义 Agent
AgentFactory.register(CustomAnalyst)
AgentFactory.register(CustomResearcher)
AgentFactory.register(CustomRiskAnalyst)
```

### 在配置中启用

```python
# 在 agent_config.py 中
CUSTOM_AGENTS_ENABLED = {
    "custom_analyst": True,
    "custom_researcher": True,
    "custom_risk": True
}
```

## 集成到决策流程

### 添加到 Analyst Phase

```python
from vibe_trading.coordinator.trading_coordinator import TradingCoordinator

class CustomTradingCoordinator(TradingCoordinator):
    async def run_analyst_phase(self, context):
        # 运行标准分析师
        standard_results = await super().run_analyst_phase(context)
        
        # 添加自定义分析师
        custom_analyst = CustomAnalyst()
        await custom_analyst.initialize(context)
        custom_result = await custom_analyst.analyze(context)
        
        # 合并结果
        standard_results["custom"] = custom_result
        return standard_results
```

### 添加到 Research Phase

```python
async def run_research_phase(self, analyst_reports):
    # 运行标准研究员
    standard_results = await super().run_research_phase(analyst_reports)
    
    # 添加自定义研究员
    custom_researcher = CustomResearcher(perspective="bullish")
    custom_result = await custom_researcher.present_case(analyst_reports)
    
    # 合并结果
    standard_results["custom"] = custom_result
    return standard_results
```

## 测试自定义 Agent

### 单元测试

```python
import pytest
from vibe_trading.agents.custom_agent import CustomAgent

@pytest.mark.asyncio
async def test_custom_agent():
    agent = CustomAgent()
    
    # 准备测试数据
    context = ToolContext(
        symbol="BTCUSDT",
        interval="1h"
    )
    await agent.initialize(context)
    
    # 测试分析
    result = await agent.analyze({"test": "data"})
    
    # 验证结果
    assert result is not None
    assert "analysis" in result
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1
```

### 集成测试

```python
@pytest.mark.asyncio
async def test_custom_agent_integration():
    # 创建测试协调器
    coordinator = CustomTradingCoordinator()
    await coordinator.initialize()
    
    # 运行完整流程
    decision = await coordinator.analyze_and_decide(
        current_price=65000,
        account_balance=10000
    )
    
    # 验证自定义 Agent 被调用
    assert "custom" in decision.agent_outputs
```

## 最佳实践

1. **继承基类**：始终继承合适的基类（BaseAgent、BaseAnalyst 等）
2. **实现必需方法**：确保实现所有必需的方法
3. **错误处理**：添加适当的错误处理
4. **日志记录**：使用日志记录重要操作
5. **性能优化**：避免阻塞操作，使用异步
6. **测试覆盖**：编写单元测试和集成测试

## 示例项目

查看 `examples/custom_agents/` 目录了解更多示例：

- `volume_analyst.py` - 成交量分析 Agent
- `momentum_researcher.py` - 动量研究员 Agent
- `dynamic_risk.py` - 动态风控 Agent

## 下一步

- 查看 [API文档](/guide/api) 了解可用 API
- 学习 [配置说明](/guide/configuration) 配置 Agent
- 了解 [记忆系统](/guide/memory) 集成学习功能