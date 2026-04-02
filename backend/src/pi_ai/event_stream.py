"""
异步事件流

对应 TypeScript 版本 pi-ai 的 EventStream 类。
使用 asyncio.Queue 实现异步事件的推送和消费。
"""

from __future__ import annotations

import asyncio
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Generic,
    List,
    Optional,
    TypeVar,
)

TEvent = TypeVar("TEvent")
TResult = TypeVar("TResult")

_SENTINEL = object()


class EventStream(Generic[TEvent, TResult]):
    """
    异步事件流。

    支持生产者推送事件、消费者异步迭代消费。
    对应 TypeScript 中 pi-ai 的 EventStream<TEvent, TResult>。

    用法:
        stream = EventStream(
            is_terminal=lambda e: e.type == "agent_end",
            extract_result=lambda e: e.messages if e.type == "agent_end" else []
        )

        # 生产者
        stream.push(event)
        stream.end(result)

        # 消费者
        async for event in stream:
            handle(event)

        result = await stream.result()
    """

    def __init__(
        self,
        is_terminal: Callable[[TEvent], bool],
        extract_result: Callable[[TEvent], TResult],
    ):
        """
        Args:
            is_terminal: 判断事件是否为终止事件
            extract_result: 从终止事件中提取最终结果
        """
        self._is_terminal = is_terminal
        self._extract_result = extract_result
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._result_value: Optional[TResult] = None
        self._result_set = False
        self._result_event = asyncio.Event()
        self._ended = False
        self._events: List[TEvent] = []

    def push(self, event: TEvent) -> None:
        """推送一个事件到流中"""
        if self._ended:
            return

        self._events.append(event)
        self._queue.put_nowait(event)

        if self._is_terminal(event):
            result = self._extract_result(event)
            if not self._result_set:
                self._result_value = result
                self._result_set = True
                self._result_event.set()
            self._ended = True
            self._queue.put_nowait(_SENTINEL)

    def end(self, result: Optional[TResult] = None) -> None:
        """手动结束流"""
        if self._ended:
            return
        self._ended = True
        if not self._result_set:
            self._result_value = result  # type: ignore
            self._result_set = True
            self._result_event.set()
        self._queue.put_nowait(_SENTINEL)

    async def result(self) -> TResult:
        """等待并获取最终结果"""
        await self._result_event.wait()
        return self._result_value  # type: ignore

    @property
    def is_ended(self) -> bool:
        """流是否已结束"""
        return self._ended

    @property
    def events(self) -> List[TEvent]:
        """已推送的所有事件"""
        return self._events.copy()

    def __aiter__(self) -> AsyncIterator[TEvent]:
        return self._async_iter()

    async def _async_iter(self) -> AsyncIterator[TEvent]:
        """异步迭代所有事件"""
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                break
            yield item
