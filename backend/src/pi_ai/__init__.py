"""
pi-ai 核心包
提供统一的 LLM API 抽象层和异步流等工具。
"""

from .event_stream import EventStream
from .llm import (
    Model,
    get_model,
    stream_simple,
    StreamResponse,
    AssistantMessageEvent,
    validate_tool_arguments,
)
from .config import (
    LLMConfig,
    get_llm_config,
    get_model_from_config,
    set_current_llm,
    list_llm_configs,
)
from .model_router import ModelRouter, create_model_router_from_config
from .types import (
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
    ToolDef,
)
from .exceptions import (
    PiAIError,
    LLMError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMStreamError,
    LLMTimeoutError,
    LLMAuthenticationError,
    AgentError,
    AgentToolError,
    AgentValidationError,
    AgentCancelledError,
    RetryableError,
    MaxRetriesExceededError,
)

__version__ = "0.1.0"

__all__ = [
    # Event Stream
    "EventStream",
    # LLM
    "Model",
    "get_model",
    "stream_simple",
    "StreamResponse",
    "AssistantMessageEvent",
    "validate_tool_arguments",
    # Config
    "LLMConfig",
    "get_llm_config",
    "get_model_from_config",
    "set_current_llm",
    "list_llm_configs",
    # Model Router
    "ModelRouter",
    "create_model_router_from_config",
    # Types
    "TextContent",
    "ImageContent",
    "ThinkingContent",
    "ToolCall",
    "Content",
    "ThinkingLevel",
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "Message",
    "ToolDef",
    # Exceptions
    "PiAIError",
    "LLMError",
    "LLMConnectionError",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMStreamError",
    "LLMTimeoutError",
    "LLMAuthenticationError",
    "AgentError",
    "AgentToolError",
    "AgentValidationError",
    "AgentCancelledError",
    "RetryableError",
    "MaxRetriesExceededError",
]
