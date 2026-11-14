"""交易系统的 agent 运行时（zenagent kernel 的唯一入口）。

见 :mod:`vibe_trading.runtime.agent` 的模块文档。
"""
from __future__ import annotations

from vibe_trading.runtime.agent import TradingAgent, one_shot
from vibe_trading.runtime.messages import (
    is_assistant,
    is_tool_result,
    is_user,
    last_assistant,
    last_assistant_text,
    message_text,
)
from vibe_trading.runtime.model import for_role, get_api_key, get_model, tuned_stream
from vibe_trading.runtime.tools import make_tool

__all__ = [
    "TradingAgent",
    "for_role",
    "get_api_key",
    "get_model",
    "is_assistant",
    "is_tool_result",
    "is_user",
    "last_assistant",
    "last_assistant_text",
    "make_tool",
    "message_text",
    "one_shot",
    "tuned_stream",
]
