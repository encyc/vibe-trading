"""
Message Channel - 消息通道/事件总线

连接所有Subagent和Prime Agent的异步消息通道。
支持优先级队列、消息去重、背压控制和统计监控。
"""
import asyncio
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from heapq import heappop, heappush
from typing import Dict, List, Optional, Set

from pi_logger import get_logger

from vibe_trading.agents.messaging import AgentMessage, MessageType
from vibe_trading.prime.models import MessagePriority, MessageStats

logger = get_logger(__name__)


@dataclass(order=True)
class PriorityMessage:
    """优先级消息包装器"""
    priority: int  # 优先级（数字越小优先级越高）
    timestamp: float  # 时间戳（用于同优先级排序）
    message: AgentMessage = field(compare=False)

    @classmethod
    def create(cls, message: AgentMessage, priority: MessagePriority) -> "PriorityMessage":
        """创建优先级消息"""
        priority_map = {
            MessagePriority.CRITICAL: 0,
            MessagePriority.HIGH: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.LOW: 3,
        }
        return cls(
            priority=priority_map[priority],
            timestamp=datetime.now().timestamp(),
            message=message,
        )


class MessageChannel:
    """
    消息通道 - 事件总线

    特性：
    - 优先级队列（紧急消息优先）
    - 消息去重
    - 背压控制（防止消息堆积）
    - 事件订阅和过滤
    - 统计和监控
    """

    def __init__(
        self,
        maxsize: int = 1000,
        enable_dedup: bool = True,
        dedup_window: float = 10.0,
        enable_stats: bool = True,
    ):
        """
        初始化消息通道

        Args:
            maxsize: 队列最大大小
            enable_dedup: 是否启用消息去重
            dedup_window: 去重时间窗口（秒）
            enable_stats: 是否启用统计
        """
        self.maxsize = maxsize
        self.enable_dedup = enable_dedup
        self.dedup_window = dedup_window
        self.enable_stats = enable_stats

        # 优先级队列
        self._queue: List[PriorityMessage] = []
        self._queue_lock = asyncio.Lock()

        # 消息去重
        self._seen_messages: Dict[str, float] = {}  # message_hash -> timestamp
        self._dedup_lock = asyncio.Lock()

        # 事件订阅
        self._subscriptions: Dict[str, Set[MessageType]] = defaultdict(set)
        self._subscriptions_lock = asyncio.Lock()

        # 统计
        self.stats = MessageStats() if enable_stats else None

        # 信号量（用于背压控制）
        self._semaphore = asyncio.Semaphore(maxsize)
        self._get_event = asyncio.Event()

        logger.info(
            f"MessageChannel initialized: maxsize={maxsize}, "
            f"dedup={enable_dedup}, stats={enable_stats}"
        )

    async def put(
        self,
        message: AgentMessage,
        priority: MessagePriority = MessagePriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        发送消息到channel

        Args:
            message: 消息
            priority: 优先级
            timeout: 超时时间（None表示无限等待）

        Returns:
            是否成功发送
        """
        try:
            # 获取信号量（背压控制）
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=timeout
            )

            # 消息去重检查
            if self.enable_dedup:
                message_hash = self._compute_hash(message)
                async with self._dedup_lock:
                    if await self._is_duplicate(message_hash):
                        logger.debug(f"Duplicate message discarded: {message.message_id}")
                        self._semaphore.release()
                        return False

                    # 记录消息
                    self._seen_messages[message_hash] = datetime.now().timestamp()

            # 添加到优先级队列
            priority_msg = PriorityMessage.create(message, priority)

            async with self._queue_lock:
                if len(self._queue) >= self.maxsize:
                    # 队列已满，移除最旧的低优先级消息
                    self._remove_oldest_low_priority()
                heappush(self._queue, priority_msg)

            # 通知有新消息
            self._get_event.set()

            logger.debug(
                f"Message put: {message.message_type.value} from {message.sender}, "
                f"priority={priority.value}"
            )

            return True

        except asyncio.TimeoutError:
            logger.warning(f"Message put timeout: {message.message_id}")
            return False
        except Exception as e:
            logger.error(f"Error putting message: {e}")
            return False

    async def get(
        self,
        timeout: Optional[float] = None,
        message_types: Optional[List[MessageType]] = None,
        senders: Optional[List[str]] = None,
    ) -> Optional[AgentMessage]:
        """
        从channel获取消息

        Args:
            timeout: 超时时间（None表示无限等待）
            message_types: 消息类型过滤（None表示不过滤）
            senders: 发送者过滤（None表示不过滤）

        Returns:
            消息或None（超时）
        """
        try:
            while True:
                # 等待消息
                try:
                    await asyncio.wait_for(
                        self._get_event.wait(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    return None

                self._get_event.clear()

                # 从队列获取消息
                async with self._queue_lock:
                    if not self._queue:
                        continue

                    priority_msg = heappop(self._queue)
                    message = priority_msg.message

                # 释放信号量
                self._semaphore.release()

                # 过滤检查
                if message_types and message.message_type not in message_types:
                    # 不匹配，放回队列并继续
                    await self.put(message)
                    continue

                if senders and message.sender not in senders:
                    # 不匹配，放回队列并继续
                    await self.put(message)
                    continue

                # 清理过期去重记录
                await self._cleanup_dedup()

                # 记录统计
                if self.stats:
                    start_time = datetime.now().timestamp()
                    processing_time = datetime.now().timestamp() - start_time
                    self.stats.record_message(message, processing_time)

                return message

        except Exception as e:
            logger.error(f"Error getting message: {e}")
            return None

    async def subscribe(
        self,
        agent_id: str,
        message_types: List[MessageType],
    ) -> None:
        """
        订阅特定类型的消息

        Args:
            agent_id: 订阅者ID
            message_types: 要订阅的消息类型列表
        """
        async with self._subscriptions_lock:
            self._subscriptions[agent_id].update(message_types)

        logger.info(f"Agent {agent_id} subscribed to: {[mt.value for mt in message_types]}")

    async def unsubscribe(
        self,
        agent_id: str,
        message_types: Optional[List[MessageType]] = None,
    ) -> None:
        """
        取消订阅

        Args:
            agent_id: 订阅者ID
            message_types: 要取消的消息类型（None表示取消所有）
        """
        async with self._subscriptions_lock:
            if message_types is None:
                # 取消所有订阅
                self._subscriptions.pop(agent_id, None)
            else:
                # 取消特定订阅
                if agent_id in self._subscriptions:
                    self._subscriptions[agent_id].difference_update(message_types)

        logger.info(f"Agent {agent_id} unsubscribed from: {message_types}")

    def get_subscribers(self, message_type: MessageType) -> Set[str]:
        """获取订阅了特定消息类型的订阅者"""
        return {
            agent_id
            for agent_id, types in self._subscriptions.items()
            if message_type in types
        }

    async def size(self) -> int:
        """获取当前队列大小"""
        async with self._queue_lock:
            return len(self._queue)

    async def clear(self) -> None:
        """清空队列"""
        async with self._queue_lock:
            self._queue.clear()

        logger.info("Message channel cleared")

    async def get_stats(self) -> Optional[MessageStats]:
        """获取统计信息"""
        return self.stats

    async def reset_stats(self) -> None:
        """重置统计信息"""
        if self.stats:
            self.stats = MessageStats()

        logger.debug("Message channel stats reset")

    def _compute_hash(self, message: AgentMessage) -> str:
        """计算消息哈希（用于去重）"""
        # 使用关键字段计算哈希
        hash_input = f"{message.sender}_{message.message_type.value}_{message.content}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    async def _is_duplicate(self, message_hash: str) -> bool:
        """检查消息是否重复"""
        if message_hash not in self._seen_messages:
            return False

        # 检查是否在去重窗口内
        timestamp = self._seen_messages[message_hash]
        if datetime.now().timestamp() - timestamp > self.dedup_window:
            # 过期了，删除并返回非重复
            del self._seen_messages[message_hash]
            return False

        return True

    async def _cleanup_dedup(self) -> None:
        """清理过期的去重记录"""
        now = datetime.now().timestamp()
        async with self._dedup_lock:
            expired = [
                hash_key
                for hash_key, timestamp in self._seen_messages.items()
                if now - timestamp > self.dedup_window
            ]
            for hash_key in expired:
                del self._seen_messages[hash_key]

    def _remove_oldest_low_priority(self) -> None:
        """移除最旧的低优先级消息"""
        if not self._queue:
            return

        # 找到最低优先级的消息
        # 注意：heappush保证队列顶部是优先级最高的
        # 我们需要找优先级最低的（通常在队列末尾）
        # 简化处理：移除最后一个元素
        if self._queue:
            # 按优先级和时间戳排序，移除最后一个
            self._queue.sort()
            removed = self._queue.pop()
            logger.debug(
                f"Removed low priority message: "
                f"{removed.message.message_type.value} from {removed.message.sender}"
            )
