"""
Agent 类

对应 TypeScript 版本的 agent.ts。
提供有状态的高层 Agent 封装，管理整个 Agent 生命周期。
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Union,
)

from pi_ai import (
    Model,
    get_model,
    stream_simple,
    AssistantMessage,
    ImageContent,
    Message,
    TextContent,
    ThinkingContent,
    ThinkingLevel,
    ToolCall,
    UserMessage,
)
from .agent_loop import agent_loop, agent_loop_continue
from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentState,
    AgentTool,
    AgentToolResult,
    StreamFn,
)


@dataclass
class AgentOptions:
    """
    Agent 构造选项。

    Attributes:
        initial_state: 初始状态（部分）
        convert_to_llm: 转换 AgentMessage 到 LLM Message
        transform_context: 上下文转换（裁剪/注入）
        steering_mode: Steering 消息模式
        follow_up_mode: Follow-up 消息模式
        stream_fn: 自定义流式函数
        session_id: 会话 ID
        get_api_key: 动态 API Key 获取
        thinking_budgets: 思考预算
        # Credit tracking 配置
        enable_credit_tracking: 是否启用 credit 计费追踪
        user_id: 用户 ID（用于计费）
        project_id: 项目 ID（用于计费）
        agent_role: Agent 角色（用于计费）
        model_config_name: 模型配置名称（用于计费，如 "glm_4_7"）
    """

    initial_state: Optional[Dict[str, Any]] = None
    convert_to_llm: Optional[
        Callable[[List[AgentMessage]], Union[List[Message], Awaitable[List[Message]]]]
    ] = None
    transform_context: Optional[
        Callable[[List[AgentMessage], Optional[Any]], Awaitable[List[AgentMessage]]]
    ] = None
    steering_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    follow_up_mode: Literal["all", "one-at-a-time"] = "one-at-a-time"
    stream_fn: Optional[StreamFn] = None
    session_id: Optional[str] = None
    get_api_key: Optional[
        Callable[[str], Union[Optional[str], Awaitable[Optional[str]]]]
    ] = None
    thinking_budgets: Optional[Dict[str, int]] = None
    max_retry_delay_ms: Optional[int] = None
    # Credit tracking
    enable_credit_tracking: bool = False
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    agent_role: Optional[str] = None
    model_config_name: Optional[str] = None


def _default_convert_to_llm(messages: List[AgentMessage]) -> List[Message]:
    """
    默认的 convertToLlm: 只保留 LLM 兼容的消息。

    过滤掉自定义消息类型，只保留 user/assistant/toolResult。
    """
    return [
        m
        for m in messages
        if getattr(m, "role", None) in ("user", "assistant", "toolResult")
    ]


class Agent:
    """
    有状态的 Agent 类。

    管理 Agent 生命周期，提供以下核心能力:
    - 状态管理 (system prompt, model, tools, messages)
    - 事件订阅和发布
    - Prompt 发送和流式处理
    - Steering/Follow-up 消息队列
    - 取消和重置

    对应 TypeScript 版本的 Agent 类。

    Usage:
        agent = Agent(AgentOptions(
            initial_state={"system_prompt": "你是一个助手", "model": get_model("openai", "gpt-4o")},
        ))

        agent.subscribe(lambda event: print(event.type))
        await agent.prompt("你好！")
    """

    def __init__(self, opts: Optional[AgentOptions] = None):
        if opts is None:
            opts = AgentOptions()

        # 初始化状态
        self._state = AgentState()
        if opts.initial_state:
            for key, value in opts.initial_state.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

        # 配置
        self._convert_to_llm = opts.convert_to_llm or _default_convert_to_llm
        self._transform_context = opts.transform_context
        self._steering_mode = opts.steering_mode
        self._follow_up_mode = opts.follow_up_mode
        self._stream_fn: StreamFn = opts.stream_fn or stream_simple
        self._session_id = opts.session_id
        self._get_api_key = opts.get_api_key
        self._thinking_budgets = opts.thinking_budgets
        self._max_retry_delay_ms = opts.max_retry_delay_ms
        # Credit tracking
        self._enable_credit_tracking = opts.enable_credit_tracking
        self._user_id = opts.user_id
        self._project_id = opts.project_id
        self._agent_role = opts.agent_role
        self._model_config_name = opts.model_config_name
        # Model routing (from initial_state)
        self._model_router = getattr(self._state, 'model_router', None)

        # 事件监听器
        self._listeners: Set[Callable[[AgentEvent], None]] = set()

        # 取消控制
        self._cancel_event: Optional[asyncio.Event] = None

        # 消息队列
        self._steering_queue: List[AgentMessage] = []
        self._follow_up_queue: List[AgentMessage] = []

        # 运行状态
        self._running_prompt: Optional[asyncio.Future] = None
        self._resolve_running_prompt: Optional[Callable] = None

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def state(self) -> AgentState:
        """获取当前状态"""
        return self._state

    @property
    def session_id(self) -> Optional[str]:
        """获取会话 ID"""
        return self._session_id

    @session_id.setter
    def session_id(self, value: Optional[str]):
        """设置会话 ID"""
        self._session_id = value

    @property
    def thinking_budgets(self) -> Optional[Dict[str, int]]:
        """获取思考预算"""
        return self._thinking_budgets

    @thinking_budgets.setter
    def thinking_budgets(self, value: Optional[Dict[str, int]]):
        """设置思考预算"""
        self._thinking_budgets = value

    @property
    def stream_fn(self) -> StreamFn:
        """获取流式函数"""
        return self._stream_fn

    @stream_fn.setter
    def stream_fn(self, value: StreamFn):
        """设置流式函数"""
        self._stream_fn = value

    # =========================================================================
    # 事件订阅
    # =========================================================================

    def subscribe(self, fn: Callable[[AgentEvent], None]) -> Callable[[], None]:
        """
        订阅 Agent 事件。

        Args:
            fn: 事件处理函数

        Returns:
            取消订阅的函数
        """
        self._listeners.add(fn)

        def unsubscribe():
            self._listeners.discard(fn)

        return unsubscribe

    def _emit(self, event: AgentEvent) -> None:
        """发送事件给所有监听器"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass  # 不让监听器错误影响 Agent

    # =========================================================================
    # 状态操作
    # =========================================================================

    def set_system_prompt(self, prompt: str) -> None:
        """设置系统提示词"""
        self._state.system_prompt = prompt

    def set_model(self, model: Model) -> None:
        """设置 LLM 模型"""
        self._state.model = model

    def set_thinking_level(self, level: ThinkingLevel) -> None:
        """设置思考级别"""
        self._state.thinking_level = level

    def set_tools(self, tools: List[AgentTool]) -> None:
        """设置可用工具"""
        self._state.tools = tools

    def replace_messages(self, messages: List[AgentMessage]) -> None:
        """替换全部消息历史"""
        self._state.messages = list(messages)

    def append_message(self, message: AgentMessage) -> None:
        """追加一条消息"""
        self._state.messages = [*self._state.messages, message]

    def clear_messages(self) -> None:
        """清空消息历史"""
        self._state.messages = []

    # =========================================================================
    # Steering / Follow-up 消息
    # =========================================================================

    def set_steering_mode(self, mode: Literal["all", "one-at-a-time"]) -> None:
        """设置 steering 模式"""
        self._steering_mode = mode

    def get_steering_mode(self) -> str:
        """获取 steering 模式"""
        return self._steering_mode

    def set_follow_up_mode(self, mode: Literal["all", "one-at-a-time"]) -> None:
        """设置 follow-up 模式"""
        self._follow_up_mode = mode

    def get_follow_up_mode(self) -> str:
        """获取 follow-up 模式"""
        return self._follow_up_mode

    def steer(self, message: AgentMessage) -> None:
        """
        排队一条 steering 消息来中断 Agent 运行。

        在当前工具执行完成后交付，跳过剩余工具。
        """
        self._steering_queue.append(message)

    def follow_up(self, message: AgentMessage) -> None:
        """
        排队一条 follow-up 消息，在 Agent 完成后处理。

        仅当 Agent 没有更多工具调用或 steering 消息时交付。
        """
        self._follow_up_queue.append(message)

    def clear_steering_queue(self) -> None:
        """清空 steering 队列"""
        self._steering_queue = []

    def clear_follow_up_queue(self) -> None:
        """清空 follow-up 队列"""
        self._follow_up_queue = []

    def clear_all_queues(self) -> None:
        """清空所有队列"""
        self._steering_queue = []
        self._follow_up_queue = []

    def has_queued_messages(self) -> bool:
        """是否有排队的消息"""
        return len(self._steering_queue) > 0 or len(self._follow_up_queue) > 0

    def _dequeue_steering_messages(self) -> List[AgentMessage]:
        """出队 steering 消息"""
        if self._steering_mode == "one-at-a-time":
            if self._steering_queue:
                first = self._steering_queue[0]
                self._steering_queue = self._steering_queue[1:]
                return [first]
            return []
        else:
            steering = list(self._steering_queue)
            self._steering_queue = []
            return steering

    def _dequeue_follow_up_messages(self) -> List[AgentMessage]:
        """出队 follow-up 消息"""
        if self._follow_up_mode == "one-at-a-time":
            if self._follow_up_queue:
                first = self._follow_up_queue[0]
                self._follow_up_queue = self._follow_up_queue[1:]
                return [first]
            return []
        else:
            follow_up = list(self._follow_up_queue)
            self._follow_up_queue = []
            return follow_up

    # =========================================================================
    # 控制
    # =========================================================================

    def abort(self) -> None:
        """取消当前操作"""
        if self._cancel_event:
            self._cancel_event.set()

    async def wait_for_idle(self) -> None:
        """等待 Agent 完成当前操作"""
        if self._running_prompt:
            await self._running_prompt

    def reset(self) -> None:
        """重置 Agent 状态"""
        self._state.messages = []
        self._state.is_streaming = False
        self._state.stream_message = None
        self._state.pending_tool_calls = set()
        self._state.error = None
        self._steering_queue = []
        self._follow_up_queue = []

    # =========================================================================
    # Prompt
    # =========================================================================

    async def prompt(
        self,
        input_data: Union[str, AgentMessage, List[AgentMessage]],
        images: Optional[List[ImageContent]] = None,
    ) -> None:
        """
        发送 prompt 给 Agent。

        支持三种输入形式:
        1. 文本字符串（可附带图片）
        2. 单个 AgentMessage
        3. AgentMessage 列表

        Args:
            input_data: 输入数据
            images: 可选的图片列表

        Raises:
            RuntimeError: Agent 正在处理另一个 prompt
        """
        if self._state.is_streaming:
            raise RuntimeError(
                "Agent is already processing a prompt. "
                "Use steer() or follow_up() to queue messages, "
                "or wait for completion."
            )

        model = self._state.model
        if not model:
            raise RuntimeError("No model configured")

        # 构建消息
        msgs: List[AgentMessage]
        if isinstance(input_data, list):
            msgs = input_data
        elif isinstance(input_data, str):
            from .types import UserMessage

            content = [TextContent(text=input_data)]
            if images:
                content.extend(images)
            msgs = [UserMessage(content=content)]
        else:
            msgs = [input_data]

        await self._run_loop(msgs)

    async def continue_(self) -> None:
        """
        从当前上下文继续（用于重试和恢复排队消息）。

        Raises:
            RuntimeError: Agent 正在处理或无法继续
        """
        if self._state.is_streaming:
            raise RuntimeError(
                "Agent is already processing. Wait for completion before continuing."
            )

        messages = self._state.messages
        if not messages:
            raise RuntimeError("No messages to continue from")

        last_msg = messages[-1]
        if getattr(last_msg, "role", None) == "assistant":
            # 尝试从队列中获取消息
            queued_steering = self._dequeue_steering_messages()
            if queued_steering:
                await self._run_loop(
                    queued_steering, skip_initial_steering_poll=True
                )
                return

            queued_follow_up = self._dequeue_follow_up_messages()
            if queued_follow_up:
                await self._run_loop(queued_follow_up)
                return

            raise RuntimeError("Cannot continue from message role: assistant")

        await self._run_loop(None)

    # =========================================================================
    # 内部循环
    # =========================================================================

    async def _run_loop(
        self,
        messages: Optional[List[AgentMessage]],
        skip_initial_steering_poll: bool = False,
    ) -> None:
        """运行 Agent 循环"""
        model = self._state.model
        if not model:
            raise RuntimeError("No model configured")

        # 创建运行 Promise
        loop = asyncio.get_event_loop()
        self._running_prompt = loop.create_future()

        # 创建取消事件
        self._cancel_event = asyncio.Event()
        self._state.is_streaming = True
        self._state.stream_message = None
        self._state.error = None

        reasoning = (
            None
            if self._state.thinking_level == ThinkingLevel.OFF
            else self._state.thinking_level.value
        )

        context = AgentContext(
            system_prompt=self._state.system_prompt,
            messages=list(self._state.messages),
            tools=self._state.tools,
        )

        _skip_initial = skip_initial_steering_poll

        config = AgentLoopConfig(
            model=model,
            reasoning=reasoning,
            session_id=self._session_id,
            max_retry_delay_ms=self._max_retry_delay_ms,
            convert_to_llm=self._convert_to_llm,
            transform_context=self._transform_context,
            get_api_key=self._get_api_key,
            get_steering_messages=self._make_steering_callback(_skip_initial),
            get_follow_up_messages=self._make_follow_up_callback(),
            # Credit tracking
            enable_credit_tracking=self._enable_credit_tracking,
            user_id=self._user_id,
            project_id=self._project_id,
            agent_role=self._agent_role,
            model_config_name=self._model_config_name,
            # Model routing
            model_router=self._model_router,
        )

        partial: Optional[AgentMessage] = None

        try:
            if messages is not None:
                event_stream = agent_loop(
                    messages, context, config, self._cancel_event, self._stream_fn
                )
            else:
                event_stream = agent_loop_continue(
                    context, config, self._cancel_event, self._stream_fn
                )

            async for event in event_stream:
                # 根据事件更新内部状态
                if event.type == "message_start":
                    partial = event.message
                    self._state.stream_message = event.message

                elif event.type == "message_update":
                    partial = event.message
                    self._state.stream_message = event.message

                elif event.type == "message_end":
                    partial = None
                    self._state.stream_message = None
                    self.append_message(event.message)

                elif event.type == "tool_execution_start":
                    self._state.pending_tool_calls = (
                        self._state.pending_tool_calls | {event.tool_call_id}
                    )

                elif event.type == "tool_execution_end":
                    self._state.pending_tool_calls = (
                        self._state.pending_tool_calls - {event.tool_call_id}
                    )

                elif event.type == "turn_end":
                    if (
                        event.message
                        and getattr(event.message, "role", None) == "assistant"
                        and getattr(event.message, "error_message", None)
                    ):
                        self._state.error = event.message.error_message

                elif event.type == "agent_end":
                    self._state.is_streaming = False
                    self._state.stream_message = None

                # 发送事件给监听器
                self._emit(event)

            # 处理剩余的 partial 消息
            if (
                partial
                and getattr(partial, "role", None) == "assistant"
                and getattr(partial, "content", None)
            ):
                has_content = any(
                    (isinstance(c, ThinkingContent) and c.thinking.strip())
                    or (isinstance(c, TextContent) and c.text.strip())
                    or (isinstance(c, ToolCall) and c.name.strip())
                    for c in partial.content
                )
                if has_content:
                    self.append_message(partial)
                else:
                    if self._cancel_event and self._cancel_event.is_set():
                        raise RuntimeError("Request was aborted")

        except Exception as err:
            error_msg = AssistantMessage(
                content=[TextContent(text="")],
                api=model.api if hasattr(model, "api") else "",
                provider=model.provider,
                model=model.id,
                usage={
                    "input": 0,
                    "output": 0,
                    "cache_read": 0,
                    "cache_write": 0,
                    "total_tokens": 0,
                    "cost": {"input": 0, "output": 0, "total": 0},
                },
                stop_reason=(
                    "aborted"
                    if self._cancel_event and self._cancel_event.is_set()
                    else "error"
                ),
                error_message=str(err),
            )

            self.append_message(error_msg)
            self._state.error = str(err)
            self._emit(AgentEndEvent(messages=[error_msg]))

        finally:
            self._state.is_streaming = False
            self._state.stream_message = None
            self._state.pending_tool_calls = set()
            self._cancel_event = None
            if self._running_prompt and not self._running_prompt.done():
                self._running_prompt.set_result(None)
            self._running_prompt = None

    def _make_steering_callback(
        self, skip_initial: bool
    ) -> Callable[[], Awaitable[List[AgentMessage]]]:
        """创建 steering 消息的回调"""
        skipped = [skip_initial]  # 用列表包装实现闭包可变

        async def callback() -> List[AgentMessage]:
            if skipped[0]:
                skipped[0] = False
                return []
            return self._dequeue_steering_messages()

        return callback

    def _make_follow_up_callback(
        self,
    ) -> Callable[[], Awaitable[List[AgentMessage]]]:
        """创建 follow-up 消息的回调"""

        async def callback() -> List[AgentMessage]:
            return self._dequeue_follow_up_messages()

        return callback
