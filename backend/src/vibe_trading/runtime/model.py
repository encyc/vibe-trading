"""模型与采样参数装配。

两个职责：

1. **构造 Model**：交给 ``config.llm_config``（catalog 命中 → 继承；未命中 →
   sniff_compat 兜底）。这里只做转发，让 agent 层不直接 import zenagent。

2. **注入采样参数**：zenagent 的 ``Agent`` 没有 ``temperature`` /
   ``max_tokens`` 入口——loop 构造 ``StreamOptions`` 时只填
   ``api_key`` / ``thinking`` / ``session_id`` / ``abort``。但 ``stream_fn``
   是公开接缝，包一层就能把这两个值补上：

       async def stream(model, messages, tools, options):
           options = replace(options, temperature=0.4, max_tokens=2000)
           async for event in inner(model, messages, tools, options):
               yield event

   迁移前 ``AgentConfig.temperature`` 有 12 个值但从未被读取（
   ``create_trading_agent`` 不读它，``AgentOptions`` 也没有该字段），
   所以这里的注入是**故意引入的行为变更**：agent 的输出会随之变化。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from zenagent.providers.catalog import Model
from zenagent.providers.registry import StreamFn, stream_fn_for
from zenagent.providers.stream_options import StreamOptions

from vibe_trading.config.llm_config import (
    get_api_key_from_config,
    get_llm_config,
    get_model_from_config,
)

__all__ = [
    "for_role",
    "get_api_key",
    "get_model",
    "tuned_stream",
]


def get_model(name: Optional[str] = None) -> Model:
    """取配置对应的 zenagent Model。"""
    return get_model_from_config(name)


def get_api_key(name: Optional[str] = None) -> str:
    """取配置对应的 api_key（无则空串，交给上游报错）。"""
    return get_api_key_from_config(name) or ""


def for_role(role: Optional[str] = None) -> tuple[Model, str, Optional[float]]:
    """一次取齐构造 agent 需要的三样：Model、api_key、温度。

    ``role`` 目前不影响选择（12 个 agent 跑同一个模型，与迁移前一致）；
    保留参数是为了将来按角色分派模型时不必改调用点。
    """
    cfg = get_llm_config()
    return (
        cfg.get_model(),
        cfg.get_api_key() or "",
        cfg.get_temperature(),
    )


def tuned_stream(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    base: Optional[StreamFn] = None,
) -> Optional[StreamFn]:
    """把采样参数预先绑进 stream_fn。

    两个参数都是 None 时返回 None，让 zenagent 走自己的默认派发
    （``stream_fn_for(model)``），不多包一层。

    ``base`` 留作测试注入口（传假流即可离线验证）；默认从
    ``stream_fn_for`` 取底层实现需要在拿到 model 之后，所以这里在调用时解析。
    """

    if temperature is None and max_tokens is None:
        return None

    overrides: dict = {}
    if temperature is not None:
        overrides["temperature"] = temperature
    if max_tokens is not None:
        overrides["max_tokens"] = max_tokens

    # 延迟到调用期解析底层实现：构造 agent 时还没决定用哪个 model
    holder: dict = {}

    async def stream(model, messages, tools, options):
        inner = base if base is not None else holder.get("inner")
        if inner is None:
            inner = stream_fn_for(model)
            holder["inner"] = inner
        patched = replace(options, **overrides)
        assert isinstance(patched, StreamOptions)  # replace 保留类型
        async for event in inner(model, messages, tools, patched):
            yield event

    return stream
