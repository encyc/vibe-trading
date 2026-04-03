"""
Event Queue

Priority queue for managing trigger events.
"""
import asyncio
import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum

from vibe_trading.triggers.base_trigger import TriggerEvent, TriggerSeverity

logger = logging.getLogger(__name__)


class EventStatus(str, Enum):
    """Event status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    IGNORED = "ignored"


@dataclass(order=True)
class PriorityEvent:
    """
    Event with priority for queue ordering
    
    Higher priority (lower score) events are processed first.
    """
    priority_score: int  # Lower = higher priority
    timestamp: int  # For FIFO ordering within same priority
    event: TriggerEvent
    status: EventStatus = field(default=EventStatus.PENDING)
    
    def __post_init__(self):
        """Convert event severity to priority score"""
        if self.priority_score == 0:
            self.priority_score = self._get_priority_score(self.event.severity)
    
    @staticmethod
    def _get_priority_score(severity: TriggerSeverity) -> int:
        """Convert severity to priority score"""
        severity_scores = {
            TriggerSeverity.CRITICAL: 10,
            TriggerSeverity.HIGH: 20,
            TriggerSeverity.MEDIUM: 30,
            TriggerSeverity.LOW: 40,
        }
        return severity_scores.get(severity, 50)


class EventQueue:
    """
    Priority queue for managing trigger events
    
    Provides:
    - Priority-based event ordering
    - Thread-safe operations
    - Event status tracking
    - Statistics and monitoring
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize event queue
        
        Args:
            max_size: Maximum queue size
        """
        self._queue: List[PriorityEvent] = []
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._event_counter = 0
        
        # Statistics
        self._total_events = 0
        self._processed_events = 0
        self._failed_events = 0
        self._ignored_events = 0
        
        logger.info("EventQueue initialized")
    
    async def put(self, event: TriggerEvent) -> bool:
        """
        Add event to queue
        
        Args:
            event: Trigger event to add
            
        Returns:
            True if event was added successfully
        """
        async with self._lock:
            if len(self._queue) >= self._max_size:
                logger.warning("Event queue is full, dropping event")
                return False
            
            # Create priority event
            priority_event = PriorityEvent(
                priority_score=0,  # Will be set in __post_init__
                timestamp=int(datetime.now().timestamp() * 1000),
                event=event,
                status=EventStatus.PENDING,
            )
            
            # Add to heap
            heapq.heappush(self._queue, priority_event)
            self._total_events += 1
            self._event_counter += 1
            
            logger.debug(f"Event added to queue: {event.event_id} (severity={event.severity.value})")
            return True
    
    async def get(self, timeout: Optional[float] = None) -> Optional[TriggerEvent]:
        """
        Get highest priority event from queue
        
        Args:
            timeout: Optional timeout in seconds
            
        Returns:
            Trigger event or None if queue is empty
        """
        async with self._lock:
            if not self._queue:
                return None
            
            # Get highest priority event
            priority_event = heapq.heappop(self._queue)
            priority_event.status = EventStatus.PROCESSING
            
            logger.debug(f"Event retrieved from queue: {priority_event.event.event_id}")
            return priority_event.event
    
    async def put_batch(self, events: List[TriggerEvent]) -> int:
        """
        Add multiple events to queue
        
        Args:
            events: List of trigger events to add
            
        Returns:
            Number of events successfully added
        """
        added_count = 0
        
        for event in events:
            if await self.put(event):
                added_count += 1
        
        logger.info(f"Added {added_count}/{len(events)} events to queue")
        return added_count
    
    async def mark_completed(self, event_id: str, success: bool = True) -> bool:
        """
        Mark event as completed
        
        Args:
            event_id: Event ID to mark
            success: Whether event was processed successfully
            
        Returns:
            True if event was found and marked
        """
        async with self._lock:
            for priority_event in self._queue:
                if priority_event.event.event_id == event_id:
                    if success:
                        priority_event.status = EventStatus.COMPLETED
                        self._processed_events += 1
                    else:
                        priority_event.status = EventStatus.FAILED
                        self._failed_events += 1
                    return True
            return False
    
    async def mark_ignored(self, event_id: str) -> bool:
        """
        Mark event as ignored
        
        Args:
            event_id: Event ID to mark
            
        Returns:
            True if event was found and marked
        """
        async with self._lock:
            for priority_event in self._queue:
                if priority_event.event.event_id == event_id:
                    priority_event.status = EventStatus.IGNORED
                    self._ignored_events += 1
                    return True
            return False
    
    async def get_by_id(self, event_id: str) -> Optional[TriggerEvent]:
        """
        Get event by ID without removing from queue
        
        Args:
            event_id: Event ID to retrieve
            
        Returns:
            Trigger event or None if not found
        """
        async with self._lock:
            for priority_event in self._queue:
                if priority_event.event.event_id == event_id:
                    return priority_event.event
            return None
    
    async def peek(self) -> Optional[TriggerEvent]:
        """
        Peek at highest priority event without removing
        
        Returns:
            Trigger event or None if queue is empty
        """
        async with self._lock:
            if not self._queue:
                return None
            return self._queue[0].event
    
    async def size(self) -> int:
        """
        Get current queue size
        
        Returns:
            Number of events in queue
        """
        async with self._lock:
            return len(self._queue)
    
    async def is_empty(self) -> bool:
        """
        Check if queue is empty
        
        Returns:
            True if queue is empty
        """
        async with self._lock:
            return len(self._queue) == 0
    
    async def clear(self) -> None:
        """Clear all events from queue"""
        async with self._lock:
            self._queue.clear()
            logger.info("Event queue cleared")
    
    async def get_statistics(self) -> Dict:
        """
        Get queue statistics
        
        Returns:
            Dictionary of statistics
        """
        async with self._lock:
            # Count events by severity
            severity_counts = {}
            for priority_event in self._queue:
                severity = priority_event.event.severity.value
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            # Count events by status
            status_counts = {}
            for priority_event in self._queue:
                status = priority_event.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "queue_size": len(self._queue),
                "max_size": self._max_size,
                "total_events": self._total_events,
                "processed_events": self._processed_events,
                "failed_events": self._failed_events,
                "ignored_events": self._ignored_events,
                "severity_distribution": severity_counts,
                "status_distribution": status_counts,
            }
    
    async def get_pending_events(self, limit: int = 10) -> List[TriggerEvent]:
        """
        Get pending events (for monitoring)
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of pending trigger events
        """
        async with self._lock:
            pending = [
                pe.event for pe in self._queue
                if pe.status == EventStatus.PENDING
            ]
            # Sort by priority (already sorted in heap)
            return pending[:limit]
    
    def __len__(self) -> int:
        """Get queue size (synchronous)"""
        return len(self._queue)
    
    def __repr__(self) -> str:
        return f"EventQueue(size={len(self._queue)}, max_size={self._max_size})"


# Global instance
_event_queue: Optional[EventQueue] = None


def get_event_queue() -> EventQueue:
    """Get global event queue instance"""
    global _event_queue
    if _event_queue is None:
        _event_queue = EventQueue()
    return _event_queue


def reset_event_queue() -> None:
    """Reset global event queue (for testing)"""
    global _event_queue
    _event_queue = None