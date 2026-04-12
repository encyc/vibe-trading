"""
LLM 调用重试和限流处理器

提供智能重试、限流、超时处理等功能，特别针对流式输出场景优化。
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from .exceptions import (
    LLMConnectionError,
    LLMRateLimitError,
    LLMStreamError,
    LLMTimeoutError,
    RetryableError,
    MaxRetriesExceededError,
)
from .llm import Model, StreamResponse

logger = logging.getLogger(__name__)


class RetryStrategy(str, Enum):
    """重试策略"""
    FIXED = "fixed"  # 固定延迟
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性增长


@dataclass
class RetryConfig:
    """重试配置"""

    max_attempts: int = 3  # 最大重试次数
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 60.0  # 最大延迟（秒）
    exponential_base: float = 2.0  # 指数退避基数
    jitter: bool = True  # 是否添加随机抖动
    jitter_range: float = 0.1  # 抖动范围（±10%）

    # 可重试的异常类型
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        LLMConnectionError,
        LLMRateLimitError,
        LLMTimeoutError,
        LLMStreamError,
        asyncio.TimeoutError,
        ConnectionError,
        OSError,
    )

    # 不可重试的异常类型
    non_retryable_exceptions: Tuple[Type[Exception], ...] = ()


@dataclass
class RateLimitConfig:
    """限流配置"""

    max_concurrent: int = 3  # 最大并发请求数
    requests_per_minute: int = 100  # 每分钟最大请求数
    requests_per_hour: int = 1000  # 每小时最大请求数
    queue_timeout: float = 30.0  # 队列等待超时（秒）

    # 模型特定的限流配置
    model_limits: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def get_limit_for_model(self, model_id: str) -> Dict[str, int]:
        """获取特定模型的限流配置"""
        return self.model_limits.get(model_id, {})


@dataclass
class TimeoutConfig:
    """超时配置"""

    default_timeout: float = 120.0  # 默认超时（秒）
    stream_timeout: float = 300.0  # 流式请求超时（秒）
    connect_timeout: float = 10.0  # 连接超时（秒）
    read_timeout: float = 30.0  # 读取超时（秒）

    # 模型特定的超时配置
    model_timeouts: Dict[str, float] = field(default_factory=dict)

    def get_timeout_for_model(self, model_id: str, is_stream: bool = False) -> float:
        """获取特定模型的超时时间"""
        if model_id in self.model_timeouts:
            return self.model_timeouts[model_id]
        return self.stream_timeout if is_stream else self.default_timeout


class TokenBucket:
    """令牌桶限流器"""

    def __init__(self, rate: float, capacity: float):
        """
        初始化令牌桶

        Args:
            rate: 令牌生成速率（每秒）
            capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        获取令牌

        Args:
            tokens: 需要的令牌数
            timeout: 超时时间（秒）

        Returns:
            是否成功获取令牌
        """
        start_time = time.time()

        while True:
            async with self._lock:
                now = time.time()
                elapsed = now - self.last_update

                # 补充令牌
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # 检查超时
            if timeout is not None:
                if time.time() - start_time >= timeout:
                    return False

            # 等待一段时间后重试
            await asyncio.sleep(0.1)


class RetryHandler:
    """
    重试处理器

    提供智能重试功能，支持多种退避策略和异常处理。
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        初始化重试处理器

        Args:
            config: 重试配置
        """
        self.config = config or RetryConfig()
        self._attempt_counts: Dict[str, int] = {}

    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay * attempt
        else:  # EXPONENTIAL
            delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))

        # 应用最大延迟限制
        delay = min(delay, self.config.max_delay)

        # 添加随机抖动
        if self.config.jitter:
            import random
            jitter_amount = delay * self.config.jitter_range
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0, delay)

    def _is_retryable(self, error: Exception) -> bool:
        """判断异常是否可重试"""
        # 检查是否在不可重试列表中
        if self.config.non_retryable_exceptions:
            if isinstance(error, self.config.non_retryable_exceptions):
                return False

        # 检查是否在可重试列表中
        if self.config.retryable_exceptions:
            return isinstance(error, self.config.retryable_exceptions)

        # 默认情况下，所有异常都可重试
        return True

    async def execute_with_retry(
        self,
        func: Callable,
        operation_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        执行函数并在失败时重试

        Args:
            func: 要执行的异步函数
            operation_id: 操作ID（用于追踪）
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            MaxRetriesExceededError: 超过最大重试次数
            Exception: 不可重试的异常
        """
        if operation_id is None:
            operation_id = f"op_{id(func)}"

        last_error = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # 记录尝试
                self._attempt_counts[operation_id] = attempt

                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # 成功后清除计数
                if operation_id in self._attempt_counts:
                    del self._attempt_counts[operation_id]

                return result

            except Exception as e:
                last_error = e

                # 检查是否可重试
                if not self._is_retryable(e):
                    logger.warning(f"操作 {operation_id} 遇到不可重试的错误: {type(e).__name__}: {e}")
                    raise

                # 检查是否还有重试机会
                if attempt >= self.config.max_attempts:
                    logger.error(
                        f"操作 {operation_id} 达到最大重试次数 ({self.config.max_attempts}), "
                        f"最后错误: {type(e).__name__}: {e}"
                    )
                    raise MaxRetriesExceededError(
                        max_retries=self.config.max_attempts,
                        last_error=e,
                    ) from e

                # 计算延迟并等待
                delay = self._calculate_delay(attempt)
                logger.info(
                    f"操作 {operation_id} 第 {attempt} 次尝试失败: {type(e).__name__}: {e}. "
                    f"等待 {delay:.2f} 秒后重试..."
                )

                await asyncio.sleep(delay)

        # 理论上不会到达这里
        raise MaxRetriesExceededError(
            max_retries=self.config.max_attempts,
            last_error=last_error,
        )

    def get_attempt_count(self, operation_id: str) -> int:
        """获取操作的尝试次数"""
        return self._attempt_counts.get(operation_id, 0)

    def reset_attempt_count(self, operation_id: str) -> None:
        """重置操作的尝试次数"""
        if operation_id in self._attempt_counts:
            del self._attempt_counts[operation_id]


class LLMRateLimiter:
    """
    LLM 调用限流器

    提供多级限流控制：
    - 并发请求限制
    - 时间窗口请求限制
    - 模型特定限制
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        初始化限流器

        Args:
            config: 限流配置
        """
        self.config = config or RateLimitConfig()

        # 并发控制
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)

        # 令牌桶（分钟级）
        self._minute_bucket = TokenBucket(
            rate=self.config.requests_per_minute / 60.0,
            capacity=self.config.requests_per_minute,
        )

        # 令牌桶（小时级）
        self._hour_bucket = TokenBucket(
            rate=self.config.requests_per_hour / 3600.0,
            capacity=self.config.requests_per_hour,
        )

        # 模型特定的限流器
        self._model_limiters: Dict[str, TokenBucket] = {}
        self._model_semaphores: Dict[str, asyncio.Semaphore] = {}

    async def acquire(
        self,
        model_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        获取执行许可

        Args:
            model_id: 模型ID（用于模型特定限制）
            timeout: 超时时间（秒）

        Returns:
            是否成功获取许可
        """
        # 使用配置的队列超时
        if timeout is None:
            timeout = self.config.queue_timeout

        start_time = time.time()

        try:
            # 1. 并发限制
            semaphore = self._get_semaphore_for_model(model_id)
            if not await self._wait_for_semaphore(semaphore, timeout):
                raise LLMTimeoutError(timeout, "获取并发许可")

            # 2. 分钟级限制
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout <= 0:
                raise LLMTimeoutError(timeout, "获取分钟级许可")

            if not await self._minute_bucket.acquire(timeout=remaining_timeout):
                raise LLMRateLimitError("minute", retry_after=60)

            # 3. 小时级限制
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout <= 0:
                raise LLMTimeoutError(timeout, "获取小时级许可")

            if not await self._hour_bucket.acquire(timeout=remaining_timeout):
                raise LLMRateLimitError("hour", retry_after=3600)

            # 4. 模型特定限制
            if model_id:
                remaining_timeout = timeout - (time.time() - start_time)
                if remaining_timeout <= 0:
                    raise LLMTimeoutError(timeout, "获取模型特定许可")

                model_limiter = self._get_limiter_for_model(model_id)
                if not await model_limiter.acquire(timeout=remaining_timeout):
                    model_limit = self.config.get_limit_for_model(model_id)
                    raise LLMRateLimitError(
                        f"model_{model_id}",
                        retry_after=model_limit.get("retry_after", 60),
                    )

            return True

        except Exception:
            # 释放已获取的许可
            await self.release(model_id)
            raise

    async def release(self, model_id: Optional[str] = None) -> None:
        """释放执行许可"""
        if model_id:
            semaphore = self._model_semaphores.get(model_id)
            if semaphore:
                semaphore.release()
        else:
            self._semaphore.release()

    def _get_semaphore_for_model(self, model_id: Optional[str]) -> asyncio.Semaphore:
        """获取模型的信号量"""
        if model_id and model_id in self.config.model_limits:
            if model_id not in self._model_semaphores:
                limit = self.config.model_limits[model_id].get("max_concurrent", self.config.max_concurrent)
                self._model_semaphores[model_id] = asyncio.Semaphore(limit)
            return self._model_semaphores[model_id]
        return self._semaphore

    def _get_limiter_for_model(self, model_id: str) -> TokenBucket:
        """获取模型的限流器"""
        if model_id not in self._model_limiters:
            model_config = self.config.get_limit_for_model(model_id)
            if model_config:
                rate = model_config.get("requests_per_minute", self.config.requests_per_minute) / 60.0
                capacity = model_config.get("requests_per_minute", self.config.requests_per_minute)
            else:
                rate = self.config.requests_per_minute / 60.0
                capacity = self.config.requests_per_minute
            self._model_limiters[model_id] = TokenBucket(rate=rate, capacity=capacity)
        return self._model_limiters[model_id]

    async def _wait_for_semaphore(self, semaphore: asyncio.Semaphore, timeout: float) -> bool:
        """等待信号量"""
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def __aenter__(self):
        """上下文管理器入口"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        await self.release()


class StreamRetryHandler:
    """
    流式输出重试处理器

    针对流式输出的特殊处理：
    - 检测流中断
    - 支持部分结果的保存和恢复
    - 超时检测和重试
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """
        初始化流式重试处理器

        Args:
            retry_config: 重试配置
            timeout_config: 超时配置
        """
        self.retry_config = retry_config or RetryConfig()
        self.timeout_config = timeout_config or TimeoutConfig()
        self.retry_handler = RetryHandler(self.retry_config)

    async def execute_stream_with_retry(
        self,
        func: Callable,
        model: Model,
        context: Dict[str, Any],
        operation_id: Optional[str] = None,
        *args,
        **kwargs,
    ) -> StreamResponse:
        """
        执行流式函数并在失败时重试

        Args:
            func: 流式函数（返回 StreamResponse）
            model: LLM 模型
            context: 调用上下文
            operation_id: 操作ID
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            StreamResponse 对象

        Raises:
            MaxRetriesExceededError: 超过最大重试次数
        """
        # 设置超时
        timeout = kwargs.pop(
            "timeout",
            self.timeout_config.get_timeout_for_model(model.id, is_stream=True),
        )

        # 定义带超时的执行函数
        async def execute_with_timeout():
            try:
                return await asyncio.wait_for(func(model, context, *args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError as e:
                raise LLMTimeoutError(timeout, "流式请求") from e

        # 使用重试处理器执行
        return await self.retry_handler.execute_with_retry(
            execute_with_timeout,
            operation_id=operation_id,
        )


# =============================================================================
# 便捷函数
# =============================================================================

# 全局实例
_default_retry_handler: Optional[RetryHandler] = None
_default_rate_limiter: Optional[LLMRateLimiter] = None
_default_stream_handler: Optional[StreamRetryHandler] = None


def get_default_retry_handler() -> RetryHandler:
    """获取默认重试处理器"""
    global _default_retry_handler
    if _default_retry_handler is None:
        _default_retry_handler = RetryHandler()
    return _default_retry_handler


def get_default_rate_limiter() -> LLMRateLimiter:
    """获取默认限流器"""
    global _default_rate_limiter
    if _default_rate_limiter is None:
        _default_rate_limiter = LLMRateLimiter()
    return _default_rate_limiter


def get_default_stream_handler() -> StreamRetryHandler:
    """获取默认流式处理器"""
    global _default_stream_handler
    if _default_stream_handler is None:
        _default_stream_handler = StreamRetryHandler()
    return _default_stream_handler


async def execute_with_retry(
    func: Callable,
    operation_id: Optional[str] = None,
    *args,
    **kwargs,
) -> Any:
    """
    使用默认重试处理器执行函数

    Args:
        func: 要执行的函数
        operation_id: 操作ID
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        函数执行结果
    """
    handler = get_default_retry_handler()
    return await handler.execute_with_retry(func, operation_id, *args, **kwargs)
