"""
进度追踪器

实时追踪回测进度并提供统计信息。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from pi_logger import get_logger

logger = get_logger(__name__)


class BacktestStatus(str, Enum):
    """回测状态"""
    PENDING = "pending"  # 等待开始
    INITIALIZING = "initializing"  # 初始化中
    RUNNING = "running"  # 运行中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class ProgressUpdate:
    """进度更新信息"""
    task_id: str
    status: BacktestStatus
    current_kline: int
    total_klines: int
    current_time: Optional[datetime] = None

    # 统计信息
    current_equity: float = 0.0
    total_trades: int = 0
    open_trades: int = 0
    total_return: float = 0.0

    # 性能指标
    llm_calls: int = 0
    llm_cache_hits: int = 0
    cache_hit_rate: float = 0.0

    # 预估
    estimated_remaining_seconds: Optional[float] = None

    # 错误信息
    error_message: Optional[str] = None

    @property
    def progress_percentage(self) -> float:
        """进度百分比"""
        if self.total_klines > 0:
            return (self.current_kline / self.total_klines) * 100
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "current_kline": self.current_kline,
            "total_klines": self.total_klines,
            "progress_percentage": round(self.progress_percentage, 2),
            "current_time": self.current_time.isoformat() if self.current_time else None,
            "current_equity": round(self.current_equity, 2),
            "total_trades": self.total_trades,
            "open_trades": self.open_trades,
            "total_return": round(self.total_return, 4),
            "llm_calls": self.llm_calls,
            "llm_cache_hits": self.llm_cache_hits,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds) if self.estimated_remaining_seconds else None,
            "error_message": self.error_message,
        }


class ProgressTracker:
    """
    进度追踪器

    追踪回测进度并提供回调机制。
    """

    def __init__(self, task_id: str):
        """
        初始化进度追踪器

        Args:
            task_id: 任务ID
        """
        self.task_id = task_id
        self.status = BacktestStatus.PENDING

        # 进度信息
        self.current_kline = 0
        self.total_klines = 0
        self.current_time: Optional[datetime] = None

        # 统计信息
        self.current_equity = 0.0
        self.total_trades = 0
        self.open_trades = 0
        self.total_return = 0.0

        # LLM统计
        self.llm_calls = 0
        self.llm_cache_hits = 0
        self.cache_hit_rate = 0.0

        # 时间追踪
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # 错误信息
        self.error_message: Optional[str] = None

        # 回调函数
        self._callbacks: List[Callable[[ProgressUpdate], None]] = []

        # 预估计算
        self._progress_history: List[tuple[datetime, int]] = []

    def add_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """
        添加进度更新回调

        Args:
            callback: 回调函数，接收ProgressUpdate参数
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ProgressUpdate], None]) -> None:
        """
        移除进度更新回调

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """通知所有回调函数"""
        update = self.get_progress_update()
        for callback in self._callbacks:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}", exc_info=True)

    def start(self, total_klines: int) -> None:
        """
        开始回测

        Args:
            total_klines: 总K线数量
        """
        self.status = BacktestStatus.RUNNING
        self.total_klines = total_klines
        self.current_kline = 0
        self.started_at = datetime.now()
        self._progress_history = []
        self._notify_callbacks()

    def update(
        self,
        current_kline: int,
        current_equity: float = 0.0,
        total_trades: int = 0,
        open_trades: int = 0,
        llm_calls: int = 0,
        llm_cache_hits: int = 0,
        current_time: Optional[datetime] = None,
    ) -> None:
        """
        更新进度

        Args:
            current_kline: 当前K线索引
            current_equity: 当前权益
            total_trades: 总交易数
            open_trades: 开放交易数
            llm_calls: LLM调用次数
            llm_cache_hits: LLM缓存命中次数
            current_time: 当前K线时间
        """
        self.current_kline = current_kline
        self.current_equity = current_equity
        self.total_trades = total_trades
        self.open_trades = open_trades
        self.llm_calls = llm_calls
        self.llm_cache_hits = llm_cache_hits

        if llm_calls > 0:
            self.cache_hit_rate = llm_cache_hits / llm_calls

        self.current_time = current_time

        # 记录进度历史（用于估算剩余时间）
        self._progress_history.append((datetime.now(), current_kline))

        # 定期通知回调（每100根K线或每完成10%）
        if current_kline % 100 == 0 or int(self.progress_percentage) % 10 == 0:
            self._notify_callbacks()

    def complete(self) -> None:
        """完成回测"""
        self.status = BacktestStatus.COMPLETED
        self.completed_at = datetime.now()
        self.current_kline = self.total_klines
        self._notify_callbacks()

    def fail(self, error_message: str) -> None:
        """
        标记回测失败

        Args:
            error_message: 错误信息
        """
        self.status = BacktestStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()
        self._notify_callbacks()

    def pause(self) -> None:
        """暂停回测"""
        self.status = BacktestStatus.PAUSED
        self._notify_callbacks()

    def resume(self) -> None:
        """恢复回测"""
        if self.status == BacktestStatus.PAUSED:
            self.status = BacktestStatus.RUNNING
            self._notify_callbacks()

    def cancel(self) -> None:
        """取消回测"""
        self.status = BacktestStatus.CANCELLED
        self.completed_at = datetime.now()
        self._notify_callbacks()

    def get_progress_update(self) -> ProgressUpdate:
        """
        获取当前进度更新

        Returns:
            ProgressUpdate对象
        """
        return ProgressUpdate(
            task_id=self.task_id,
            status=self.status,
            current_kline=self.current_kline,
            total_klines=self.total_klines,
            current_time=self.current_time,
            current_equity=self.current_equity,
            total_trades=self.total_trades,
            open_trades=self.open_trades,
            total_return=self.total_return,
            llm_calls=self.llm_calls,
            llm_cache_hits=self.llm_cache_hits,
            cache_hit_rate=self.cache_hit_rate,
            estimated_remaining_seconds=self._estimate_remaining_time(),
            error_message=self.error_message,
        )

    @property
    def progress_percentage(self) -> float:
        """进度百分比"""
        if self.total_klines > 0:
            return (self.current_kline / self.total_klines) * 100
        return 0.0

    def _estimate_remaining_time(self) -> Optional[float]:
        """
        估算剩余时间

        Returns:
            剩余秒数，如果无法估算则返回None
        """
        if len(self._progress_history) < 2:
            return None

        # 取最近的10个数据点
        recent_history = self._progress_history[-10:]

        if len(recent_history) < 2:
            return None

        # 计算平均速度（K线/秒）
        total_klines_processed = recent_history[-1][1] - recent_history[0][1]
        total_time = (recent_history[-1][0] - recent_history[0][0]).total_seconds()

        if total_time <= 0:
            return None

        speed = total_klines_processed / total_time  # K线/秒

        if speed <= 0:
            return None

        # 估算剩余时间
        remaining_klines = self.total_klines - self.current_kline
        return remaining_klines / speed

    def get_summary(self) -> Dict[str, Any]:
        """
        获取进度摘要

        Returns:
            摘要字典
        """
        elapsed_seconds = 0.0
        if self.started_at:
            end_time = self.completed_at or datetime.now()
            elapsed_seconds = (end_time - self.started_at).total_seconds()

        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress_percentage": round(self.progress_percentage, 2),
            "current_kline": self.current_kline,
            "total_klines": self.total_klines,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "estimated_remaining_seconds": round(self._estimate_remaining_time()) if self._estimate_remaining_time() else None,
            "current_equity": round(self.current_equity, 2),
            "total_trades": self.total_trades,
            "open_trades": self.open_trades,
            "llm_calls": self.llm_calls,
            "llm_cache_hits": self.llm_cache_hits,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
        }


class MultiTaskProgressTracker:
    """
    多任务进度追踪器

    管理多个回测任务的进度。
    """

    def __init__(self):
        """初始化多任务追踪器"""
        self._trackers: Dict[str, ProgressTracker] = {}

    def create_tracker(self, task_id: str) -> ProgressTracker:
        """
        创建新的进度追踪器

        Args:
            task_id: 任务ID

        Returns:
            ProgressTracker实例
        """
        if task_id in self._trackers:
            raise ValueError(f"任务ID已存在: {task_id}")

        tracker = ProgressTracker(task_id)
        self._trackers[task_id] = tracker
        return tracker

    def get_tracker(self, task_id: str) -> Optional[ProgressTracker]:
        """
        获取进度追踪器

        Args:
            task_id: 任务ID

        Returns:
            ProgressTracker实例，如果不存在则返回None
        """
        return self._trackers.get(task_id)

    def remove_tracker(self, task_id: str) -> None:
        """
        移除进度追踪器

        Args:
            task_id: 任务ID
        """
        if task_id in self._trackers:
            del self._trackers[task_id]

    def get_all_summaries(self) -> List[Dict[str, Any]]:
        """
        获取所有任务的进度摘要

        Returns:
            摘要列表
        """
        return [tracker.get_summary() for tracker in self._trackers.values()]

    def get_active_tasks(self) -> List[str]:
        """
        获取所有活动任务ID

        Returns:
            任务ID列表
        """
        return [
            task_id for task_id, tracker in self._trackers.items()
            if tracker.status in [BacktestStatus.RUNNING, BacktestStatus.PAUSED]
        ]
