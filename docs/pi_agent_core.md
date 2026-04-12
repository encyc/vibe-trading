# pi_agent_core 框架详解

> 基于 badlogic/pi-mono 的 @mariozechner/pi-agent-core 包进行的 Python 复刻
>
> 原始项目: https://github.com/badlogic/pi-mono

## 目录

- [概述](#概述)
- [核心架构](#核心架构)
- [类型系统](#类型系统)
- [Agent 类详解](#agent-类详解)
- [Agent Loop 引擎](#agent-loop-引擎)
- [工具系统](#工具系统)
- [Context 封装问题](#context-封装问题)
- [最佳实践](#最佳实践)

---

## 概述

`pi_agent_core` 是一个轻量级、事件驱动的 AI Agent 框架，提供：

- **有状态的 Agent 管理** - 完整的 Agent 生命周期控制
- **双层循环引擎** - 内层处理消息，外层管理对话轮次
- **事件流架构** - 基于事件的异步通信
- **工具执行** - 可扩展的函数调用系统
- **Skill 管理** - 基于文件系统的技能加载

### 核心设计理念

```
┌─────────────────────────────────────────────────────┐
│                     Agent                           │
│  (有状态，管理生命周期、事件订阅、状态持久化)         │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                   agent_loop()                       │
│  (无状态，纯函数式，处理消息流和工具调用)             │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                    LLM API                           │
│  (通过 Model Router 抽象，支持多模型)                 │
└─────────────────────────────────────────────────────┘
```

---

## 核心架构

### 文件结构

```
pi_agent_core/
├── __init__.py       # 包导出
├── agent.py          # Agent 类 (有状态 API)
├── agent_loop.py     # agent_loop() 函数 (无状态引擎)
├── types.py          # 核心类型定义
├── skills.py         # Skill 管理系统
└── proxy.py          # 代理相关 (未完成)
```

### 模块依赖关系

```
pi_agent_core
    │
    ├── pi_ai (LLM 抽象层)
    │   ├── Model (模型接口)
    │   ├── stream_simple (流式调用)
    │   └── ModelRouter (模型路由)
    │
    └── pydantic (参数验证)
```

---

## 类型系统

### AgentState - Agent 状态

```python
@dataclass
class AgentState:
    system_prompt: str           # 系统提示词
    model: Model                 # LLM 模型
    thinking_level: ThinkingLevel # 思考级别
    tools: List[AgentTool]       # 可用工具
    messages: List[AgentMessage] # 消息历史
    is_streaming: bool           # 是否正在流式处理
    stream_message: Optional[AgentMessage] # 当前流式消息
    pending_tool_calls: Set[str] # 待执行的工具调用
    error: Optional[str]         # 错误信息
    model_router: Optional[ModelRouter] # 模型路由器
```

### AgentContext - 循环上下文

```python
@dataclass
class AgentContext:
    system_prompt: str                    # 系统提示词
    messages: List[AgentMessage]          # 消息历史
    tools: Optional[List[AgentTool]]      # 可用工具
```

**重要**: `AgentContext` 是传递给 `agent_loop()` 的**不可变上下文**，每次调用都会创建新实例。

### AgentMessage - 消息类型

```python
# 标准 LLM 消息
AgentMessage = Union[
    UserMessage,       # 用户消息
    AssistantMessage,  # 助手消息
    ToolResultMessage, # 工具结果消息
]

# 自定义消息
class CustomMessage:
    timestamp: float
    role: str = "custom"
    # ... 自定义字段
```

### AgentEvent - 事件类型

```python
AgentEvent = Union[
    AgentStartEvent,           # Agent 生命周期开始
    AgentEndEvent,             # Agent 生命周期结束
    TurnStartEvent,            # 对话轮次开始
    TurnEndEvent,              # 对话轮次结束
    MessageStartEvent,         # 消息开始
    MessageUpdateEvent,        # 消息流式更新
    MessageEndEvent,           # 消息完成
    ToolExecutionStartEvent,   # 工具开始执行
    ToolExecutionUpdateEvent,  # 工具流式进度
    ToolExecutionEndEvent,     # 工具执行完成
]
```

---

## Agent 类详解

### 初始化

```python
from pi_agent_core import Agent, AgentOptions
from pi_ai import get_model

agent = Agent(AgentOptions(
    initial_state={
        "system_prompt": "你是一个交易助手",
        "model": get_model("anthropic", "claude-sonnet-4-20250514"),
        "thinking_level": ThinkingLevel.MEDIUM,
    },
    session_id="trading-session-001",
))
```

### 核心方法

#### 1. prompt() - 发送消息

```python
# 文本输入
await agent.prompt("分析 BTC 的当前趋势")

# 带图片
await agent.prompt(
    "这张图表显示了什么？",
    images=[ImageContent(url="https://example.com/chart.png")]
)

# 多条消息
await agent.prompt([
    UserMessage(content=[TextContent(text="第一句")]),
    UserMessage(content=[TextContent(text="第二句")]),
])
```

#### 2. steer() - 中断控制

```python
# 在工具执行完成后立即中断
agent.steak(UserMessage(content=[TextContent(text="取消当前操作")]))

# 模式：one-at-a-time (默认) 或 all
agent.set_steering_mode("one-at-a-time")
```

#### 3. follow_up() - 后续消息

```python
# 在 Agent 完成后处理
agent.follow_up(UserMessage(content=[TextContent(text="继续分析")]))
```

#### 4. 事件订阅

```python
def handle_event(event: AgentEvent):
    print(f"Event: {event.type}")

unsubscribe = agent.subscribe(handle_event)
# ...
unsubscribe()  # 取消订阅
```

#### 5. 状态管理

```python
# 设置系统提示词
agent.set_system_prompt("新的系统提示")

# 设置模型
agent.set_model(get_model("openai", "gpt-4o"))

# 设置工具
agent.set_tools([tool1, tool2])

# 操作消息历史
agent.append_message(message)
agent.replace_messages(new_messages)
agent.clear_messages()
```

#### 6. 控制

```python
# 取消当前操作
agent.abort()

# 等待完成
await agent.wait_for_idle()

# 重置状态
agent.reset()
```

---

## Agent Loop 引擎

### 双层循环架构

```
┌─────────────────────────────────────────────┐
│            Outer Loop (Turn Loop)           │
│  管理对话轮次，处理 steering/follow-up 消息   │
└─────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│           Inner Loop (Message Loop)          │
│  处理消息流、LLM 调用、工具执行              │
└─────────────────────────────────────────────┘
```

### agent_loop() 函数

```python
def agent_loop(
    prompts: List[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    cancel_event: Optional[asyncio.Event],
    stream_fn: Optional[StreamFn],
) -> EventStream[AgentEvent, List[AgentMessage]]:
    """
    启动 Agent 循环

    返回事件流，可以异步迭代:
        async for event in agent_loop(...):
            if event.type == "message_update":
                print(event.message)
    """
```

### AgentLoopConfig

```python
@dataclass
class AgentLoopConfig:
    model: Model                           # LLM 模型
    convert_to_llm: Callable               # 消息转换
    transform_context: Callable            # 上下文转换
    get_api_key: Callable                  # 动态 API Key
    get_steering_messages: Callable        # 获取 steering 消息
    get_follow_up_messages: Callable       # 获取 follow-up 消息
    reasoning: Optional[str]               # 思考级别
    session_id: Optional[str]              # 会话 ID
    enable_credit_tracking: bool           # 计费追踪
    model_router: Optional[ModelRouter]    # 模型路由
```

---

## 工具系统

### AgentTool 定义

```python
from pydantic import BaseModel
from pi_agent_core import AgentTool, AgentToolResult

class GetPriceInput(BaseModel):
    symbol: str

async def get_price_execution(
    tool_name: str,
    args: GetPriceInput,
    context: Any,
    update_callback: Callable,
) -> AgentToolResult:
    price = await fetch_price(args.symbol)

    # 发送进度更新
    if update_callback:
        update_callback(AgentToolResult(
            content=[TextContent(text=f"获取价格: {price}")]
        ))

    return AgentToolResult(
        content=[TextContent(text=f"当前价格: {price}")],
        details={"symbol": args.symbol, "price": price}
    )

tool = AgentTool(
    name="get_price",
    label="获取价格",
    description="获取指定交易对的当前价格",
    parameters=GetPriceInput,
    execute=get_price_execution,
)
```

### 工具执行流程

```
1. LLM 返回 tool call
   ↓
2. agent_loop 发出 ToolExecutionStartEvent
   ↓
3. 执行 tool.execute()
   ↓
4. (可选) 发出 ToolExecutionUpdateEvent (流式进度)
   ↓
5. 发出 ToolExecutionEndEvent
   ↓
6. 将结果作为 ToolResultMessage 发回 LLM
```

---

## Context 封装问题

### 问题分析

`pi_agent_core` 的 `AgentContext` **没有对业务上下文进行封装**。它只包含：

```python
@dataclass
class AgentContext:
    system_prompt: str               # LLM 系统提示词
    messages: List[AgentMessage]     # 消息历史
    tools: Optional[List[AgentTool]] # 工具列表
```

### 为什么这样设计？

这是**有意的设计选择**：

1. **关注点分离** - `AgentContext` 只关注 LLM 需要的上下文
2. **灵活性** - 业务上下文通过工具参数传递，不耦合到框架
3. **无状态性** - `agent_loop()` 是纯函数，不应依赖业务状态

### Vibe Trading 的解决方案

在 `vibe_trading` 项目中，业务上下文通过 **`ToolContext`** 封装：

```python
@dataclass
class ToolContext:
    symbol: str                      # 交易对
    interval: str                    # K线周期
    storage: KlineStorage            # 数据存储
    current_price: float             # 当前价格
    # ... 其他业务上下文

# 在工具执行时注入
async def execute_tool(
    tool_name: str,
    args: BaseModel,
    context: ToolContext,  # 业务上下文
    ...
):
    # 使用 context.symbol, context.storage 等
```

### 推荐模式

```python
# ❌ 不推荐：扩展 AgentContext
@dataclass
class MyContext(AgentContext):
    symbol: str  # 污染框架定义

# ✅ 推荐：独立的业务上下文
@dataclass
class BusinessContext:
    symbol: str
    storage: Storage
    # ...

# 通过工具参数传递
tool = AgentTool(
    name="analyze",
    execute=lambda name, args, business_context, ...: ...
)
```

---

## 最佳实践

### 1. Agent 生命周期管理

```python
async def with_agent():
    agent = Agent(AgentOptions(
        initial_state={"model": get_model(...)}
    ))

    try:
        await agent.prompt("你好")
        await agent.wait_for_idle()
    finally:
        # 清理资源
        agent.reset()
```

### 2. 并发控制

```python
# 使用锁防止并发 prompt
from asyncio import Lock

class SafeAgent:
    def __init__(self):
        self.agent = Agent(...)
        self._lock = Lock()

    async def prompt(self, text: str):
        async with self._lock:
            await self.agent.prompt(text)
```

### 3. 事件流处理

```python
async def stream_with_events():
    agent = Agent(...)

    def log_events(event: AgentEvent):
        if event.type == "tool_execution_start":
            print(f"工具 {event.tool_name} 开始执行")

    agent.subscribe(log_events)

    await agent.prompt("使用工具获取数据")
```

### 4. 错误处理

```python
try:
    await agent.prompt("...")
except RuntimeError as e:
    if "is already processing" in str(e):
        # 使用 steer() 或 follow_up() 代替
        agent.follow_up(UserMessage(...))
    else:
        raise
```

### 5. 模型路由

```python
from pi_ai.model_router import ModelRouter

router = ModelRouter()
router.register("tools", get_model("openai", "gpt-4o"))
router.register("no-tools", get_model("anthropic", "claude-haiku"))

agent = Agent(AgentOptions(
    initial_state={
        "model_router": router,
        "model": router.get_model(has_tools=True)
    }
))
```

---

## 总结

`pi_agent_core` 是一个设计精良的 Agent 框架：

| 特性 | 评价 |
|------|------|
| **架构设计** | ⭐⭐⭐⭐⭐ 分离关注点，有状态/无状态清晰 |
| **事件驱动** | ⭐⭐⭐⭐⭐ 基于事件流，易于扩展 |
| **工具系统** | ⭐⭐⭐⭐ 灵活但需要手动管理上下文 |
| **并发控制** | ⭐⭐⭐ 内置锁机制，但需要配合使用 |
| **Context 封装** | ⭐⭐⭐ 有意不封装业务上下文，保持框架纯粹 |

**关于 Context 的建议**：

1. **不要** 扩展 `AgentContext` 来包含业务字段
2. **应该** 使用独立的 `BusinessContext` 或 `ToolContext`
3. **通过** 工具参数传递业务上下文
4. **保持** `AgentContext` 只包含 LLM 相关的数据

这样设计的好处是框架保持纯粹，业务逻辑和框架完全解耦。
