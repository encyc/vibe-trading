"""
增强的 LLM 调用接口

集成重试、限流、超时等功能的统一接口。
"""
import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from .llm import Model, StreamResponse, stream_simple
from .retry_handler import (
    RetryConfig,
    RateLimitConfig,
    TimeoutConfig,
    LLMRateLimiter,
    StreamRetryHandler,
    get_default_rate_limiter,
    get_default_stream_handler,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 增强的 stream_simple
# =============================================================================


async def stream_simple_with_retry(
    model: Model,
    context: Dict[str, Any],
    *,
    retry_config: Optional[RetryConfig] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
    timeout_config: Optional[TimeoutConfig] = None,
    operation_id: Optional[str] = None,
    **options,
) -> StreamResponse:
    """
    带重试和限流的 LLM 流式调用

    Args:
        model: LLM 模型
        context: 上下文字典 (system_prompt, messages, tools)
        retry_config: 重试配置
        rate_limit_config: 限流配置
        timeout_config: 超时配置
        operation_id: 操作ID（用于追踪和日志）
        **options: 额外选项

    Returns:
        StreamResponse 包装器

    Example:
        ```python
        from pi_ai import stream_simple_with_retry, get_model

        model = get_model("openai", "gpt-4o")

        response = await stream_simple_with_retry(
            model,
            {
                "system_prompt": "你是一个助手",
                "messages": [{"role": "user", "content": "你好"}],
            },
            operation_id="chat_001",
        )

        async for event in response:
            print(event)
        ```
    """
    # 初始化处理器
    rate_limiter = get_default_rate_limiter()
    if rate_limit_config:
        rate_limiter = LLMRateLimiter(rate_limit_config)

    stream_handler = get_default_stream_handler()
    if retry_config or timeout_config:
        stream_handler = StreamRetryHandler(
            retry_config=retry_config,
            timeout_config=timeout_config,
        )

    # 获取执行许可
    logger.debug(f"[{operation_id}] 等待限流许可...")
    await rate_limiter.acquire(model_id=model.id)
    logger.debug(f"[{operation_id}] 获得执行许可")

    try:
        # 执行流式调用（带重试）
        response = await stream_handler.execute_stream_with_retry(
            func=stream_simple,
            model=model,
            context=context,
            operation_id=operation_id,
            **options,
        )

        return response

    except Exception as e:
        logger.error(f"[{operation_id}] 调用失败: {type(e).__name__}: {e}")
        raise

    finally:
        # 释放许可
        await rate_limiter.release(model_id=model.id)
        logger.debug(f"[{operation_id}] 释放执行许可")


# =============================================================================
# 批量调用接口
# =============================================================================


async def batch_call_with_retry(
    calls: list[tuple[Model, Dict[str, Any], dict]],
    *,
    retry_config: Optional[RetryConfig] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
    timeout_config: Optional[TimeoutConfig] = None,
    max_concurrent: int = 3,
) -> list[StreamResponse]:
    """
    批量 LLM 调用（带并发控制）

    Args:
        calls: 调用列表，每个元素是 (model, context, options) 元组
        retry_config: 重试配置
        rate_limit_config: 限流配置
        timeout_config: 超时配置
        max_concurrent: 最大并发数

    Returns:
        StreamResponse 列表

    Example:
        ```python
        calls = [
            (model1, {"system_prompt": "...", "messages": [...]}, {}),
            (model2, {"system_prompt": "...", "messages": [...]}, {}),
        ]

        responses = await batch_call_with_retry(calls, max_concurrent=2)
        ```
    """
    # 创建信号量
    semaphore = asyncio.Semaphore(max_concurrent)

    async def call_with_semaphore(index: int, call: tuple) -> tuple[int, StreamResponse]:
        async with semaphore:
            model, context, options = call
            operation_id = f"batch_{index}"

            response = await stream_simple_with_retry(
                model,
                context,
                retry_config=retry_config,
                rate_limit_config=rate_limit_config,
                timeout_config=timeout_config,
                operation_id=operation_id,
                **options,
            )

            return index, response

    # 创建所有任务
    tasks = [
        asyncio.create_task(call_with_semaphore(i, call))
        for i, call in enumerate(calls)
    ]

    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理结果
    responses: list[StreamResponse] = [None] * len(calls)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"批量调用失败: {result}")
            # 可以选择在这里抛出异常，或者继续处理其他结果
            raise result
        else:
            index, response = result
            responses[index] = response

    return responses


# =============================================================================
# 工具函数
# =============================================================================


async def safe_stream_iterate(
    response: StreamResponse,
    operation_id: Optional[str] = None,
    timeout: float = 300.0,
) -> AsyncGenerator:
    """
    安全地迭代流式响应

    处理超时和异常，确保不会因为流中断而hang住。

    Args:
        response: StreamResponse 对象
        operation_id: 操作ID
        timeout: 单个事件超时时间

    Yields:
        流事件
    """
    try:
        iterator = response.__aiter__()

        while True:
            try:
                # 使用超时等待下一个事件
                event = await asyncio.wait_for(
                    iterator.__anext__(),
                    timeout=timeout,
                )
                yield event

            except StopAsyncIteration:
                logger.debug(f"[{operation_id}] 流迭代正常结束")
                break

            except asyncio.TimeoutError:
                logger.warning(f"[{operation_id}] 流事件超时，强制结束")
                # 取消响应
                if hasattr(response, '_cancel'):
                    await response._cancel()
                break

    except Exception as e:
        logger.error(f"[{operation_id}] 流迭代异常: {type(e).__name__}: {e}")
        raise


# 导出
__all__ = [
    "stream_simple_with_retry",
    "batch_call_with_retry",
    "safe_stream_iterate",
]
