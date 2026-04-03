"""
API限流管理器

管理API调用频率，避免超限和被封禁。
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """限流配置"""
    requests_per_minute: int = 1200    # 每分钟请求数
    requests_per_hour: int = 50000      # 每小时请求数
    requests_per_day: int = 100000      # 每天请求数
    burst_size: int = 100               # 突发请求数


@dataclass
class RateLimitStats:
    """限流统计"""
    total_requests: int = 0
    blocked_requests: int = 0
    wait_time_seconds: float = 0.0
    last_reset_time: Optional[datetime] = None


class RateLimiter:
    """
    API限流管理器

    使用令牌桶算法实现多级限流控制。
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        初始化限流器

        Args:
            config: 限流配置，默认为Binance标准配置
        """
        self.config = config or RateLimitConfig()

        # 令牌桶
        self.minute_tokens = self.config.requests_per_minute
        self.hour_tokens = self.config.requests_per_hour
        self.day_tokens = self.config.requests_per_day

        # 最后更新时间
        self.last_minute_update = datetime.now()
        self.last_hour_update = datetime.now()
        self.last_day_update = datetime.now()

        # 请求历史（用于精确控制）
        self.minute_requests: List[datetime] = []
        self.hour_requests: List[datetime] = []

        # 统计
        self.stats = RateLimitStats()

        # 锁
        self._lock = asyncio.Lock()

        logger.info(
            f"RateLimiter initialized: "
            f"{self.config.requests_per_minute}/min, "
            f"{self.config.requests_per_hour}/hour, "
            f"{self.config.requests_per_day}/day"
        )

    async def acquire(self, tokens: int = 1) -> bool:
        """
        获取请求许可（令牌）

        Args:
            tokens: 需要的令牌数量

        Returns:
            是否成功获取
        """
        async with self._lock:
            self._refill_tokens()

            # 检查各级限制
            if not self._check_minute_limit(tokens):
                wait_time = self._calculate_wait_time("minute")
                logger.warning(
                    f"Minute rate limit reached, waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                self.stats.wait_time_seconds += wait_time
                self._refill_tokens()

            if not self._check_hour_limit(tokens):
                wait_time = self._calculate_wait_time("hour")
                logger.warning(
                    f"Hour rate limit reached, waiting {wait_time:.1f}s"
                )
                await asyncio.sleep(wait_time)
                self.stats.wait_time_seconds += wait_time
                self._refill_tokens()

            if not self._check_day_limit(tokens):
                logger.error("Daily rate limit reached. Please wait until tomorrow.")
                self.stats.blocked_requests += tokens
                return False

            # 消耗令牌
            self.minute_tokens -= tokens
            self.hour_tokens -= tokens
            self.day_tokens -= tokens

            # 记录请求
            now = datetime.now()
            self.minute_requests.append(now)
            self.hour_requests.append(now)

            self.stats.total_requests += tokens

            return True

    async def acquire_with_timeout(
        self,
        tokens: int = 1,
        timeout: float = 60.0,
    ) -> bool:
        """
        获取请求许可（带超时）

        Args:
            tokens: 需要的令牌数量
            timeout: 超时时间

        Returns:
            是否成功获取
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < timeout:
            if await self.acquire(tokens):
                return True
            await asyncio.sleep(0.1)

        logger.warning(f"RateLimiter timeout after {timeout}s")
        return False

    def _refill_tokens(self):
        """补充令牌"""
        now = datetime.now()

        # 补充分钟令牌
        minute_delta = (now - self.last_minute_update).total_seconds()
        if minute_delta >= 60:
            self.minute_tokens = self.config.requests_per_minute
            self.last_minute_update = now
            self.minute_requests.clear()
        elif minute_delta > 0:
            # 按比例补充
            refill = int(minute_delta / 60 * self.config.requests_per_minute)
            self.minute_tokens = min(
                self.config.requests_per_minute,
                self.minute_tokens + refill
            )
            self.last_minute_update = now

        # 补充小时令牌
        hour_delta = (now - self.last_hour_update).total_seconds()
        if hour_delta >= 3600:
            self.hour_tokens = self.config.requests_per_hour
            self.last_hour_update = now
            self.hour_requests.clear()
        elif hour_delta > 0:
            refill = int(hour_delta / 3600 * self.config.requests_per_hour)
            self.hour_tokens = min(
                self.config.requests_per_hour,
                self.hour_tokens + refill
            )
            self.last_hour_update = now

        # 补充天令牌
        day_delta = (now - self.last_day_update).total_seconds()
        if day_delta >= 86400:
            self.day_tokens = self.config.requests_per_day
            self.last_day_update = now
        elif day_delta > 0:
            refill = int(day_delta / 86400 * self.config.requests_per_day)
            self.day_tokens = min(
                self.config.requests_per_day,
                self.day_tokens + refill
            )
            self.last_day_update = now

        # 清理过期请求记录
        self._cleanup_old_requests()

    def _cleanup_old_requests(self):
        """清理过期的请求记录"""
        now = datetime.now()
        cutoff_minute = now - timedelta(minutes=1)
        cutoff_hour = now - timedelta(hours=1)

        self.minute_requests = [
            r for r in self.minute_requests if r > cutoff_minute
        ]
        self.hour_requests = [
            r for r in self.hour_requests if r > cutoff_hour
        ]

    def _check_minute_limit(self, tokens: int) -> bool:
        """检查分钟限制"""
        return self.minute_tokens >= tokens

    def _check_hour_limit(self, tokens: int) -> bool:
        """检查小时限制"""
        return self.hour_tokens >= tokens

    def _check_day_limit(self, tokens: int) -> bool:
        """检查天限制"""
        return self.day_tokens >= tokens

    def _calculate_wait_time(self, period: str) -> float:
        """计算等待时间"""
        now = datetime.now()

        if period == "minute":
            if self.minute_requests:
                # 计算到最旧请求满1分钟的时间
                oldest = min(self.minute_requests)
                return 60.0 - (now - oldest).total_seconds()
            return 1.0

        elif period == "hour":
            if self.hour_requests:
                oldest = min(self.hour_requests)
                return 3600.0 - (now - oldest).total_seconds()
            return 60.0

        return 1.0

    def get_remaining_tokens(self) -> Dict[str, int]:
        """获取剩余令牌数"""
        self._refill_tokens()
        return {
            "minute": int(self.minute_tokens),
            "hour": int(self.hour_tokens),
            "day": int(self.day_tokens),
        }

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_requests": self.stats.total_requests,
            "blocked_requests": self.stats.blocked_requests,
            "wait_time_seconds": round(self.stats.wait_time_seconds, 2),
            "remaining_tokens": self.get_remaining_tokens(),
            "utilization": {
                "minute": 1 - (self.minute_tokens / self.config.requests_per_minute),
                "hour": 1 - (self.hour_tokens / self.config.requests_per_hour),
                "day": 1 - (self.day_tokens / self.config.requests_per_day),
            }
        }


class MultiEndpointRateLimiter:
    """
    多端点限流管理器

    为不同的API端点分别管理限流。
    """

    def __init__(self):
        self.limiters: Dict[str, RateLimiter] = {}
        self.endpoint_configs: Dict[str, RateLimitConfig] = {
            # Binance REST API
            "binance_rest": RateLimitConfig(
                requests_per_minute=2400,
                requests_per_hour=100000,
                requests_per_day=200000,
            ),
            # Binance WebSocket
            "binance_ws": RateLimitConfig(
                requests_per_minute=300,  # 5 per second
                requests_per_hour=18000,
                requests_per_day=432000,
            ),
            # CryptoCompare
            "cryptocompare": RateLimitConfig(
                requests_per_minute=30,  # 免费版限制
                requests_per_hour=1000,
                requests_per_day=10000,
            ),
            # Alternative.me (Fear & Greed)
            "alternative_me": RateLimitConfig(
                requests_per_minute=10,
                requests_per_hour=100,
                requests_per_day=1000,
            ),
            # 默认
            "default": RateLimitConfig(),
        }

    def get_limiter(self, endpoint: str) -> RateLimiter:
        """获取指定端点的限流器"""
        if endpoint not in self.limiters:
            config = self.endpoint_configs.get(
                endpoint,
                self.endpoint_configs["default"]
            )
            self.limiters[endpoint] = RateLimiter(config)

        return self.limiters[endpoint]

    async def acquire(
        self,
        endpoint: str,
        tokens: int = 1,
        timeout: float = 60.0,
    ) -> bool:
        """获取请求许可"""
        limiter = self.get_limiter(endpoint)
        return await limiter.acquire_with_timeout(tokens, timeout)

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有端点的统计信息"""
        return {
            endpoint: limiter.get_stats()
            for endpoint, limiter in self.limiters.items()
        }


# 预配置的限流器实例
_binance_rest_limiter = None
_binance_ws_limiter = None
_multi_limiter = MultiEndpointRateLimiter()


def get_binance_rest_limiter() -> RateLimiter:
    """获取Binance REST API限流器"""
    global _binance_rest_limiter
    if _binance_rest_limiter is None:
        config = RateLimitConfig(
            requests_per_minute=2400,
            requests_per_hour=100000,
        )
        _binance_rest_limiter = RateLimiter(config)
    return _binance_rest_limiter


def get_binance_ws_limiter() -> RateLimiter:
    """获取Binance WebSocket限流器"""
    global _binance_ws_limiter
    if _binance_ws_limiter is None:
        config = RateLimitConfig(
            requests_per_minute=300,  # 5 per second
            requests_per_hour=18000,
        )
        _binance_ws_limiter = RateLimiter(config)
    return _binance_ws_limiter


def get_multi_endpoint_limiter() -> MultiEndpointRateLimiter:
    """获取多端点限流器"""
    return _multi_limiter


# 上下文管理器
class RateLimitContext:
    """限流上下文管理器"""

    def __init__(
        self,
        limiter: RateLimiter,
        tokens: int = 1,
        timeout: float = 60.0,
    ):
        self.limiter = limiter
        self.tokens = tokens
        self.timeout = timeout
        self.acquired = False

    async def __aenter__(self):
        self.acquired = await self.limiter.acquire_with_timeout(
            self.tokens,
            self.timeout
        )
        if not self.acquired:
            raise RuntimeError("Failed to acquire rate limit token")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# 使用示例
async def example_usage():
    """使用示例"""

    # 基本使用
    limiter = RateLimiter()
    success = await limiter.acquire()
    if success:
        # 执行API请求
        pass

    # 多端点使用
    multi_limiter = get_multi_endpoint_limiter()
    await multi_limiter.acquire("binance_rest")
    await multi_limiter.acquire("cryptocompare")

    # 上下文管理器
    async with RateLimitContext(limiter, tokens=1):
        # 执行API请求
        pass

    # 获取统计
    stats = limiter.get_stats()
    print(f"Remaining tokens: {stats['remaining_tokens']}")
