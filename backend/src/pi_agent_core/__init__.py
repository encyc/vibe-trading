"""
Pi-Agent-Core: Python 复刻版

基于 badlogic/pi-mono 的 @mariozechner/pi-agent-core 包进行的 Python 复刻。
提供有状态的 Agent、无状态的 Agent Loop、事件流、工具执行和 Skill 管理。

原始项目: https://github.com/badlogic/pi-mono
"""

# Core Agent
from .agent import Agent, AgentOptions

# Loop functions
from .agent_loop import agent_loop, agent_loop_continue

# Types
from .types import (
    AgentContext,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentState,
    AgentTool,
    AgentToolResult,
    ThinkingLevel,
)

# Event Stream
from pi_ai import EventStream, Model, get_model, stream_simple

# Skills
from .skills import Skill, load_skills, format_skills_for_prompt

__version__ = "0.1.0"

__all__ = [
    # Agent
    "Agent",
    "AgentOptions",
    # Loop
    "agent_loop",
    "agent_loop_continue",
    # Types
    "AgentState",
    "AgentTool",
    "AgentToolResult",
    "AgentMessage",
    "AgentEvent",
    "AgentContext",
    "AgentLoopConfig",
    "ThinkingLevel",
    # Event Stream
    "EventStream",
    # LLM
    "Model",
    "get_model",
    "stream_simple",
    # Skills
    "Skill",
    "load_skills",
    "format_skills_for_prompt",
]
