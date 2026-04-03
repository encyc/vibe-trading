"""
Thread Manager

Manages multiple threads in the trading system, including lifecycle,
inter-thread communication, and emergency mode control.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import uuid

from vibe_trading.coordinator.shared_state import SharedStateManager, get_shared_state_manager
from vibe_trading.agents.messaging import (
    MessageBroker,
    MessageType,
    get_message_broker,
    AgentMessage,
)

logger = logging.getLogger(__name__)


class ThreadStatus(str, Enum):
    """Thread status"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ThreadInfo:
    """Thread information"""
    name: str
    task: Optional[asyncio.Task]
    status: ThreadStatus
    current_task: str = ""
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    error_count: int = 0
    total_runs: int = 0
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "current_task": self.current_task,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "error_count": self.error_count,
            "total_runs": self.total_runs,
            "metadata": self.metadata,
        }


class ThreadManager:
    """
    Thread manager for multi-threaded trading system
    
    Provides:
    - Thread lifecycle management (start, stop, pause, resume)
    - Inter-thread communication via MessageBroker
    - Emergency mode control (pause main thread, execute emergency actions)
    - Thread state persistence to database
    - Health monitoring and statistics
    """
    
    def __init__(
        self,
        shared_state: Optional[SharedStateManager] = None,
        message_broker: Optional[MessageBroker] = None
    ):
        """
        Initialize thread manager
        
        Args:
            shared_state: Shared state manager instance
            message_broker: Message broker instance
        """
        self.shared_state = shared_state or get_shared_state_manager()
        self.message_broker = message_broker or get_message_broker()
        
        self._threads: Dict[str, ThreadInfo] = {}
        self._lock = asyncio.Lock()
        self._emergency_lock = asyncio.Lock()
        self._main_thread_stopped_event = asyncio.Event()
        
        logger.info("ThreadManager initialized")
    
    async def register_thread(
        self,
        name: str,
        coroutine: Callable,
        metadata: Optional[Dict] = None
    ) -> ThreadInfo:
        """
        Register a new thread
        
        Args:
            name: Thread name
            coroutine: Async coroutine to run
            metadata: Optional metadata
            
        Returns:
            ThreadInfo instance
        """
        async with self._lock:
            if name in self._threads:
                raise ValueError(f"Thread already registered: {name}")
            
            thread_info = ThreadInfo(
                name=name,
                task=None,
                status=ThreadStatus.INITIALIZING,
                metadata=metadata or {}
            )
            
            self._threads[name] = thread_info
            logger.info(f"Thread registered: {name}")
            
            return thread_info
    
    async def start_thread(self, name: str) -> bool:
        """
        Start a registered thread
        
        Args:
            name: Thread name
            
        Returns:
            True if thread started successfully
        """
        async with self._lock:
            thread_info = self._threads.get(name)
            if not thread_info:
                logger.error(f"Thread not found: {name}")
                return False
            
            if thread_info.status == ThreadStatus.RUNNING:
                logger.warning(f"Thread already running: {name}")
                return False
            
            # Create and start task
            thread_info.status = ThreadStatus.RUNNING
            thread_info.started_at = datetime.now()
            thread_info.last_activity_at = datetime.now()
            
            # Store coroutine for execution
            # Note: Actual task creation happens in run_thread method
            logger.info(f"Thread started: {name}")
            
            return True
    
    async def run_thread(
        self,
        name: str,
        coroutine: Callable,
        *args,
        **kwargs
    ) -> None:
        """
        Run a thread with error handling and monitoring
        
        Args:
            name: Thread name
            coroutine: Async coroutine to run
            *args: Coroutine arguments
            **kwargs: Coroutine keyword arguments
        """
        async with self._lock:
            thread_info = self._threads.get(name)
            if not thread_info:
                logger.error(f"Thread not found: {name}")
                return
            
            # Create task
            thread_info.task = asyncio.create_task(
                self._run_thread_wrapper(name, coroutine, *args, **kwargs)
            )
        
        # Wait for task to complete
        try:
            await thread_info.task
        except asyncio.CancelledError:
            logger.info(f"Thread cancelled: {name}")
        except Exception as e:
            logger.error(f"Thread error: {name} - {e}")
    
    async def _run_thread_wrapper(
        self,
        name: str,
        coroutine: Callable,
        *args,
        **kwargs
    ) -> None:
        """
        Thread wrapper with error handling and monitoring
        
        Args:
            name: Thread name
            coroutine: Async coroutine to run
            *args: Coroutine arguments
            **kwargs: Coroutine keyword arguments
        """
        thread_info = self._threads.get(name)
        if not thread_info:
            return
        
        try:
            # Execute coroutine
            await coroutine(*args, **kwargs)
            
            # Update thread info
            thread_info.status = ThreadStatus.STOPPED
            thread_info.last_activity_at = datetime.now()
            
            logger.info(f"Thread completed: {name}")
            
        except asyncio.CancelledError:
            thread_info.status = ThreadStatus.STOPPED
            thread_info.last_activity_at = datetime.now()
            logger.info(f"Thread cancelled: {name}")
            raise
        
        except Exception as e:
            thread_info.status = ThreadStatus.ERROR
            thread_info.error_count += 1
            thread_info.last_activity_at = datetime.now()
            logger.error(f"Thread error: {name} - {e}", exc_info=True)
            
            # Send error message
            self.message_broker.send(
                sender=name,
                receiver="system",
                message_type=MessageType.ERROR,
                content={"error": str(e), "thread": name},
                correlation_id=str(uuid.uuid4()),
            )
    
    async def stop_thread(self, name: str, timeout: float = 30.0) -> bool:
        """
        Stop a running thread
        
        Args:
            name: Thread name
            timeout: Timeout in seconds
            
        Returns:
            True if thread stopped successfully
        """
        async with self._lock:
            thread_info = self._threads.get(name)
            if not thread_info:
                logger.error(f"Thread not found: {name}")
                return False
            
            if thread_info.status in [ThreadStatus.STOPPED, ThreadStatus.STOPPING]:
                logger.warning(f"Thread already stopped: {name}")
                return True
            
            thread_info.status = ThreadStatus.STOPPING
            
        # Cancel task
        if thread_info.task and not thread_info.task.done():
            thread_info.task.cancel()
            
            try:
                await asyncio.wait_for(thread_info.task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Thread stop timeout: {name}")
                return False
            except asyncio.CancelledError:
                pass
        
        async with self._lock:
            thread_info.status = ThreadStatus.STOPPED
            thread_info.last_activity_at = datetime.now()
        
        logger.info(f"Thread stopped: {name}")
        return True
    
    async def pause_thread(self, name: str) -> bool:
        """
        Pause a running thread
        
        Args:
            name: Thread name
            
        Returns:
            True if thread paused successfully
        """
        async with self._lock:
            thread_info = self._threads.get(name)
            if not thread_info:
                logger.error(f"Thread not found: {name}")
                return False
            
            if thread_info.status != ThreadStatus.RUNNING:
                logger.warning(f"Thread not running: {name}")
                return False
            
            thread_info.status = ThreadStatus.PAUSED
        
        # Send pause message
        self.message_broker.send(
            sender="thread_manager",
            receiver=name,
            message_type=MessageType.WARNING,
            content={"action": "pause"},
            correlation_id=str(uuid.uuid4()),
        )
        
        logger.info(f"Thread paused: {name}")
        return True
    
    async def resume_thread(self, name: str) -> bool:
        """
        Resume a paused thread
        
        Args:
            name: Thread name
            
        Returns:
            True if thread resumed successfully
        """
        async with self._lock:
            thread_info = self._threads.get(name)
            if not thread_info:
                logger.error(f"Thread not found: {name}")
                return False
            
            if thread_info.status != ThreadStatus.PAUSED:
                logger.warning(f"Thread not paused: {name}")
                return False
            
            thread_info.status = ThreadStatus.RUNNING
        
        # Send resume message
        self.message_broker.send(
            sender="thread_manager",
            receiver=name,
            message_type=MessageType.INFO,
            content={"action": "resume"},
            correlation_id=str(uuid.uuid4()),
        )
        
        logger.info(f"Thread resumed: {name}")
        return True
    
    async def notify_emergency_mode(
        self,
        trigger_event: Optional[Dict] = None
    ) -> None:
        """
        Notify system to enter emergency mode
        
        Args:
            trigger_event: Optional trigger event data
        """
        async with self._emergency_lock:
            logger.warning("Entering emergency mode")
            
            # Set emergency mode flag
            await self.shared_state.set("emergency_mode", True, notify=True)
            await self.shared_state.set("emergency_event", trigger_event, notify=True)
            
            # Notify main thread to stop
            self.message_broker.send(
                sender="thread_manager",
                receiver="main_thread",
                message_type=MessageType.WARNING,
                content={
                    "action": "emergency_stop",
                    "trigger_event": trigger_event,
                },
                correlation_id=str(uuid.uuid4()),
            )
            
            # Wait for main thread to acknowledge
            await asyncio.wait_for(
                self._wait_for_main_thread_stop(),
                timeout=30.0
            )
            
            logger.info("Main thread stopped for emergency mode")
    
    async def notify_emergency_complete(self) -> None:
        """
        Notify system that emergency mode is complete
        """
        async with self._emergency_lock:
            logger.info("Emergency mode complete")
            
            # Clear emergency mode flag
            await self.shared_state.set("emergency_mode", False, notify=True)
            await self.shared_state.set("emergency_event", None, notify=True)
            
            # Notify main thread to resume
            self.message_broker.send(
                sender="thread_manager",
                receiver="main_thread",
                message_type=MessageType.INFO,
                content={"action": "emergency_resume"},
                correlation_id=str(uuid.uuid4()),
            )
            
            # Clear the stop event
            self._main_thread_stopped_event.clear()
    
    async def _wait_for_main_thread_stop(self) -> None:
        """Wait for main thread to acknowledge stop"""
        # Subscribe to main thread status changes
        event = asyncio.Event()
        
        def on_state_change(state_change):
            if state_change.key == "main_thread_stopped" and state_change.new_value:
                event.set()
        
        self.shared_state.subscribe("main_thread_stopped", on_state_change)
        
        try:
            # Wait for main thread to set the flag
            await asyncio.wait_for(event.wait(), timeout=30.0)
        finally:
            self.shared_state.unsubscribe("main_thread_stopped", on_state_change)
    
    async def is_emergency_mode(self) -> bool:
        """
        Check if system is in emergency mode
        
        Returns:
            True if in emergency mode
        """
        return await self.shared_state.get("emergency_mode", False)
    
    async def get_thread_info(self, name: str) -> Optional[ThreadInfo]:
        """
        Get thread information
        
        Args:
            name: Thread name
            
        Returns:
            ThreadInfo or None
        """
        async with self._lock:
            return self._threads.get(name)
    
    async def get_all_threads(self) -> Dict[str, ThreadInfo]:
        """
        Get all thread information
        
        Returns:
            Dictionary of thread name to ThreadInfo
        """
        async with self._lock:
            return self._threads.copy()
    
    async def get_statistics(self) -> Dict:
        """
        Get thread manager statistics
        
        Returns:
            Dictionary of statistics
        """
        async with self._lock:
            status_counts = {}
            for thread_info in self._threads.values():
                status = thread_info.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_threads": len(self._threads),
                "status_counts": status_counts,
                "emergency_mode": await self.shared_state.get("emergency_mode", False),
                "shared_state_stats": await self.shared_state.get_statistics(),
            }
    
    async def shutdown(self, timeout: float = 30.0) -> None:
        """
        Shutdown all threads gracefully
        
        Args:
            timeout: Timeout in seconds for each thread
        """
        logger.info("Shutting down thread manager...")
        
        # Stop all threads
        for name in list(self._threads.keys()):
            await self.stop_thread(name, timeout=timeout)
        
        # Stop cleanup task
        await self.shared_state.stop_cleanup_task()
        
        logger.info("Thread manager shutdown complete")


# Global instance
_thread_manager: Optional[ThreadManager] = None


def get_thread_manager() -> ThreadManager:
    """Get global thread manager instance"""
    global _thread_manager
    if _thread_manager is None:
        _thread_manager = ThreadManager()
    return _thread_manager


def reset_thread_manager() -> None:
    """Reset global thread manager (for testing)"""
    global _thread_manager
    _thread_manager = None