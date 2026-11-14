"""工具适配：把本项目的 (Pydantic 参数类 + 异步 execute 函数) 包装成 zenagent 工具。

zenagent 的 ``AgentTool`` 是 dataclass（不是 Protocol），字段：

    name / description / parameters(JSON Schema dict) / execute /
    execution_mode / approval / timeout_s / hidden / default_inactive

``execute(call_id, args, abort, on_update) -> ToolResultAgent``。

本项目 24 个工具一直是 ``(name, args: Pydantic, extra, callback)`` 的形状，
由执行函数自己用 Pydantic 校验。适配器在中间做 dict → Pydantic 的转换，
业务函数零改动。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional, Type

from pydantic import BaseModel
from zenagent.agent.loop import AgentTool, ToolResultAgent

__all__ = ["make_tool"]


def make_tool(
    *,
    name: str,
    description: str,
    parameters: Type[BaseModel],
    execute: Callable[..., Awaitable[ToolResultAgent]],
    approval: str = "exec",
    execution_mode: str = "parallel",
    timeout_s: Optional[float] = None,
    label: str = "",
) -> AgentTool:
    """把一个 Pydantic 参数类 + 执行函数组装成 zenagent AgentTool。

    Args:
        name: 模型看到的工具名。
        description: 模型看到的工具说明。
        parameters: Pydantic 参数模型类（转成 JSON Schema 交给模型）。
        execute: 业务执行函数，签名 ``(name, args: <Pydantic>, extra, callback)``，
            返回 ``ToolResultAgent``。
        approval: 能力声明 —— ``read``（只读）/ ``write``（改文件/状态）/
            ``exec``（执行动作）。交易工具都调外部 API 或下单，用 ``exec``。
        execution_mode: ``parallel``（可并发）或 ``sequential``（同批内单独串行）。
            下单类工具用 ``sequential``，避免与其他工具并发。
        timeout_s: 单次调用墙钟上限（None = 不限，由工具自己管）。
        label: 人类可读的工具标签。zenagent 的 AgentTool 没有这个字段，
            仅用于日志/调试；保留参数是为了让 24 个调用点不改。
    """
    params_cls = parameters

    async def _execute(
        call_id: str,
        args: Any,
        abort: Any = None,
        on_update: Optional[Callable[[ToolResultAgent], None]] = None,
    ) -> ToolResultAgent:
        # args 来自模型（dict）；Pydantic 负责校验与默认值填充。
        # 已经是目标类型时直接用（测试与内部调用会这么传）。
        if isinstance(args, params_cls):
            parsed = args
        elif isinstance(args, dict):
            parsed = params_cls(**args)
        else:
            parsed = params_cls.model_validate(args)
        return await execute(name, parsed, None, on_update)

    return AgentTool(
        name=name,
        description=description,
        parameters=params_cls.model_json_schema(),
        execute=_execute,
        approval=approval,
        execution_mode=execution_mode,
        timeout_s=timeout_s,
    )
