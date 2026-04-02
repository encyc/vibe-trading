"""
Agent 循环引擎

对应 TypeScript 版本的 agent-loop.ts。
实现 Agent 的双层循环消息处理引擎（无状态纯函数式设计）。

核心函数:
  - agent_loop(): 接受新 prompt，启动循环
  - agent_loop_continue(): 从现有上下文继续（重试）
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import logging
import time
from typing import Any, Dict, List, Optional

from pi_ai import (
    EventStream,
    StreamResponse,
    stream_simple,
    validate_tool_arguments,
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
)
from pi_ai.exceptions import (
    LLMStreamError,
    LLMTimeoutError,
    LLMRateLimitError,
    RetryableError,
    MaxRetriesExceededError,
)

# Credit tracking support (可选导入)
try:
    from api.billing.credit_tracker import track_llm_usage
    CREDIT_TRACKING_AVAILABLE = True
except ImportError:
    CREDIT_TRACKING_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# 重试配置
# =============================================================================

MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # 基础延迟（秒）
RETRY_DELAY_MULTIPLIER = 2.0  # 指数退避乘数


async def _retry_stream_operation(
    operation,
    operation_name: str = "stream",
    max_retries: int = MAX_RETRIES,
):
    """
    带重试的流式操作包装器。
    
    Args:
        operation: 要执行的异步操作
        operation_name: 操作名称（用于日志）
        max_retries: 最大重试次数
        
    Returns:
        操作结果
        
    Raises:
        MaxRetriesExceededError: 超过最大重试次数
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except (RuntimeError, LLMStreamError, LLMTimeoutError, asyncio.TimeoutError, LLMRateLimitError) as e:
            last_error = e
            error_msg = str(e)
            
            # 检查是否是速率限制错误 (429)
            is_rate_limit = isinstance(e, LLMRateLimitError) or "429" in error_msg or "rate" in error_msg.lower()
            
            # 检查是否是流式响应错误
            is_stream_error = "Stream did not produce a result" in error_msg or isinstance(e, LLMStreamError)
            
            if is_rate_limit or is_stream_error:
                if attempt < max_retries:
                    # 速率限制使用更长的延迟
                    if is_rate_limit:
                        delay = RETRY_DELAY_BASE * (RETRY_DELAY_MULTIPLIER ** attempt) * 2  # 双倍延迟
                        logger.warning(
                            f"{operation_name} 速率限制 (尝试 {attempt + 1}/{max_retries + 1}): "
                            f"{error_msg}, {delay:.1f}s 后重试..."
                        )
                    else:
                        delay = RETRY_DELAY_BASE * (RETRY_DELAY_MULTIPLIER ** attempt)
                        logger.warning(
                            f"{operation_name} 失败 (尝试 {attempt + 1}/{max_retries + 1}): "
                            f"{error_msg}, {delay:.1f}s 后重试..."
                        )
                    await asyncio.sleep(delay)
                    continue
            else:
                # 其他错误不重试
                raise
    
    raise MaxRetriesExceededError(max_retries, last_error)
from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentStartEvent,
    AgentTool,
    AgentToolResult,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    StreamFn,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)


def _create_agent_stream() -> EventStream[AgentEvent, List[AgentMessage]]:
    """创建 Agent 事件流"""
    return EventStream(
        is_terminal=lambda e: e.type == "agent_end",
        extract_result=lambda e: e.messages if e.type == "agent_end" else [],
    )


def agent_loop(
    prompts: List[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    cancel_event: Optional[asyncio.Event] = None,
    stream_fn: Optional[StreamFn] = None,
) -> EventStream[AgentEvent, List[AgentMessage]]:
    """
    以新 prompt 开始一个 Agent 循环。

    Prompt 添加到上下文中，并为其发出事件。

    Args:
        prompts: 用户消息列表
        context: Agent 上下文
        config: 循环配置
        cancel_event: 可选的取消事件
        stream_fn: 可选的自定义流式函数

    Returns:
        EventStream 事件流
    """
    stream = _create_agent_stream()

    async def _run():
        new_messages: List[AgentMessage] = list(prompts)
        current_context = AgentContext(
            system_prompt=context.system_prompt,
            messages=list(context.messages) + list(prompts),
            tools=context.tools,
        )

        stream.push(AgentStartEvent())
        stream.push(TurnStartEvent())

        for prompt in prompts:
            stream.push(MessageStartEvent(message=prompt))
            stream.push(MessageEndEvent(message=prompt))

        await _run_loop(
            current_context, new_messages, config, cancel_event, stream, stream_fn
        )

    asyncio.ensure_future(_run())
    return stream


def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    cancel_event: Optional[asyncio.Event] = None,
    stream_fn: Optional[StreamFn] = None,
) -> EventStream[AgentEvent, List[AgentMessage]]:
    """
    从现有上下文继续 Agent 循环（不添加新消息）。

    用于重试—— 上下文中已有 user 消息或 tool results。

    重要: 上下文中最后一条消息必须通过 convert_to_llm 转换为
    user 或 toolResult 消息。否则 LLM Provider 会拒绝请求。

    Args:
        context: Agent 上下文
        config: 循环配置
        cancel_event: 可选的取消事件
        stream_fn: 可选的自定义流式函数

    Returns:
        EventStream 事件流

    Raises:
        ValueError: 上下文为空或最后一条消息是 assistant
    """
    if not context.messages:
        raise ValueError("Cannot continue: no messages in context")

    last_msg = context.messages[-1]
    if getattr(last_msg, "role", None) == "assistant":
        raise ValueError("Cannot continue from message role: assistant")

    stream = _create_agent_stream()

    async def _run():
        new_messages: List[AgentMessage] = []
        current_context = AgentContext(
            system_prompt=context.system_prompt,
            messages=list(context.messages),
            tools=context.tools,
        )

        stream.push(AgentStartEvent())
        stream.push(TurnStartEvent())

        await _run_loop(
            current_context, new_messages, config, cancel_event, stream, stream_fn
        )

    asyncio.ensure_future(_run())
    return stream


# =============================================================================
# 内部循环逻辑
# =============================================================================


async def _run_loop(
    current_context: AgentContext,
    new_messages: List[AgentMessage],
    config: AgentLoopConfig,
    cancel_event: Optional[asyncio.Event],
    stream: EventStream[AgentEvent, List[AgentMessage]],
    stream_fn: Optional[StreamFn] = None,
) -> None:
    """
    agentLoop 和 agentLoopContinue 共享的主循环逻辑。

    实现双层循环:
    - 外层循环: 处理 follow-up 消息
    - 内层循环: 处理工具调用和 steering 消息
    """
    first_turn = True

    # 检查是否有 steering 消息（用户可能在等待期间输入了内容）
    pending_messages: List[AgentMessage] = []
    if config.get_steering_messages:
        pending_messages = await config.get_steering_messages()

    # 外层循环: 当有排队的 follow-up 消息时继续
    while True:
        has_more_tool_calls = True
        steering_after_tools: Optional[List[AgentMessage]] = None

        # 内层循环: 处理工具调用和 steering 消息
        while has_more_tool_calls or pending_messages:
            # 检查取消
            if cancel_event and cancel_event.is_set():
                stream.push(AgentEndEvent(messages=new_messages))
                stream.end(new_messages)
                return

            if not first_turn:
                stream.push(TurnStartEvent())
            else:
                first_turn = False

            # 处理待定消息（注入到下一次 assistant 响应前）
            if pending_messages:
                for message in pending_messages:
                    stream.push(MessageStartEvent(message=message))
                    stream.push(MessageEndEvent(message=message))
                    current_context.messages.append(message)
                    new_messages.append(message)
                pending_messages = []

            # 流式获取 assistant 响应
            message = await _stream_assistant_response(
                current_context, config, cancel_event, stream, stream_fn
            )
            new_messages.append(message)

            # 检查停止原因
            if message.stop_reason in ("error", "aborted"):
                stream.push(TurnEndEvent(message=message, tool_results=[]))
                stream.push(AgentEndEvent(messages=new_messages))
                stream.end(new_messages)
                return

            # 检查工具调用
            tool_calls = [c for c in message.content if isinstance(c, ToolCall)]
            has_more_tool_calls = len(tool_calls) > 0

            tool_results: List[ToolResultMessage] = []
            if has_more_tool_calls:
                tool_execution = await _execute_tool_calls(
                    current_context.tools,
                    message,
                    cancel_event,
                    stream,
                    config.get_steering_messages,
                )
                tool_results.extend(tool_execution["tool_results"])
                steering_after_tools = tool_execution.get("steering_messages")

                for result in tool_results:
                    current_context.messages.append(result)
                    new_messages.append(result)

            stream.push(TurnEndEvent(message=message, tool_results=tool_results))

            # Turn 完成后获取 steering 消息
            if steering_after_tools and len(steering_after_tools) > 0:
                pending_messages = steering_after_tools
                steering_after_tools = None
            elif config.get_steering_messages:
                pending_messages = await config.get_steering_messages()
            else:
                pending_messages = []

        # Agent 将在此停止。检查 follow-up 消息。
        if config.get_follow_up_messages:
            follow_up_messages = await config.get_follow_up_messages()
            if follow_up_messages:
                pending_messages = follow_up_messages
                continue

        # 没有更多消息，退出
        break

    stream.push(AgentEndEvent(messages=new_messages))
    stream.end(new_messages)


async def _stream_assistant_response(
    context: AgentContext,
    config: AgentLoopConfig,
    cancel_event: Optional[asyncio.Event],
    stream: EventStream[AgentEvent, List[AgentMessage]],
    stream_fn: Optional[StreamFn] = None,
) -> AssistantMessage:
    """
    流式获取 assistant 响应，支持自动重试。
    
    Args:
        context: Agent 上下文
        config: 循环配置
        cancel_event: 取消事件
        stream: 事件流
        stream_fn: 可选的自定义流式函数
        
    Returns:
        AssistantMessage 响应消息
        
    Raises:
        MaxRetriesExceededError: 超过最大重试次数
    """
    # 应用上下文转换（AgentMessage[] → AgentMessage[]）
    messages = list(context.messages)
    if config.transform_context:
        messages = await config.transform_context(messages, cancel_event)

    # 转换为 LLM 兼容消息（AgentMessage[] → Message[]）
    if config.convert_to_llm:
        result = config.convert_to_llm(messages)
        if inspect.isawaitable(result):
            llm_messages = await result
        else:
            llm_messages = result
    else:
        # 默认: 保留 user/assistant/toolResult
        llm_messages = [
            m
            for m in messages
            if getattr(m, "role", None) in ("user", "assistant", "toolResult")
        ]

    # 构建 LLM 上下文
    llm_context = {
        "system_prompt": context.system_prompt,
        "messages": llm_messages,
        "tools": context.tools,
    }

    # 选择流式函数
    stream_function = stream_fn or stream_simple

    # 解析 API key
    resolved_api_key = None
    if config.get_api_key:
        result = config.get_api_key(config.model.provider)
        if inspect.isawaitable(result):
            resolved_api_key = await result
        else:
            resolved_api_key = result
    if not resolved_api_key:
        resolved_api_key = config.api_key

    # 流式调用选项
    stream_options = {}
    if resolved_api_key:
        stream_options["api_key"] = resolved_api_key
    if config.reasoning:
        stream_options["reasoning"] = config.reasoning
    if config.session_id:
        stream_options["session_id"] = config.session_id

    # 模型路由逻辑：根据是否有 tools 选择不同模型
    has_tools = bool(llm_context.get("tools"))
    active_model = config.model
    active_config_name = config.model_config_name

    if config.model_router:
        active_model = config.model_router.select_model(has_tools)
        active_config_name = config.model_router.get_model_config_name(has_tools)
        logger.info(f"模型路由: has_tools={has_tools}, 使用模型={active_model.id}, config_name={active_config_name}")

    # Credit tracking: 如果启用，创建包装的流式函数
    if config.enable_credit_tracking and CREDIT_TRACKING_AVAILABLE:
        # 验证必需参数
        if not config.user_id:
            logger.warning("Credit tracking 启用但缺少 user_id，已禁用")
        elif not config.model_config_name:
            logger.warning("Credit tracking 启用但缺少 model_config_name，已禁用")
        else:
            # 创建 billing callback
            async def _billing_callback(usage_data: Dict[str, Any]) -> None:
                """计费回调函数"""
                try:
                    from api.billing import get_credit_service, TokenUsage
                    from api.database.base import get_session_factory

                    service = get_credit_service()
                    session_factory = get_session_factory()

                    async with session_factory() as session:
                        usage = TokenUsage(
                            input_tokens=usage_data["usage"].get("input", 0),
                            output_tokens=usage_data["usage"].get("output", 0),
                            cache_read_tokens=usage_data["usage"].get("cache_read", 0),
                            cache_write_tokens=usage_data["usage"].get("cache_write", 0),
                        )

                        await service.record_usage(
                            db=session,
                            user_id=config.user_id,
                            model=usage_data.get("model", active_model.id),
                            model_config_name=active_config_name,
                            usage=usage,
                            session_id=config.session_id,
                            project_id=config.project_id,
                            agent_role=config.agent_role,
                            action=usage_data.get("action", "llm_call"),
                        )

                        # 手动提交事务（async_sessionmaker 不会自动 commit）
                        await session.commit()
                except Exception as e:
                    logger.error(f"Credit 记录失败: {e}")

            # 包装流式函数
            original_stream_function = stream_function

            def _credit_wrapped_stream(model, context, **options):
                """带 credit tracking 的流式函数包装器"""
                return track_llm_usage(
                    model=model,
                    context=context,
                    billing_callback=_billing_callback,
                    model_config_name=active_config_name,
                    **options,
                )

            stream_function = _credit_wrapped_stream

    async def _do_stream():
        """执行单次流式操作"""
        # stream_function 现在是 async 函数，需要 await
        # 使用 active_model（可能经过路由选择）替代 config.model
        response = await stream_function(active_model, llm_context, **stream_options)

        partial_message: Optional[AssistantMessage] = None
        added_partial = False

        async for event in response:
            event_type = event.type

            if event_type == "start":
                partial_message = event.partial
                context.messages.append(partial_message)
                added_partial = True
                stream.push(MessageStartEvent(message=copy.copy(partial_message)))

            elif event_type in (
                "text_start",
                "text_delta",
                "text_end",
                "thinking_start",
                "thinking_delta",
                "thinking_end",
                "toolcall_start",
                "toolcall_delta",
                "toolcall_end",
            ):
                if partial_message:
                    partial_message = event.partial
                    context.messages[-1] = partial_message
                    stream.push(
                        MessageUpdateEvent(
                            message=copy.copy(partial_message),
                            assistant_message_event=event,
                        )
                    )

            elif event_type in ("done", "error"):
                final_message = await response.result()
                if added_partial:
                    context.messages[-1] = final_message
                else:
                    context.messages.append(final_message)
                if not added_partial:
                    stream.push(MessageStartEvent(message=copy.copy(final_message)))
                stream.push(MessageEndEvent(message=final_message))
                return final_message

        return await response.result()

    # 带重试执行流式操作
    return await _retry_stream_operation(_do_stream, "LLM stream")


async def _execute_tool_calls(
    tools: Optional[List[AgentTool]],
    assistant_message: AssistantMessage,
    cancel_event: Optional[asyncio.Event],
    stream: EventStream[AgentEvent, List[AgentMessage]],
    get_steering_messages: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    执行 assistant 消息中的工具调用。

    Args:
        tools: 可用工具列表
        assistant_message: 包含工具调用的 assistant 消息
        cancel_event: 取消事件
        stream: 事件流
        get_steering_messages: 获取 steering 消息的回调

    Returns:
        包含 tool_results 和可选 steering_messages 的字典
    """
    tool_calls = [c for c in assistant_message.content if isinstance(c, ToolCall)]
    results: List[ToolResultMessage] = []
    steering_messages: Optional[List[AgentMessage]] = None

    for index, tool_call in enumerate(tool_calls):
        # 检查取消
        if cancel_event and cancel_event.is_set():
            # 跳过剩余工具
            for skipped in tool_calls[index:]:
                results.append(_skip_tool_call(skipped, stream))
            break

        tool = None
        if tools:
            tool = next((t for t in tools if t.name == tool_call.name), None)

        stream.push(
            ToolExecutionStartEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                args=tool_call.arguments,
            )
        )

        result: AgentToolResult
        is_error = False

        try:
            if tool is None:
                raise RuntimeError(f"Tool '{tool_call.name}' not found")

            validated_args = validate_tool_arguments(tool, tool_call)

            def on_update(partial_result: AgentToolResult):
                stream.push(
                    ToolExecutionUpdateEvent(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                        partial_result=partial_result,
                    )
                )

            result = await tool.execute(
                tool_call.id, validated_args, cancel_event, on_update
            )

        except Exception as e:
            result = AgentToolResult(
                content=[TextContent(text=str(e))],
                details={},
            )
            is_error = True

        stream.push(
            ToolExecutionEndEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=result,
                is_error=is_error,
            )
        )

        tool_result_message = ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=result.content,
            details=result.details,
            is_error=is_error,
        )

        results.append(tool_result_message)
        stream.push(MessageStartEvent(message=tool_result_message))
        stream.push(MessageEndEvent(message=tool_result_message))

        # 检查 steering 消息——如果用户中断则跳过剩余工具
        if get_steering_messages:
            steering = await get_steering_messages()
            if steering:
                steering_messages = steering
                remaining_calls = tool_calls[index + 1 :]
                for skipped in remaining_calls:
                    results.append(_skip_tool_call(skipped, stream))
                break

    return {"tool_results": results, "steering_messages": steering_messages}


def _skip_tool_call(
    tool_call: ToolCall,
    stream: EventStream[AgentEvent, List[AgentMessage]],
) -> ToolResultMessage:
    """
    因 steering 跳过的工具调用。

    生成一个标记为错误的工具结果，告知 LLM 该工具被跳过。
    """
    result = AgentToolResult(
        content=[TextContent(text="Skipped due to queued user message.")],
        details={},
    )

    stream.push(
        ToolExecutionStartEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
        )
    )
    stream.push(
        ToolExecutionEndEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
            is_error=True,
        )
    )

    tool_result_message = ToolResultMessage(
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=result.content,
        details={},
        is_error=True,
    )

    stream.push(MessageStartEvent(message=tool_result_message))
    stream.push(MessageEndEvent(message=tool_result_message))

    return tool_result_message
