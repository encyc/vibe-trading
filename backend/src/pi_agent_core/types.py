"""
核心类型定义

对应原始 TypeScript 版本的 types.ts。
定义了 Agent 系统中所有的核心数据结构和类型。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Set,
    Type,
    Union,
    runtime_checkable,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from pi_ai.model_router import ModelRouter

from pydantic import BaseModel


from pi_ai.types import (
    TextContent,
    ImageContent,
    ThinkingContent,
    ToolCall,
    Content,
    ThinkingLevel,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
    Message,
)


@dataclass
class CustomMessage:
    """
    自定义消息基类。

    应用可以继承此类来创建自定义消息类型，类似于 TypeScript 版本的
    declaration merging 机制。

    示例:
        @dataclass
        class NotificationMessage(CustomMessage):
            text: str
            role: str = "notification"
    """

    timestamp: float = field(default_factory=time.time)
    role: str = "custom"


# AgentMessage = 标准 LLM 消息 + 自定义消息
AgentMessage = Union[Message, CustomMessage]


# =============================================================================
# Tool Types
# =============================================================================


@dataclass
class AgentToolResult:
    """
    工具执行结果。

    Attributes:
        content: 内容块列表（文本或图片）
        details: 供 UI 显示或日志记录的详细信息
    """

    content: List[Union[TextContent, ImageContent]]
    details: Any = None


# 工具更新回调类型
AgentToolUpdateCallback = Callable[[AgentToolResult], None]


@dataclass
class AgentTool:
    """
    Agent 工具定义。

    扩展了基础 Tool 接口，增加了 execute 函数和 label 字段。
    对应 TypeScript 版本的 AgentTool<TParameters, TDetails>。

    Attributes:
        name: 工具标识符
        label: UI 显示名称
        description: LLM 可读的工具描述
        parameters: Pydantic Model 类，用于参数验证
        execute: 异步执行函数
    """

    name: str
    label: str
    description: str
    parameters: Type[BaseModel]
    execute: Callable[
        [str, Any, Optional[Any], Optional[AgentToolUpdateCallback]],
        Awaitable[AgentToolResult],
    ]


# =============================================================================
# Agent Context
# =============================================================================


@dataclass
class AgentContext:
    """
    Agent 上下文，类似于 LLM 的 Context 但使用 AgentTool。

    Attributes:
        system_prompt: 系统提示词
        messages: 消息历史
        tools: 可用工具列表
    """

    system_prompt: str
    messages: List[AgentMessage]
    tools: Optional[List[AgentTool]] = None


# =============================================================================
# Agent State
# =============================================================================


@dataclass
class AgentState:
    """
    Agent 状态，包含所有配置和对话数据。

    Attributes:
        system_prompt: 系统提示词
        model: 当前使用的 LLM 模型
        thinking_level: 思考级别
        tools: 可用工具列表
        messages: 消息历史（可包含自定义消息类型）
        is_streaming: 是否正在流式处理
        stream_message: 流式处理中的部分消息
        pending_tool_calls: 待执行的工具调用 ID 集合
        error: 错误信息
    """

    system_prompt: str = ""
    model: Any = None  # Model 类型，在 llm.py 中定义
    thinking_level: ThinkingLevel = ThinkingLevel.OFF
    tools: List[AgentTool] = field(default_factory=list)
    messages: List[AgentMessage] = field(default_factory=list)
    is_streaming: bool = False
    stream_message: Optional[AgentMessage] = None
    pending_tool_calls: Set[str] = field(default_factory=set)
    error: Optional[str] = None
    model_router: Optional['ModelRouter'] = None


# =============================================================================
# Agent Events
# =============================================================================


@dataclass
class AgentStartEvent:
    """Agent 生命周期开始"""

    type: Literal["agent_start"] = "agent_start"


@dataclass
class AgentEndEvent:
    """Agent 生命周期结束"""

    messages: List[AgentMessage] = field(default_factory=list)
    type: Literal["agent_end"] = "agent_end"


@dataclass
class TurnStartEvent:
    """对话 Turn 开始"""

    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEndEvent:
    """对话 Turn 结束"""

    message: Optional[AgentMessage] = None
    tool_results: List[ToolResultMessage] = field(default_factory=list)
    type: Literal["turn_end"] = "turn_end"


@dataclass
class MessageStartEvent:
    """消息开始（user/assistant/toolResult）"""

    message: Optional[AgentMessage] = None
    type: Literal["message_start"] = "message_start"


@dataclass
class MessageUpdateEvent:
    """消息流式更新（仅 assistant 消息）"""

    message: Optional[AgentMessage] = None
    assistant_message_event: Any = None
    type: Literal["message_update"] = "message_update"


@dataclass
class MessageEndEvent:
    """消息完成"""

    message: Optional[AgentMessage] = None
    type: Literal["message_end"] = "message_end"


@dataclass
class ToolExecutionStartEvent:
    """工具开始执行"""

    tool_call_id: str = ""
    tool_name: str = ""
    args: Any = None
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass
class ToolExecutionUpdateEvent:
    """工具流式进度"""

    tool_call_id: str = ""
    tool_name: str = ""
    args: Any = None
    partial_result: Any = None
    type: Literal["tool_execution_update"] = "tool_execution_update"


@dataclass
class ToolExecutionEndEvent:
    """工具执行完成"""

    tool_call_id: str = ""
    tool_name: str = ""
    result: Any = None
    is_error: bool = False
    type: Literal["tool_execution_end"] = "tool_execution_end"


# Agent 事件联合类型
AgentEvent = Union[
    AgentStartEvent,
    AgentEndEvent,
    TurnStartEvent,
    TurnEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolExecutionEndEvent,
]


# =============================================================================
# Agent Loop Config
# =============================================================================


@dataclass
class AgentLoopConfig:
    """
    Agent 循环配置。

    Attributes:
        model: LLM 模型
        convert_to_llm: 将 AgentMessage[] 转换为 LLM 可理解的 Message[]
        transform_context: 可选，在 convert_to_llm 之前转换上下文
        get_api_key: 可选，动态获取 API Key
        get_steering_messages: 可选，获取中途插入的 steering 消息
        get_follow_up_messages: 可选，获取后续 follow-up 消息
        reasoning: 可选，思考级别
        api_key: 可选，静态 API Key
        session_id: 可选，会话标识
        max_retry_delay_ms: 可选，最大重试等待时间
        # Credit tracking 配置
        enable_credit_tracking: 是否启用 credit 计费追踪
        user_id: 用户 ID（用于计费）
        project_id: 项目 ID（用于计费）
        agent_role: Agent 角色（用于计费，如 "world_builder", "character" 等）
        model_config_name: 模型配置名称（用于计费，如 "glm_4_7"）
    """

    model: Any = None  # Model 类型
    convert_to_llm: Optional[
        Callable[[List[AgentMessage]], Union[List[Message], Awaitable[List[Message]]]]
    ] = None
    transform_context: Optional[
        Callable[[List[AgentMessage], Optional[Any]], Awaitable[List[AgentMessage]]]
    ] = None
    get_api_key: Optional[
        Callable[[str], Union[Optional[str], Awaitable[Optional[str]]]]
    ] = None
    get_steering_messages: Optional[
        Callable[[], Awaitable[List[AgentMessage]]]
    ] = None
    get_follow_up_messages: Optional[
        Callable[[], Awaitable[List[AgentMessage]]]
    ] = None
    reasoning: Optional[str] = None
    api_key: Optional[str] = None
    session_id: Optional[str] = None
    max_retry_delay_ms: Optional[int] = None
    # Credit tracking
    enable_credit_tracking: bool = False
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    agent_role: Optional[str] = None
    model_config_name: Optional[str] = None
    # Model routing
    model_router: Optional['ModelRouter'] = None


# =============================================================================
# Stream Function Type
# =============================================================================

# 流式函数类型：接受 model, context, options，返回异步生成器
StreamFn = Callable[..., Any]
