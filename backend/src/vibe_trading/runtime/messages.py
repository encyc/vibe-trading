"""消息读取的稳定接口。

zenagent 的消息 dataclass（``UserMessage`` / ``AssistantMessage`` /
``ToolResultMessage``）**没有 ``.role`` 属性** —— ``role`` 只出现在
``to_json()`` 的返回值里。用 ``getattr(m, "role", None) == "assistant"`` 判断
会静默取到 ``None``，把"没有助手回复"伪装成正常空结果。

所以 agent 层一律通过这里的 ``isinstance`` 判别读取消息，不碰 ``role``。
"""
from __future__ import annotations

from zenagent.types import (
    AssistantMessage,
    Message,
    TextContent,
    ThinkingContent,
    ToolResultMessage,
    UserMessage,
)

__all__ = [
    "assistant_text",
    "is_assistant",
    "is_tool_result",
    "is_user",
    "last_assistant",
    "last_assistant_text",
    "message_text",
]


def is_assistant(message: Message) -> bool:
    """该消息是否是助手回复。"""
    return isinstance(message, AssistantMessage)


def is_user(message: Message) -> bool:
    """该消息是否是用户输入。"""
    return isinstance(message, UserMessage)


def is_tool_result(message: Message) -> bool:
    """该消息是否是工具结果。"""
    return isinstance(message, ToolResultMessage)


def message_text(message: Message) -> str:
    """把消息里的文本内容块拼成一段纯文本（忽略思考块与工具调用）。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    parts = [
        block.text
        for block in content
        if isinstance(block, TextContent) and block.text
    ]
    return "".join(parts)


def last_assistant(messages: list[Message]) -> AssistantMessage | None:
    """最后一条助手消息；没有则返回 None。"""
    for message in reversed(messages):
        if isinstance(message, AssistantMessage):
            return message
    return None


def last_assistant_text(messages: list[Message]) -> str:
    """最后一条助手消息的文本；没有助手消息时返回空字符串。

    调用点据此判断"agent 有没有给出回复"——空字符串意味着没有，而不是
    "agent 返回了一句空话"。
    """
    message = last_assistant(messages)
    if message is None:
        return ""
    return message_text(message)


def assistant_text(message: AssistantMessage) -> str:
    """助手消息的文本内容（含思考块之外的纯文本）。"""
    return message_text(message)


def thinking_text(message: AssistantMessage) -> str:
    """助手消息里的思考内容（流式打印用）。"""
    return "".join(
        block.thinking
        for block in message.content
        if isinstance(block, ThinkingContent) and block.thinking
    )
