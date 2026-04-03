"""
缓存管理

为API调用和计算结果提供缓存支持。
"""
import asyncio
import hashlib
import json
import logging
import pickle
import time
from datetime import datetime, timedelta
from functools import wraps, lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheEntry:
    """缓存条目"""

    def __init__(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ):
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = time.time()
        self.metadata = metadata or {}
        self.hit_count = 0
        self.last_access = self.created_at

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl

    def touch(self):
        """更新访问时间"""
        self.last_access = time.time()
        self.hit_count += 1


class MemoryCache:
    """
    内存缓存

    简单高效的内存缓存实现。
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        """
        初始化内存缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()

        # 统计
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        async with self._lock:
            entry = self.cache.get(key)

            if entry is None:
                self.misses += 1
                return None

            if entry.is_expired():
                del self.cache[key]
                self.misses += 1
                return None

            entry.touch()
            self.hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ):
        """设置缓存值"""
        async with self._lock:
            # 检查是否超过最大大小
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()

            ttl = ttl or self.default_ttl
            self.cache[key] = CacheEntry(key, value, ttl, metadata)

    async def delete(self, key: str):
        """删除缓存值"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]

    async def clear(self):
        """清空缓存"""
        async with self._lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0

    async def invalidate_pattern(self, pattern: str):
        """按模式失效缓存"""
        async with self._lock:
            keys_to_delete = [
                k for k in self.cache.keys()
                if pattern in k
            ]
            for key in keys_to_delete:
                del self.cache[key]

    def _evict_lru(self):
        """淘汰最久未使用的条目"""
        if not self.cache:
            return

        # 找到最久未访问的条目
        lru_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].last_access
        )
        del self.cache[lru_key]

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }


class FileCache:
    """
    文件缓存

    持久化缓存到文件系统。
    """

    def __init__(
        self,
        cache_dir: str = "./cache",
        default_ttl: float = 3600.0,
    ):
        """
        初始化文件缓存

        Args:
            cache_dir: 缓存目录
            default_ttl: 默认过期时间（秒）
        """
        self.cache_dir = Path(cache_dir)
        self.default_ttl = default_ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 统计
        self.hits = 0
        self.misses = 0

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用哈希避免文件名过长
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            self.misses += 1
            return None

        try:
            with open(cache_path, "rb") as f:
                entry = pickle.load(f)

            if entry.is_expired():
                cache_path.unlink()
                self.misses += 1
                return None

            entry.touch()
            self.hits += 1

            # 更新磁盘上的访问时间
            with open(cache_path, "wb") as f:
                pickle.dump(entry, f)

            return entry.value

        except (pickle.PickleError, EOFError, OSError) as e:
            logger.warning(f"Failed to load cache {key}: {e}")
            self.misses += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ):
        """设置缓存值"""
        cache_path = self._get_cache_path(key)
        ttl = ttl or self.default_ttl

        entry = CacheEntry(key, value, ttl, metadata)

        try:
            with open(cache_path, "wb") as f:
                pickle.dump(entry, f)
        except (OSError, pickle.PickleError) as e:
            logger.error(f"Failed to save cache {key}: {e}")

    async def delete(self, key: str):
        """删除缓存值"""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()

    async def clear(self):
        """清空缓存"""
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                cache_file.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {e}")

        self.hits = 0
        self.misses = 0

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        cache_files = list(self.cache_dir.glob("*.cache"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "cache_dir": str(self.cache_dir),
            "file_count": len(cache_files),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }


class HybridCache:
    """
    混合缓存

    结合内存缓存和文件缓存的优点。
    """

    def __init__(
        self,
        memory_max_size: int = 1000,
        memory_ttl: float = 300.0,
        file_cache_dir: str = "./cache",
        file_ttl: float = 3600.0,
    ):
        """
        初始化混合缓存

        Args:
            memory_max_size: 内存缓存最大大小
            memory_ttl: 内存缓存TTL
            file_cache_dir: 文件缓存目录
            file_ttl: 文件缓存TTL
        """
        self.memory = MemoryCache(max_size=memory_max_size, default_ttl=memory_ttl)
        self.file = FileCache(cache_dir=file_cache_dir, default_ttl=file_ttl)

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值（先内存后文件）"""
        # 先查内存
        value = await self.memory.get(key)
        if value is not None:
            return value

        # 再查文件
        value = await self.file.get(key)
        if value is not None:
            # 回填内存缓存
            await self.memory.set(key, value)

        return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ):
        """设置缓存值（同时写内存和文件）"""
        await self.memory.set(key, value, ttl, metadata)
        await self.file.set(key, value, ttl, metadata)

    async def delete(self, key: str):
        """删除缓存值"""
        await self.memory.delete(key)
        await self.file.delete(key)

    async def clear(self):
        """清空缓存"""
        await self.memory.clear()
        await self.file.clear()

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            "memory": self.memory.get_stats(),
            "file": self.file.get_stats(),
        }


# 全局缓存实例
_global_cache: Optional[HybridCache] = None


def get_global_cache() -> HybridCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = HybridCache()
    return _global_cache


# 装饰器
def cached(
    ttl: float = 300.0,
    key_prefix: str = "",
    cache_instance: Optional[HybridCache] = None,
):
    """
    缓存装饰器

    Args:
        ttl: 过期时间（秒）
        key_prefix: 缓存键前缀
        cache_instance: 缓存实例（默认使用全局缓存）

    使用示例:
        @cached(ttl=600, key_prefix="technical")
        async def get_indicators(symbol: str, interval: str):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # 生成缓存键
            cache = cache_instance or get_global_cache()

            # 将参数序列化为键
            key_parts = [key_prefix, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # 尝试获取缓存
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 存入缓存
            await cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def sync_cached(
    ttl: float = 300.0,
    key_prefix: str = "",
    maxsize: int = 128,
):
    """
    同步缓存装饰器（使用lru_cache）

    Args:
        ttl: 过期时间（仅用于内存缓存）
        key_prefix: 缓存键前缀
        maxsize: LRU缓存大小

    使用示例:
        @sync_cached(ttl=600, key_prefix="calc")
        def calculate_indicators(data):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_cached = lru_cache(maxsize=maxsize)(func)

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # 对于同步函数，使用lru_cache
            # 注意：lru_cache不支持TTL，需要手动清理
            return func_cached(*args, **kwargs)

        # 添加缓存清理方法
        wrapper.cache_clear = func_cached.cache_clear
        wrapper.cache_info = func_cached.cache_info

        return wrapper

    return decorator


class CachedTechnicalAnalysis:
    """
    缓存的技术分析

    为技术指标计算提供缓存支持。
    """

    def __init__(self, cache: Optional[HybridCache] = None):
        self.cache = cache or get_global_cache()
        self._local_cache: Dict[str, Tuple[float, Any]] = {}

    async def get_indicators(
        self,
        symbol: str,
        interval: str,
        timestamp: int,
        calculator_func: Callable,
    ) -> Optional[Dict]:
        """
        获取技术指标（带缓存）

        Args:
            symbol: 交易品种
            interval: K线周期
            timestamp: 时间戳
            calculator_func: 计算函数

        Returns:
            技术指标字典
        """
        cache_key = f"indicators:{symbol}:{interval}:{timestamp}"

        # 检查本地缓存（最快）
        if cache_key in self._local_cache:
            cached_time, cached_value = self._local_cache[cache_key]
            if time.time() - cached_time < 60:  # 本地缓存1分钟
                return cached_value

        # 检查全局缓存
        value = await self.cache.get(cache_key)
        if value is not None:
            self._local_cache[cache_key] = (time.time(), value)
            return value

        # 计算新值
        result = await calculator_func()

        # 存入缓存
        await self.cache.set(cache_key, result, ttl=300.0)
        self._local_cache[cache_key] = (time.time(), result)

        return result

    def invalidate_symbol(self, symbol: str):
        """失效特定品种的缓存"""
        asyncio.create_task(self.cache.invalidate_pattern(f"indicators:{symbol}"))
        self._local_cache.clear()


# 使用示例
async def example_usage():
    """使用示例"""

    # 全局缓存
    cache = get_global_cache()

    # 设置缓存
    await cache.set("test_key", {"data": "value"}, ttl=60.0)

    # 获取缓存
    value = await cache.get("test_key")
    print(f"Cached value: {value}")

    # 获取统计
    stats = cache.get_stats()
    print(f"Cache stats: {stats}")

    # 使用装饰器
    @cached(ttl=600, key_prefix="api_call")
    async def fetch_klines(symbol: str, interval: str):
        # 模拟API调用
        await asyncio.sleep(0.1)
        return {"symbol": symbol, "interval": interval, "data": []}

    # 第一次调用 - 会执行
    result1 = await fetch_klines("BTCUSDT", "5m")

    # 第二次调用 - 从缓存获取
    result2 = await fetch_klines("BTCUSDT", "5m")


if __name__ == "__main__":
    asyncio.run(example_usage())
