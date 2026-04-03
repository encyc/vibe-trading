"""
Trigger Registry

Central registry for managing all triggers in the trading system.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

from .base_trigger import BaseTrigger, TriggerEvent, TriggerContext, TriggerPriority

logger = logging.getLogger(__name__)


@dataclass
class TriggerStats:
    """Trigger statistics"""
    total_triggers: int
    enabled_triggers: int
    disabled_triggers: int
    total_fired: int
    triggers_by_priority: Dict[int, int]


class TriggerRegistry:
    """
    Central registry for managing triggers
    
    Provides:
    - Trigger registration and lifecycle management
    - Query and filtering of triggers
    - Event handling when triggers fire
    - Statistics and monitoring
    """
    
    def __init__(self):
        """Initialize trigger registry"""
        self._triggers: Dict[str, BaseTrigger] = {}
        self._lock = asyncio.Lock()
        self._event_handlers: List[Callable] = []
        
        logger.info("TriggerRegistry initialized")
    
    def register(self, trigger: BaseTrigger) -> bool:
        """
        Register a trigger
        
        Args:
            trigger: Trigger instance to register
            
        Returns:
            True if registered successfully
        """
        if not isinstance(trigger, BaseTrigger):
            raise TypeError(f"Expected BaseTrigger, got {type(trigger)}")
        
        if trigger.name in self._triggers:
            logger.warning(f"Trigger already registered: {trigger.name}")
            return False
        
        self._triggers[trigger.name] = trigger
        logger.info(f"Trigger registered: {trigger.name}")
        return True
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a trigger
        
        Args:
            name: Trigger name
            
        Returns:
            True if unregistered successfully
        """
        if name not in self._triggers:
            logger.warning(f"Trigger not found: {name}")
            return False
        
        del self._triggers[name]
        logger.info(f"Trigger unregistered: {name}")
        return True
    
    def get(self, name: str) -> Optional[BaseTrigger]:
        """
        Get trigger by name
        
        Args:
            name: Trigger name
            
        Returns:
            Trigger instance or None
        """
        return self._triggers.get(name)
    
    def get_all(self) -> Dict[str, BaseTrigger]:
        """
        Get all triggers
        
        Returns:
            Dictionary of trigger name to trigger instance
        """
        return self._triggers.copy()
    
    def get_enabled_triggers(self) -> List[BaseTrigger]:
        """
        Get all enabled triggers sorted by priority
        
        Returns:
            List of enabled triggers sorted by priority (descending)
        """
        enabled = [t for t in self._triggers.values() if t.enabled]
        return sorted(enabled, key=lambda t: t.priority.value, reverse=True)
    
    def get_triggers_by_priority(self, priority: TriggerPriority) -> List[BaseTrigger]:
        """
        Get triggers by priority level
        
        Args:
            priority: Priority level
            
        Returns:
            List of triggers with specified priority
        """
        return [t for t in self._triggers.values() if t.priority == priority]
    
    def get_triggers_by_symbol(self, symbol: str) -> List[BaseTrigger]:
        """
        Get triggers that monitor a specific symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of triggers monitoring the symbol
        """
        # This is a placeholder - in reality, you'd need to check
        # each trigger's configuration to see if it monitors the symbol
        return list(self._triggers.values())
    
    async def enable(self, name: str) -> bool:
        """
        Enable a trigger
        
        Args:
            name: Trigger name
            
        Returns:
            True if enabled successfully
        """
        trigger = self._triggers.get(name)
        if not trigger:
            logger.error(f"Trigger not found: {name}")
            return False
        
        await trigger.enable()
        return True
    
    async def disable(self, name: str) -> bool:
        """
        Disable a trigger
        
        Args:
            name: Trigger name
            
        Returns:
            True if disabled successfully
        """
        trigger = self._triggers.get(name)
        if not trigger:
            logger.error(f"Trigger not found: {name}")
            return False
        
        await trigger.disable()
        return True
    
    async def evaluate_all(
        self,
        context: TriggerContext
    ) -> List[TriggerEvent]:
        """
        Evaluate all enabled triggers
        
        Args:
            context: Trigger context
            
        Returns:
            List of trigger events (sorted by priority)
        """
        events = []
        
        for trigger in self.get_enabled_triggers():
            try:
                event = await trigger.evaluate(context)
                if event:
                    events.append(event)
            except Exception as e:
                logger.error(f"Error evaluating trigger {trigger.name}: {e}", exc_info=True)
        
        # Sort by priority (descending)
        events.sort(key=lambda e: e.severity, reverse=True)
        
        # Notify handlers
        for event in events:
            await self._notify_handlers(event)
        
        return events
    
    async def evaluate_trigger(
        self,
        name: str,
        context: TriggerContext
    ) -> Optional[TriggerEvent]:
        """
        Evaluate a specific trigger
        
        Args:
            name: Trigger name
            context: Trigger context
            
        Returns:
            Trigger event if conditions met, None otherwise
        """
        trigger = self._triggers.get(name)
        if not trigger:
            logger.error(f"Trigger not found: {name}")
            return None
        
        try:
            event = await trigger.evaluate(context)
            if event:
                await self._notify_handlers(event)
            return event
        except Exception as e:
            logger.error(f"Error evaluating trigger {name}: {e}", exc_info=True)
            return None
    
    def add_event_handler(self, handler: Callable) -> None:
        """
        Add event handler for trigger events
        
        Args:
            handler: Callback function(trigger_event)
        """
        self._event_handlers.append(handler)
        logger.debug(f"Event handler added: {handler.__name__}")
    
    def remove_event_handler(self, handler: Callable) -> None:
        """
        Remove event handler
        
        Args:
            handler: Callback function to remove
        """
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)
            logger.debug(f"Event handler removed: {handler.__name__}")
    
    async def _notify_handlers(self, event: TriggerEvent) -> None:
        """
        Notify all event handlers
        
        Args:
            event: Trigger event
        """
        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Error in event handler {handler.__name__}: {e}", exc_info=True)
    
    def get_statistics(self) -> TriggerStats:
        """
        Get registry statistics
        
        Returns:
            TriggerStats instance
        """
        total = len(self._triggers)
        enabled = len([t for t in self._triggers.values() if t.enabled])
        disabled = total - enabled
        
        total_fired = sum(
            t.get_statistics().get("trigger_count", 0)
            for t in self._triggers.values()
        )
        
        triggers_by_priority = {}
        for priority in TriggerPriority:
            count = len([t for t in self._triggers.values() if t.priority == priority])
            triggers_by_priority[priority.value] = count
        
        return TriggerStats(
            total_triggers=total,
            enabled_triggers=enabled,
            disabled_triggers=disabled,
            total_fired=total_fired,
            triggers_by_priority=triggers_by_priority,
        )
    
    def clear(self) -> None:
        """Clear all triggers"""
        self._triggers.clear()
        self._event_handlers.clear()
        logger.info("TriggerRegistry cleared")
    
    def __len__(self) -> int:
        return len(self._triggers)
    
    def __contains__(self, name: str) -> bool:
        return name in self._triggers
    
    def __repr__(self) -> str:
        return f"TriggerRegistry(triggers={len(self._triggers)}, enabled={len(self.get_enabled_triggers())})"


# Global instance
_trigger_registry: Optional[TriggerRegistry] = None


def get_trigger_registry() -> TriggerRegistry:
    """Get global trigger registry instance"""
    global _trigger_registry
    if _trigger_registry is None:
        _trigger_registry = TriggerRegistry()
    return _trigger_registry


def reset_trigger_registry() -> None:
    """Reset global trigger registry (for testing)"""
    global _trigger_registry
    _trigger_registry = None


# Decorator for easy registration
def register_trigger(registry: Optional[TriggerRegistry] = None):
    """
    Decorator to register a trigger class
    
    Usage:
        @register_trigger()
        class MyTrigger(BaseTrigger):
            pass
    """
    def decorator(trigger_class):
        # Create instance if it's a class
        if isinstance(trigger_class, type):
            instance = trigger_class()
        else:
            instance = trigger_class
        
        reg = registry or get_trigger_registry()
        reg.register(instance)
        return trigger_class
    
    return decorator