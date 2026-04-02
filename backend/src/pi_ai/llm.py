"""
LLM 抽象层

对应 TypeScript 版本的 @mariozechner/pi-ai 核心功能。
提供统一的 LLM 模型定义和流式调用接口。

支持的 Provider:
  - openai (OpenAI API 兼容)
  - anthropic (Anthropic Claude)
  - google (Google Gemini)

用户也可以自定义 Provider 适配器。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

from .types import (
    AssistantMessage,
    Content,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    ToolDef,
)
from .exceptions import (
    LLMStreamError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMAuthenticationError,
    AgentValidationError,
)


# =============================================================================
# Model
# =============================================================================


@dataclass
class Model:
    """
    LLM 模型定义。

    Attributes:
        provider: 提供商标识 (e.g. "openai", "anthropic", "google")
        id: 模型 ID (e.g. "gpt-4o", "claude-sonnet-4-20250514")
        api: API 类型 (e.g. "openai", "anthropic", "google")
        api_key: API 密钥（可选，也可通过环境变量设置）
        base_url: 自定义 API 基础 URL（可选）
    """

    provider: str
    id: str
    api: str = ""
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def __post_init__(self):
        if not self.api:
            self.api = self.provider


def get_model(provider: str, model_id: str, **kwargs) -> Model:
    """
    创建一个 Model 实例。

    Args:
        provider: 提供商标识
        model_id: 模型 ID
        **kwargs: 额外参数 (api_key, base_url 等)

    Returns:
        Model 实例
    """
    return Model(provider=provider, id=model_id, **kwargs)


# =============================================================================
# Assistant Message Event (流式事件)
# =============================================================================


@dataclass
class StreamStartEvent:
    """流开始"""

    partial: AssistantMessage
    type: str = "start"


@dataclass
class StreamTextStartEvent:
    """文本块开始"""

    content_index: int
    partial: AssistantMessage
    type: str = "text_start"


@dataclass
class StreamTextDeltaEvent:
    """文本增量"""

    content_index: int
    delta: str
    partial: AssistantMessage
    type: str = "text_delta"


@dataclass
class StreamTextEndEvent:
    """文本块结束"""

    content_index: int
    content: str
    partial: AssistantMessage
    type: str = "text_end"


@dataclass
class StreamThinkingStartEvent:
    """思考块开始"""

    content_index: int
    partial: AssistantMessage
    type: str = "thinking_start"


@dataclass
class StreamThinkingDeltaEvent:
    """思考增量"""

    content_index: int
    delta: str
    partial: AssistantMessage
    type: str = "thinking_delta"


@dataclass
class StreamThinkingEndEvent:
    """思考块结束"""

    content_index: int
    content: str
    partial: AssistantMessage
    type: str = "thinking_end"


@dataclass
class StreamToolCallStartEvent:
    """工具调用开始"""

    content_index: int
    partial: AssistantMessage
    type: str = "toolcall_start"


@dataclass
class StreamToolCallDeltaEvent:
    """工具调用增量"""

    content_index: int
    delta: str
    partial: AssistantMessage
    type: str = "toolcall_delta"


@dataclass
class StreamToolCallEndEvent:
    """工具调用结束"""

    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage
    type: str = "toolcall_end"


@dataclass
class StreamDoneEvent:
    """流完成"""

    reason: str  # "stop" | "length" | "toolUse"
    message: AssistantMessage
    type: str = "done"


@dataclass
class StreamErrorEvent:
    """流错误"""

    reason: str  # "aborted" | "error"
    error: AssistantMessage
    type: str = "error"


# 流事件联合类型
AssistantMessageEvent = Union[
    StreamStartEvent,
    StreamTextStartEvent,
    StreamTextDeltaEvent,
    StreamTextEndEvent,
    StreamThinkingStartEvent,
    StreamThinkingDeltaEvent,
    StreamThinkingEndEvent,
    StreamToolCallStartEvent,
    StreamToolCallDeltaEvent,
    StreamToolCallEndEvent,
    StreamDoneEvent,
    StreamErrorEvent,
]


# =============================================================================
# Stream Response Wrapper
# =============================================================================


class StreamResponse:
    """
    流式响应包装器。

    包装 LLM 的流式响应，提供事件迭代和最终结果获取。
    """

    def __init__(self, events_gen: AsyncGenerator[AssistantMessageEvent, None]):
        self._events_gen = events_gen
        self._result: Optional[AssistantMessage] = None

    def __aiter__(self):
        return self._wrap_events()

    async def _wrap_events(self):
        async for event in self._events_gen:
            if event.type == "done":
                self._result = event.message
            elif event.type == "error":
                self._result = event.error
            yield event

    async def result(self) -> AssistantMessage:
        """获取最终的完整消息"""
        if self._result is None:
            # 消费所有事件
            async for _ in self._wrap_events():
                pass
        if self._result is None:
            raise LLMStreamError("流式响应未产生结果")
        return self._result


# =============================================================================
# Tool 参数验证
# =============================================================================


def validate_tool_arguments(tool: ToolDef, tool_call: ToolCall) -> Any:
    """
    使用 Pydantic 模型验证工具调用参数。

    Args:
        tool: 工具定义
        tool_call: LLM 的工具调用

    Returns:
        验证后的参数对象

    Raises:
        AgentValidationError: 参数验证失败
    """
    try:
        validated = tool.parameters(**tool_call.arguments)
        return validated
    except Exception as e:
        raise AgentValidationError(
            f"工具 '{tool.name}' 参数验证失败: {e}",
            field=list(tool_call.arguments.keys()) if tool_call.arguments else None
        ) from e


# =============================================================================
# Provider 适配器协议
# =============================================================================


@runtime_checkable
class ProviderAdapter(Protocol):
    """LLM Provider 适配器协议"""

    async def stream(
        self,
        model: Model,
        messages: List[Any],
        system_prompt: str,
        tools: Optional[List[ToolDef]] = None,
        **kwargs,
    ) -> AsyncGenerator[AssistantMessageEvent, None]: ...


# =============================================================================
# OpenAI 兼容 Provider
# =============================================================================


class OpenAIProvider:
    """
    OpenAI API 兼容的 Provider 适配器。

    支持 OpenAI 官方 API 和所有兼容的第三方 API（如 DeepSeek、
    Moonshot、Together AI 等）。
    """

    def __init__(self):
        self._client = None

    def _get_client(self, model: Model, api_key: Optional[str] = None):
        """延迟初始化 OpenAI 客户端"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "请安装 openai 包: pip install openai"
            )

        key = api_key or model.api_key or os.environ.get("OPENAI_API_KEY", "")
        base_url = model.base_url

        return AsyncOpenAI(api_key=key, base_url=base_url)

    async def stream(
        self,
        model: Model,
        messages: List[Any],
        system_prompt: str,
        tools: Optional[List[ToolDef]] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[AssistantMessageEvent, None]:
        """流式调用 OpenAI API"""
        client = self._get_client(model, api_key)

        # 构建消息
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "user":
                content_parts = []
                for c in msg.content:
                    if c.type == "text":
                        content_parts.append({"type": "text", "text": c.text})
                    elif c.type == "image":
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{c.mime_type};base64,{c.data}"
                            },
                        })
                api_messages.append({"role": "user", "content": content_parts})

            elif msg.role == "assistant":
                content_text = ""
                tool_calls_list = []
                for c in msg.content:
                    if c.type == "text":
                        content_text += c.text
                    elif c.type == "toolCall":
                        tool_calls_list.append({
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments),
                            },
                        })
                assistant_msg: Dict[str, Any] = {"role": "assistant"}
                if content_text:
                    assistant_msg["content"] = content_text
                if tool_calls_list:
                    assistant_msg["tool_calls"] = tool_calls_list
                api_messages.append(assistant_msg)

            elif msg.role == "toolResult":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": "\n".join(
                        c.text for c in msg.content if c.type == "text"
                    ),
                })

        # 构建工具定义
        api_tools = None
        if tools:
            api_tools = []
            for tool in tools:
                schema = tool.parameters.model_json_schema()
                # 移除 Pydantic 自动添加的 title 字段
                schema.pop("title", None)
                api_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": schema,
                    },
                })

        # 建立流式连接
        create_kwargs: Dict[str, Any] = {
            "model": model.id,
            "messages": api_messages,
            "stream": True,
        }
        if api_tools:
            create_kwargs["tools"] = api_tools

        # 合并额外参数（排除不应传递给 API 的参数）
        excluded_keys = ("signal", "api_key", "session_id", "user_id", "project_id")
        for k, v in kwargs.items():
            if k not in excluded_keys and v is not None:
                create_kwargs[k] = v

        partial = AssistantMessage(
            content=[],
            api=model.api,
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
        )

        yield StreamStartEvent(partial=partial)

        try:
            response = await client.chat.completions.create(**create_kwargs)

            current_tool_calls: Dict[int, Dict[str, Any]] = {}

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None

                # 处理文本内容
                if delta.content:
                    # 确保有文本内容块
                    if not partial.content or partial.content[-1].type != "text":
                        text_content = TextContent(text="")
                        partial.content.append(text_content)
                        ci = len(partial.content) - 1
                        yield StreamTextStartEvent(
                            content_index=ci, partial=partial
                        )

                    ci = len(partial.content) - 1
                    text_block = partial.content[ci]
                    if isinstance(text_block, TextContent):
                        text_block.text += delta.content
                    yield StreamTextDeltaEvent(
                        content_index=ci,
                        delta=delta.content,
                        partial=partial,
                    )

                # 处理工具调用
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": "",
                            }
                            tool_call_obj = ToolCall(
                                id=current_tool_calls[idx]["id"],
                                name=current_tool_calls[idx]["name"],
                                arguments={},
                            )
                            partial.content.append(tool_call_obj)
                            ci = len(partial.content) - 1
                            yield StreamToolCallStartEvent(
                                content_index=ci, partial=partial
                            )
                        else:
                            if tc.id:
                                current_tool_calls[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name

                        if tc.function and tc.function.arguments:
                            current_tool_calls[idx]["arguments"] += tc.function.arguments
                            # 更新 partial
                            ci_offset = len(partial.content) - len(current_tool_calls) + idx
                            if 0 <= ci_offset < len(partial.content):
                                tc_content = partial.content[ci_offset]
                                if isinstance(tc_content, ToolCall):
                                    tc_content.id = current_tool_calls[idx]["id"]
                                    tc_content.name = current_tool_calls[idx]["name"]
                                    try:
                                        tc_content.arguments = json.loads(
                                            current_tool_calls[idx]["arguments"]
                                        )
                                    except json.JSONDecodeError:
                                        pass
                                yield StreamToolCallDeltaEvent(
                                    content_index=ci_offset,
                                    delta=tc.function.arguments,
                                    partial=partial,
                                )

                # 完成
                if finish_reason:
                    # 结束所有打开的文本块
                    for i, c in enumerate(partial.content):
                        if isinstance(c, TextContent):
                            yield StreamTextEndEvent(
                                content_index=i,
                                content=c.text,
                                partial=partial,
                            )

                    # 结束所有工具调用
                    for idx, tc_data in current_tool_calls.items():
                        ci_offset = len(partial.content) - len(current_tool_calls) + idx
                        if 0 <= ci_offset < len(partial.content):
                            tc_content = partial.content[ci_offset]
                            if isinstance(tc_content, ToolCall):
                                yield StreamToolCallEndEvent(
                                    content_index=ci_offset,
                                    tool_call=tc_content,
                                    partial=partial,
                                )

                    # 设置 usage
                    if chunk.usage:
                        # 提取缓存 token (OpenAI 特有)
                        cache_read_tokens = 0
                        if hasattr(chunk.usage, "prompt_tokens_details"):
                            details = chunk.usage.prompt_tokens_details
                            if details and hasattr(details, "cached_tokens"):
                                cache_read_tokens = details.cached_tokens or 0

                        partial.usage = {
                            "input": chunk.usage.prompt_tokens or 0,
                            "output": chunk.usage.completion_tokens or 0,
                            "cached_tokens": cache_read_tokens,  # 保持向后兼容
                            "cache_read": cache_read_tokens,
                            "cache_write": 0,  # OpenAI 不提供此字段
                            "total_tokens": chunk.usage.total_tokens or 0,
                            "cost": {"input": 0, "output": 0, "total": 0},
                        }

                    if finish_reason == "tool_calls":
                        partial.stop_reason = "toolUse"
                    elif finish_reason == "length":
                        partial.stop_reason = "length"
                    else:
                        partial.stop_reason = "stop"

                    yield StreamDoneEvent(
                        reason=partial.stop_reason, message=partial
                    )

        except Exception as e:
            error_str = str(e)
            
            # 检测速率限制错误 (429)
            if "429" in error_str or "rate limit" in error_str.lower() or "速率限制" in error_str:
                partial.stop_reason = "error"
                partial.error_message = error_str
                yield StreamErrorEvent(reason="error", error=partial)
                raise LLMRateLimitError(provider=model.provider)
            
            # 检测认证错误
            if "401" in error_str or "unauthorized" in error_str.lower():
                partial.stop_reason = "error"
                partial.error_message = error_str
                yield StreamErrorEvent(reason="error", error=partial)
                raise LLMAuthenticationError(provider=model.provider)
            
            # 其他错误
            partial.stop_reason = "error"
            partial.error_message = error_str
            yield StreamErrorEvent(reason="error", error=partial)


# =============================================================================
# Provider 注册表
# =============================================================================

_PROVIDERS: Dict[str, ProviderAdapter] = {}


def register_provider(name: str, provider: ProviderAdapter) -> None:
    """注册一个 LLM Provider"""
    _PROVIDERS[name] = provider


def get_provider(name: str) -> ProviderAdapter:
    """获取 Provider 实例"""
    if name not in _PROVIDERS:
        # 尝试自动注册
        if name == "openai":
            _PROVIDERS[name] = OpenAIProvider()
        else:
            raise ValueError(
                f"Unknown provider: {name}. "
                f"Available: {list(_PROVIDERS.keys())}. "
                f"Use register_provider() to register custom providers."
            )
    return _PROVIDERS[name]


# =============================================================================
# stream_simple (核心流式调用)
# =============================================================================


async def stream_simple(
    model: Model,
    context: Dict[str, Any],
    **options,
) -> StreamResponse:
    """
    统一的 LLM 流式调用函数。

    对应 TypeScript 版本的 streamSimple()。
    根据 model.provider 选择对应的 Provider 进行调用。

    Args:
        model: LLM 模型
        context: 上下文字典 (system_prompt, messages, tools)
        **options: 额外选项 (api_key, reasoning, signal 等)

    Returns:
        StreamResponse 包装器
    """
    provider = get_provider(model.provider)

    system_prompt = context.get("system_prompt", "")
    messages = context.get("messages", [])
    tools = context.get("tools", None)

    async def _generate():
        async for event in provider.stream(
            model=model,
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            **options,
        ):
            yield event

    return StreamResponse(_generate())
