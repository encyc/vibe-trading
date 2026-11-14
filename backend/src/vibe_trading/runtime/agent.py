"""交易系统的 agent 运行时：zenagent kernel 的唯一包装层。

这一层存在的理由是**边界**：``vibe_trading`` 的其余部分不 import
``zenagent``，只 import 这里。换掉内核时只需改这个包。

刻意不包装的东西：

* **AgentState**：只暴露调用点实际用到的成员，而不是把整个状态机透传出去。
* **成本**：``llm.yaml`` 的配置若不在 zenagent catalog 里，``usage.cost``
  恒为 0；暴露它只会让人误以为是准的。
* **会话持久化**：zenagent 的 ``Session`` 是为交互式 ``/compact`` 与 fork 设计
  的；本项目用 ``vibe_trading.db`` 记账。

使用示例::

    from vibe_trading.runtime import TradingAgent, make_tool

    agent = TradingAgent(role="technical_analyst", system_prompt=..., tools=[...])
    await agent.prompt("分析 BTCUSDT")
    print(agent.last_assistant_text())
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from zenagent.agent import Agent as _ZenAgent
from zenagent.agent.loop import AgentTool as ZenAgentTool
from zenagent.agent.loop import ToolResultAgent
from zenagent.events import AgentEvent
from zenagent.types import Message

from vibe_trading.runtime.messages import (
    is_assistant,
    is_tool_result,
    is_user,
    last_assistant_text,
    message_text,
)
from vibe_trading.runtime.model import for_role, get_api_key, get_model, tuned_stream
from vibe_trading.runtime.tools import make_tool

__all__ = [
    "AgentEvent",
    "AgentTool",
    "Message",
    "ToolResultAgent",
    "TradingAgent",
    "for_role",
    "get_api_key",
    "get_model",
    "is_assistant",
    "is_tool_result",
    "is_user",
    "last_assistant_text",
    "make_tool",
    "message_text",
    "one_shot",
    "tuned_stream",
]

#: 别名：工具构造沿用项目里的老名字
AgentTool = ZenAgentTool


class TradingAgent:
    """一个交易 agent 的运行时包装。

    ``prompt()`` 一次跑完一轮对话（含工具调用）；zenagent 同一时刻只允许一个
    run，所以并发调用要先用 :attr:`is_running` 判断。
    """

    def __init__(
        self,
        *,
        role: str,
        system_prompt: str,
        tools: Optional[list[ZenAgentTool]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_event: Optional[Callable[[AgentEvent], Any]] = None,
    ) -> None:
        model, api_key, config_temperature = for_role(role)
        # 显式传入的温度优先；否则用 llm.yaml 里该配置的温度
        effective_temperature = temperature if temperature is not None else config_temperature

        self.role = role
        self.system_prompt = system_prompt
        self._agent = _ZenAgent(
            model=model,
            system_prompt=system_prompt,
            tools=list(tools or []),
            api_key=api_key,
            stream_fn=tuned_stream(
                temperature=effective_temperature, max_tokens=max_tokens
            ),
        )
        if on_event is not None:
            self._agent.subscribe(on_event)

    # -- 驱动 ---------------------------------------------------------------

    async def prompt(self, text: str) -> None:
        """跑一轮对话。运行中调用会抛 RuntimeError（先看 :attr:`is_running`）。"""
        await self._agent.prompt(text)

    async def wait_for_idle(self) -> None:
        await self._agent.wait_for_idle()

    def abort(self) -> None:
        self._agent.abort()

    def steer(self, text: str) -> None:
        """运行中注入提示（下一轮工具调用后生效）。"""
        self._agent.steer(text)

    # -- 状态 ---------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """是否有 run 在跑。并行 prompt 前必须判断。"""
        return self._agent.is_streaming

    @property
    def messages(self) -> list[Message]:
        return self._agent.messages

    @property
    def tools(self) -> list[ZenAgentTool]:
        """本 agent 可用的工具（只读快照）。"""
        return list(self._agent.tools)

    @property
    def termination(self) -> Optional[str]:
        return self._agent.termination

    @property
    def last_stop_reason(self) -> Optional[str]:
        """最后一条助手消息的 stop_reason。

        ``termination`` 只有在 provider 报错/取消时才会变成 ``"error"`` /
        ``"aborted"``；正常轮次的终止原因在这里（``"stop"`` / ``"length"`` /
        ``"tool_use"``）。``"length"`` 意味着输出被 max_tokens 截断——调用方
        应当把它当作"报告不完整"而不是"报告很短"。
        """
        from zenagent.types import AssistantMessage

        for message in reversed(self._agent.messages):
            if isinstance(message, AssistantMessage):
                return message.stop_reason
        return None

    @property
    def was_truncated(self) -> bool:
        """最后一条助手回复是否因输出上限被截断。"""
        return self.last_stop_reason == "length"

    @property
    def error_message(self) -> Optional[str]:
        return self._agent.error_message

    def last_assistant_text(self) -> str:
        """最后一条助手回复的文本；空串表示 agent 没给出回复。"""
        return last_assistant_text(self._agent.messages)

    def reset(self) -> None:
        """清空对话历史（配置保留）。重复分析前调用。"""
        self._agent.reset()

    def subscribe(self, listener: Callable[[AgentEvent], Any]) -> None:
        """订阅运行时事件（``(event)`` 一个参数；2 参回调也兼容）。"""
        self._agent.subscribe(listener)

    def __repr__(self) -> str:
        return f"<TradingAgent role={self.role!r} messages={len(self.messages)}>"


async def one_shot(
    system_prompt: str,
    user_text: str,
    *,
    role: str = "one_shot",
    temperature: Optional[float] = None,
) -> str:
    """一次性无工具调用，返回助手文本。

    zenagent 没有 ``stream_simple`` 之类的一次性 helper，用它自己的 ``Agent``
    拼一个最短的：单轮、无工具、跑完取文本。
    """
    agent = TradingAgent(
        role=role,
        system_prompt=system_prompt,
        tools=[],
        temperature=temperature,
        max_tokens=None,
    )
    # 单轮：不要让模型有机会继续（无工具时多轮也无意义）
    await agent.prompt(user_text)
    return agent.last_assistant_text()
