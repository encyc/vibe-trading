"""
代理流支持

对应 TypeScript 版本的 proxy.ts。
用于浏览器应用通过后端代理服务器调用 LLM。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

from .llm import (
    AssistantMessageEvent,
    StreamDoneEvent,
    StreamErrorEvent,
    StreamResponse,
    StreamStartEvent,
    StreamTextDeltaEvent,
    StreamTextEndEvent,
    StreamTextStartEvent,
    StreamThinkingDeltaEvent,
    StreamThinkingEndEvent,
    StreamThinkingStartEvent,
    StreamToolCallDeltaEvent,
    StreamToolCallEndEvent,
    StreamToolCallStartEvent,
    Model,
)
from .types import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCall,
)


@dataclass
class ProxyStreamOptions:
    """代理流选项"""

    auth_token: str
    proxy_url: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning: Optional[str] = None
    signal: Optional[Any] = None  # asyncio.Event


async def stream_proxy(
    model: Model,
    context: Dict[str, Any],
    options: ProxyStreamOptions,
) -> StreamResponse:
    """
    通过代理服务器的流式函数。

    服务器从 delta 事件中剥离 partial 字段以减少带宽。
    客户端在此重建完整的 partial 消息。

    使用方式:
        agent = Agent(AgentOptions(
            stream_fn=lambda model, context, **opts:
                stream_proxy(model, context, ProxyStreamOptions(
                    auth_token=get_auth_token(),
                    proxy_url="https://your-server.com",
                    **opts,
                )),
        ))
    """

    async def _generate() -> AsyncGenerator[AssistantMessageEvent, None]:
        try:
            import aiohttp
        except ImportError:
            raise ImportError("请安装 aiohttp 包: pip install aiohttp")

        # 构建 partial 消息
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

        headers = {
            "Authorization": f"Bearer {options.auth_token}",
            "Content-Type": "application/json",
        }

        body = {
            "model": {"provider": model.provider, "id": model.id, "api": model.api},
            "context": context,
            "options": {},
        }
        if options.temperature is not None:
            body["options"]["temperature"] = options.temperature
        if options.max_tokens is not None:
            body["options"]["max_tokens"] = options.max_tokens
        if options.reasoning:
            body["options"]["reasoning"] = options.reasoning

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{options.proxy_url}/api/stream",
                    headers=headers,
                    json=body,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"Proxy error: {response.status} {error_text}"
                        )

                    buffer = ""
                    async for chunk in response.content.iter_any():
                        if options.signal and options.signal.is_set():
                            raise RuntimeError("Request aborted by user")

                        buffer += chunk.decode("utf-8")
                        lines = buffer.split("\n")
                        buffer = lines.pop()

                        for line in lines:
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data:
                                    proxy_event = json.loads(data)
                                    event = _process_proxy_event(
                                        proxy_event, partial
                                    )
                                    if event:
                                        yield event

        except Exception as e:
            error_message = str(e)
            partial.stop_reason = "error"
            partial.error_message = error_message
            yield StreamErrorEvent(reason="error", error=partial)

    return StreamResponse(_generate())


def _process_proxy_event(
    proxy_event: Dict[str, Any],
    partial: AssistantMessage,
) -> Optional[AssistantMessageEvent]:
    """处理代理事件并更新 partial 消息"""
    event_type = proxy_event.get("type")

    if event_type == "start":
        return StreamStartEvent(partial=partial)

    elif event_type == "text_start":
        ci = proxy_event["contentIndex"]
        while len(partial.content) <= ci:
            partial.content.append(TextContent(text=""))
        partial.content[ci] = TextContent(text="")
        return StreamTextStartEvent(content_index=ci, partial=partial)

    elif event_type == "text_delta":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        if isinstance(content, TextContent):
            content.text += proxy_event["delta"]
        return StreamTextDeltaEvent(
            content_index=ci, delta=proxy_event["delta"], partial=partial
        )

    elif event_type == "text_end":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        text = content.text if isinstance(content, TextContent) else ""
        return StreamTextEndEvent(
            content_index=ci, content=text, partial=partial
        )

    elif event_type == "thinking_start":
        ci = proxy_event["contentIndex"]
        while len(partial.content) <= ci:
            partial.content.append(ThinkingContent(thinking=""))
        partial.content[ci] = ThinkingContent(thinking="")
        return StreamThinkingStartEvent(content_index=ci, partial=partial)

    elif event_type == "thinking_delta":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        if isinstance(content, ThinkingContent):
            content.thinking += proxy_event["delta"]
        return StreamThinkingDeltaEvent(
            content_index=ci, delta=proxy_event["delta"], partial=partial
        )

    elif event_type == "thinking_end":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        text = content.thinking if isinstance(content, ThinkingContent) else ""
        return StreamThinkingEndEvent(
            content_index=ci, content=text, partial=partial
        )

    elif event_type == "toolcall_start":
        ci = proxy_event["contentIndex"]
        while len(partial.content) <= ci:
            partial.content.append(
                ToolCall(id="", name="", arguments={})
            )
        partial.content[ci] = ToolCall(
            id=proxy_event.get("id", ""),
            name=proxy_event.get("toolName", ""),
            arguments={},
        )
        return StreamToolCallStartEvent(content_index=ci, partial=partial)

    elif event_type == "toolcall_delta":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        if isinstance(content, ToolCall):
            # 增量 JSON 解析（简化版）
            if not hasattr(content, "_partial_json"):
                content._partial_json = ""  # type: ignore
            content._partial_json += proxy_event["delta"]  # type: ignore
            try:
                content.arguments = json.loads(content._partial_json)  # type: ignore
            except json.JSONDecodeError:
                pass
        return StreamToolCallDeltaEvent(
            content_index=ci, delta=proxy_event["delta"], partial=partial
        )

    elif event_type == "toolcall_end":
        ci = proxy_event["contentIndex"]
        content = partial.content[ci]
        if isinstance(content, ToolCall):
            if hasattr(content, "_partial_json"):
                delattr(content, "_partial_json")
            return StreamToolCallEndEvent(
                content_index=ci, tool_call=content, partial=partial
            )

    elif event_type == "done":
        partial.stop_reason = proxy_event.get("reason", "stop")
        if "usage" in proxy_event:
            partial.usage = proxy_event["usage"]
        return StreamDoneEvent(
            reason=partial.stop_reason, message=partial
        )

    elif event_type == "error":
        partial.stop_reason = proxy_event.get("reason", "error")
        partial.error_message = proxy_event.get("errorMessage")
        if "usage" in proxy_event:
            partial.usage = proxy_event["usage"]
        return StreamErrorEvent(reason=partial.stop_reason, error=partial)

    return None
