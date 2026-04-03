"""
Base Trigger

Abstract base class for all triggers in the trading system.
"""
import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TriggerPriority(int, Enum):
    """Trigger priority level (higher = more urgent)"""
    LOW = 30
    MEDIUM = 50
    HIGH = 70
    CRITICAL = 90


class TriggerSeverity(str, Enum):
    """Trigger severity level"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TriggerContext:
    """
    Context provided to trigger check method
    
    Contains market data and system state for trigger evaluation.
    """
    symbol: str
    current_price: float
    previous_price: float
    timestamp: int
    positions: List[Dict] = field(default_factory=list)
    account_balance: float = 0.0
    additional_data: Dict = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from additional_data"""
        return self.additional_data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in additional_data"""
        self.additional_data[key] = value


@dataclass
class TriggerEvent:
    """
    Trigger event generated when trigger conditions are met
    
    Contains information about the trigger event for further processing.
    """
    event_id: str
    trigger_name: str
    severity: TriggerSeverity
    data: Dict
    timestamp: int
    
    # Optional fields
    symbol: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize event_id if not provided"""
        if not self.event_id:
            self.event_id = f"evt_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "trigger_name": self.trigger_name,
            "severity": self.severity.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "correlation_id": self.correlation_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TriggerEvent":
        """Create from dictionary"""
        return cls(
            event_id=data["event_id"],
            trigger_name=data["trigger_name"],
            severity=TriggerSeverity(data["severity"]),
            data=data["data"],
            timestamp=data["timestamp"],
            symbol=data.get("symbol"),
            correlation_id=data.get("correlation_id"),
        )


class BaseTrigger(ABC):
    """
    Abstract base class for all triggers
    
    Triggers monitor market conditions and generate events when conditions are met.
    
    Attributes:
        name: Unique trigger name
        priority: Trigger priority (TriggerPriority enum)
        cooldown_seconds: Minimum time between triggers
        check_interval: How often to check trigger condition (seconds)
        enabled: Whether trigger is enabled
        severity: Severity level when trigger fires
    """
    
    def __init__(
        self,
        name: str,
        priority: TriggerPriority = TriggerPriority.MEDIUM,
        cooldown_seconds: int = 300,
        check_interval: int = 10,
        enabled: bool = True,
        severity: TriggerSeverity = TriggerSeverity.MEDIUM,
    ):
        """
        Initialize trigger
        
        Args:
            name: Unique trigger name
            priority: Trigger priority level
            cooldown_seconds: Minimum time between triggers (seconds)
            check_interval: How often to check (seconds)
            enabled: Whether trigger is enabled
            severity: Severity level when trigger fires
        """
        self.name = name
        self.priority = priority
        self.cooldown_seconds = cooldown_seconds
        self.check_interval = check_interval
        self.enabled = enabled
        self.severity = severity
        
        # State tracking
        self._last_triggered_at: Optional[datetime] = None
        self._trigger_count = 0
        self._lock = asyncio.Lock()
        
        logger.info(f"Trigger initialized: {name} (priority={priority.value}, cooldown={cooldown_seconds}s)")
    
    @abstractmethod
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """
        Check if trigger conditions are met
        
        Args:
            context: Trigger context with market data
            
        Returns:
            TriggerEvent if conditions met, None otherwise
        """
        pass
    
    async def evaluate(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """
        Evaluate trigger with cooldown check
        
        Args:
            context: Trigger context
            
        Returns:
            TriggerEvent if conditions met and not in cooldown, None otherwise
        """
        if not self.enabled:
            return None
        
        # Check cooldown
        if not await self.check_cooldown():
            logger.debug(f"Trigger {self.name} in cooldown, skipping")
            return None
        
        # Check trigger condition
        event = await self.check(context)
        
        if event:
            # Update last triggered time
            await self._update_triggered()
            logger.info(f"Trigger {self.name} fired: {event.severity.value}")
        
        return event
    
    async def check_cooldown(self) -> bool:
        """
        Check if trigger is in cooldown period
        
        Returns:
            True if not in cooldown (can trigger), False otherwise
        """
        async with self._lock:
            if self._last_triggered_at is None:
                return True
            
            elapsed = datetime.now() - self._last_triggered_at
            return elapsed.total_seconds() >= self.cooldown_seconds
    
    async def _update_triggered(self) -> None:
        """Update trigger state after firing"""
        async with self._lock:
            self._last_triggered_at = datetime.now()
            self._trigger_count += 1
    
    async def reset_cooldown(self) -> None:
        """Reset cooldown period"""
        async with self._lock:
            self._last_triggered_at = None
            logger.debug(f"Cooldown reset for trigger: {self.name}")
    
    async def enable(self) -> None:
        """Enable trigger"""
        self.enabled = True
        logger.info(f"Trigger enabled: {self.name}")
    
    async def disable(self) -> None:
        """Disable trigger"""
        self.enabled = False
        logger.info(f"Trigger disabled: {self.name}")
    
    def get_statistics(self) -> Dict:
        """
        Get trigger statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "name": self.name,
            "priority": self.priority.value,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "cooldown_seconds": self.cooldown_seconds,
            "check_interval": self.check_interval,
            "trigger_count": self._trigger_count,
            "last_triggered_at": self._last_triggered_at.isoformat() if self._last_triggered_at else None,
            "in_cooldown": not asyncio.iscoroutinefunction(self.check_cooldown) and self._last_triggered_at is not None,
        }
    
    def __repr__(self) -> str:
        return f"BaseTrigger(name={self.name}, priority={self.priority.value}, enabled={self.enabled})"
    
    def __hash__(self) -> int:
        return hash(self.name)
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseTrigger):
            return False
        return self.name == other.name


class PriceDropTrigger(BaseTrigger):
    """
    Example: Price drop trigger
    
    Fires when price drops by specified percentage.
    """
    
    def __init__(
        self,
        threshold_pct: float = 0.03,
        **kwargs
    ):
        """
        Initialize price drop trigger
        
        Args:
            threshold_pct: Price drop threshold (e.g., 0.03 for 3%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="price_drop",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.threshold_pct = threshold_pct
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if price dropped by threshold"""
        if context.previous_price <= 0:
            return None
        
        drop_pct = (context.previous_price - context.current_price) / context.previous_price
        
        if drop_pct >= self.threshold_pct:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=self.severity,
                data={
                    "current_price": context.current_price,
                    "previous_price": context.previous_price,
                    "drop_pct": drop_pct,
                    "threshold_pct": self.threshold_pct,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class VolatilitySpikeTrigger(BaseTrigger):
    """
    Example: Volatility spike trigger
    
    Fires when price volatility exceeds threshold.
    """
    
    def __init__(
        self,
        threshold_std: float = 2.0,
        **kwargs
    ):
        """
        Initialize volatility spike trigger
        
        Args:
            threshold_std: Standard deviation threshold
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="volatility_spike",
            priority=TriggerPriority.MEDIUM,
            severity=TriggerSeverity.MEDIUM,
            **kwargs
        )
        self.threshold_std = threshold_std
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if volatility spiked"""
        # Get recent prices from context
        recent_prices = context.get("recent_prices", [])
        if len(recent_prices) < 20:
            return None
        
        # Calculate standard deviation
        import statistics
        avg_price = statistics.mean(recent_prices)
        std_price = statistics.stdev(recent_prices)
        
        # Check if current price is far from mean
        z_score = abs(context.current_price - avg_price) / std_price if std_price > 0 else 0
        
        if z_score >= self.threshold_std:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=self.severity,
                data={
                    "current_price": context.current_price,
                    "avg_price": avg_price,
                    "std_price": std_price,
                    "z_score": z_score,
                    "threshold_std": self.threshold_std,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None