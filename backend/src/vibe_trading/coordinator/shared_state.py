"""
Shared State Manager

Provides thread-safe shared state storage for multi-threaded trading system.
Supports get/set/delete operations with TTL and event notification.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Set
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)


@dataclass
class StateEntry:
    """State entry with TTL support"""
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """Check if entry has expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


@dataclass
class StateChangeEvent:
    """State change event"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp.isoformat(),
        }


class SharedStateManager:
    """
    Thread-safe shared state manager
    
    Provides:
    - Thread-safe get/set/delete operations
    - TTL (time-to-live) support for automatic expiration
    - Event notification when state changes
    - State history tracking (optional)
    """
    
    def __init__(self, enable_history: bool = False):
        """
        Initialize shared state manager
        
        Args:
            enable_history: Whether to track state change history
        """
        self._state: Dict[str, StateEntry] = {}
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, Set[Callable]] = {}
        self._enable_history = enable_history
        self._history: Dict[str, list] = {} if enable_history else None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("SharedStateManager initialized")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from shared state
        
        Args:
            key: State key
            default: Default value if key doesn't exist
            
        Returns:
            State value or default
        """
        async with self._lock:
            entry = self._state.get(key)
            if entry is None:
                return default
            if entry.is_expired():
                del self._state[key]
                logger.debug(f"State expired: {key}")
                return default
            return entry.value
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        notify: bool = True
    ) -> bool:
        """
        Set value in shared state
        
        Args:
            key: State key
            value: State value
            ttl_seconds: Time-to-live in seconds (None = no expiration)
            notify: Whether to notify subscribers
            
        Returns:
            True if value was set
        """
        async with self._lock:
            # Get old value for event notification
            old_entry = self._state.get(key)
            old_value = old_entry.value if old_entry and not old_entry.is_expired() else None
            
            # Calculate expiration time
            expires_at = None
            if ttl_seconds is not None:
                expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            
            # Create new entry
            self._state[key] = StateEntry(
                value=value,
                expires_at=expires_at
            )
            
            # Track history if enabled
            if self._enable_history and self._history is not None:
                if key not in self._history:
                    self._history[key] = []
                self._history[key].append({
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                })
                # Limit history size
                if len(self._history[key]) > 100:
                    self._history[key] = self._history[key][-100:]
            
            logger.debug(f"State set: {key}={value} (ttl={ttl_seconds})")
            
            # Notify subscribers
            if notify and old_value != value:
                await self._notify_subscribers(key, old_value, value)
            
            return True
    
    async def delete(self, key: str, notify: bool = True) -> bool:
        """
        Delete value from shared state
        
        Args:
            key: State key
            notify: Whether to notify subscribers
            
        Returns:
            True if value was deleted
        """
        async with self._lock:
            if key not in self._state:
                return False
            
            old_entry = self._state[key]
            old_value = old_entry.value if not old_entry.is_expired() else None
            
            del self._state[key]
            
            logger.debug(f"State deleted: {key}")
            
            # Notify subscribers
            if notify and old_value is not None:
                await self._notify_subscribers(key, old_value, None)
            
            return True
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in shared state
        
        Args:
            key: State key
            
        Returns:
            True if key exists and not expired
        """
        async with self._lock:
            entry = self._state.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._state[key]
                return False
            return True
    
    async def get_all(self) -> Dict[str, Any]:
        """
        Get all non-expired state values
        
        Returns:
            Dictionary of all state values
        """
        async with self._lock:
            # Clean up expired entries
            self._cleanup_expired()
            
            return {
                key: entry.value
                for key, entry in self._state.items()
                if not entry.is_expired()
            }
    
    async def clear(self) -> None:
        """Clear all state values"""
        async with self._lock:
            self._state.clear()
            if self._history is not None:
                self._history.clear()
            logger.info("Shared state cleared")
    
    def subscribe(self, key: str, callback: Callable) -> None:
        """
        Subscribe to state changes for a key
        
        Args:
            key: State key to subscribe to
            callback: Callback function(state_event)
        """
        if key not in self._subscribers:
            self._subscribers[key] = set()
        self._subscribers[key].add(callback)
        logger.debug(f"Subscribed to state: {key}")
    
    def unsubscribe(self, key: str, callback: Callable) -> None:
        """
        Unsubscribe from state changes for a key
        
        Args:
            key: State key to unsubscribe from
            callback: Callback function to remove
        """
        if key in self._subscribers:
            self._subscribers[key].discard(callback)
            if not self._subscribers[key]:
                del self._subscribers[key]
            logger.debug(f"Unsubscribed from state: {key}")
    
    async def _notify_subscribers(
        self,
        key: str,
        old_value: Any,
        new_value: Any
    ) -> None:
        """
        Notify subscribers of state change
        
        Args:
            key: State key that changed
            old_value: Old value
            new_value: New value
        """
        if key not in self._subscribers:
            return
        
        event = StateChangeEvent(
            key=key,
            old_value=old_value,
            new_value=new_value
        )
        
        # Notify all subscribers asynchronously
        tasks = []
        for callback in self._subscribers[key]:
            try:
                tasks.append(asyncio.create_task(callback(event)))
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(f"Notified {len(tasks)} subscribers for state: {key}")
    
    def _cleanup_expired(self) -> None:
        """Clean up expired entries (must be called with lock held)"""
        expired_keys = [
            key for key, entry in self._state.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._state[key]
            logger.debug(f"Cleaned up expired state: {key}")
    
    async def start_cleanup_task(self, interval_seconds: int = 60) -> None:
        """
        Start background cleanup task
        
        Args:
            interval_seconds: Cleanup interval in seconds
        """
        if self._cleanup_task is not None:
            logger.warning("Cleanup task already running")
            return
        
        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    async with self._lock:
                        self._cleanup_expired()
                except asyncio.CancelledError:
                    logger.info("Cleanup task cancelled")
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
        
        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(f"Cleanup task started (interval={interval_seconds}s)")
    
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Cleanup task stopped")
    
    async def get_history(self, key: str, limit: int = 10) -> list:
        """
        Get state change history for a key
        
        Args:
            key: State key
            limit: Maximum number of history entries
            
        Returns:
            List of history entries
        """
        if not self._enable_history or self._history is None:
            return []
        
        async with self._lock:
            history = self._history.get(key, [])
            return history[-limit:]
    
    async def get_statistics(self) -> Dict:
        """
        Get state manager statistics
        
        Returns:
            Dictionary of statistics
        """
        async with self._lock:
            self._cleanup_expired()
            
            return {
                "total_keys": len(self._state),
                "total_subscribers": sum(len(subs) for subs in self._subscribers.values()),
                "history_enabled": self._enable_history,
                "cleanup_task_running": self._cleanup_task is not None,
            }
    
    def __repr__(self) -> str:
        return f"SharedStateManager(keys={len(self._state)}, subscribers={len(self._subscribers)})"


# Global instance
_shared_state_manager: Optional[SharedStateManager] = None


def get_shared_state_manager() -> SharedStateManager:
    """Get global shared state manager instance"""
    global _shared_state_manager
    if _shared_state_manager is None:
        _shared_state_manager = SharedStateManager()
    return _shared_state_manager


def reset_shared_state_manager() -> None:
    """Reset global shared state manager (for testing)"""
    global _shared_state_manager
    _shared_state_manager = None