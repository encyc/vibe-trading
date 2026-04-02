"""
pi-ai 核心类型定义

定义底层 LLM 提供商交互的标准化消息类型和内容块。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union, Protocol, Type

from pydantic import BaseModel


# =============================================================================
# Content Types
# =============================================================================

@dataclass
class TextContent:
    """文本内容块"""
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImageContent:
    """图片内容块"""
    data: str  # base64 编码
    mime_type: str  # e.g. "image/jpeg"
    type: Literal["image"] = "image"


@dataclass
class ThinkingContent:
    """思考内容块 (reasoning)"""
    thinking: str
    type: Literal["thinking"] = "thinking"


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]
    type: Literal["toolCall"] = "toolCall"


# 内容类型联合
Content = Union[TextContent, ImageContent, ThinkingContent, ToolCall]


# =============================================================================
# Thinking Level
# =============================================================================

class ThinkingLevel(str, Enum):
    """思考/推理级别"""
    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


# =============================================================================
# Message Types
# =============================================================================

@dataclass
class UserMessage:
    """用户消息"""
    content: List[Union[TextContent, ImageContent]]
    timestamp: float = field(default_factory=time.time)
    role: Literal["user"] = "user"


@dataclass
class AssistantMessage:
    """助手消息"""
    content: List[Content]
    api: str = ""
    provider: str = ""
    model: str = ""
    stop_reason: str = "stop"  # "stop" | "length" | "toolUse" | "error" | "aborted"
    error_message: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    role: Literal["assistant"] = "assistant"


@dataclass
class ToolResultMessage:
    """工具结果消息"""
    tool_call_id: str
    tool_name: str
    content: List[Union[TextContent, ImageContent]]
    is_error: bool = False
    details: Any = None
    timestamp: float = field(default_factory=time.time)
    role: Literal["toolResult"] = "toolResult"


# 标准 LLM 消息联合类型
Message = Union[UserMessage, AssistantMessage, ToolResultMessage]


# =============================================================================
# Tool Definition Protocol
# =============================================================================

class ToolDef(Protocol):
    """
    底层 LLM 流接口所需要的 Tool 协议定义。
    只需要具有名字、描述以及 Pydantic 模型的参数即可。
    """
    name: str
    description: str
    parameters: Type[BaseModel]
