"""
Price Triggers

Triggers based on price movements and patterns.
"""
import logging
from typing import Optional

from .base_trigger import BaseTrigger, TriggerContext, TriggerEvent, TriggerPriority, TriggerSeverity

logger = logging.getLogger(__name__)


class PriceDropTrigger(BaseTrigger):
    """
    Price drop trigger
    
    Fires when price drops by a specified percentage.
    """
    
    def __init__(
        self,
        threshold_pct: float = 0.03,
        symbol: str = "BTCUSDT",
        **kwargs
    ):
        """
        Initialize price drop trigger
        
        Args:
            threshold_pct: Price drop threshold (e.g., 0.03 for 3%)
            symbol: Trading symbol to monitor
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name=f"price_drop_{symbol}",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.threshold_pct = threshold_pct
        self.symbol = symbol
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if price dropped by threshold"""
        if context.previous_price <= 0:
            return None
        
        drop_pct = (context.previous_price - context.current_price) / context.previous_price
        
        if drop_pct >= self.threshold_pct:
            severity = TriggerSeverity.CRITICAL if drop_pct >= 0.05 else TriggerSeverity.HIGH
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=severity,
                data={
                    "current_price": context.current_price,
                    "previous_price": context.previous_price,
                    "drop_pct": drop_pct,
                    "threshold_pct": self.threshold_pct,
                    "symbol": context.symbol,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class PriceSpikeTrigger(BaseTrigger):
    """
    Price spike trigger
    
    Fires when price increases by a specified percentage.
    """
    
    def __init__(
        self,
        threshold_pct: float = 0.03,
        symbol: str = "BTCUSDT",
        **kwargs
    ):
        """
        Initialize price spike trigger
        
        Args:
            threshold_pct: Price increase threshold (e.g., 0.03 for 3%)
            symbol: Trading symbol to monitor
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name=f"price_spike_{symbol}",
            priority=TriggerPriority.MEDIUM,
            severity=TriggerSeverity.MEDIUM,
            **kwargs
        )
        self.threshold_pct = threshold_pct
        self.symbol = symbol
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if price spiked by threshold"""
        if context.previous_price <= 0:
            return None
        
        spike_pct = (context.current_price - context.previous_price) / context.previous_price
        
        if spike_pct >= self.threshold_pct:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=self.severity,
                data={
                    "current_price": context.current_price,
                    "previous_price": context.previous_price,
                    "spike_pct": spike_pct,
                    "threshold_pct": self.threshold_pct,
                    "symbol": context.symbol,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class SupportBreakoutTrigger(BaseTrigger):
    """
    Support level breakout trigger
    
    Fires when price breaks below a support level.
    """
    
    def __init__(
        self,
        support_level: float,
        symbol: str = "BTCUSDT",
        tolerance_pct: float = 0.005,
        **kwargs
    ):
        """
        Initialize support breakout trigger
        
        Args:
            support_level: Support level price
            symbol: Trading symbol to monitor
            tolerance_pct: Tolerance for breakout detection (e.g., 0.005 for 0.5%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name=f"support_breakout_{symbol}",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.support_level = support_level
        self.symbol = symbol
        self.tolerance_pct = tolerance_pct
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if price broke below support"""
        if self.support_level <= 0:
            return None
        
        # Check if price is below support with tolerance
        below_support = context.current_price < self.support_level * (1 - self.tolerance_pct)
        
        if below_support:
            breakout_pct = (self.support_level - context.current_price) / self.support_level
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=self.severity,
                data={
                    "current_price": context.current_price,
                    "support_level": self.support_level,
                    "breakout_pct": breakout_pct,
                    "symbol": context.symbol,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class ResistanceBreakoutTrigger(BaseTrigger):
    """
    Resistance level breakout trigger
    
    Fires when price breaks above a resistance level.
    """
    
    def __init__(
        self,
        resistance_level: float,
        symbol: str = "BTCUSDT",
        tolerance_pct: float = 0.005,
        **kwargs
    ):
        """
        Initialize resistance breakout trigger
        
        Args:
            resistance_level: Resistance level price
            symbol: Trading symbol to monitor
            tolerance_pct: Tolerance for breakout detection (e.g., 0.005 for 0.5%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name=f"resistance_breakout_{symbol}",
            priority=TriggerPriority.MEDIUM,
            severity=TriggerSeverity.MEDIUM,
            **kwargs
        )
        self.resistance_level = resistance_level
        self.symbol = symbol
        self.tolerance_pct = tolerance_pct
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if price broke above resistance"""
        if self.resistance_level <= 0:
            return None
        
        # Check if price is above resistance with tolerance
        above_resistance = context.current_price > self.resistance_level * (1 + self.tolerance_pct)
        
        if above_resistance:
            breakout_pct = (context.current_price - self.resistance_level) / self.resistance_level
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=self.severity,
                data={
                    "current_price": context.current_price,
                    "resistance_level": self.resistance_level,
                    "breakout_pct": breakout_pct,
                    "symbol": context.symbol,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class WickReversalTrigger(BaseTrigger):
    """
    Wick (long shadow) reversal trigger
    
    Fires when a candle has a long wick indicating potential reversal.
    """
    
    def __init__(
        self,
        wick_ratio: float = 0.3,
        symbol: str = "BTCUSDT",
        **kwargs
    ):
        """
        Initialize wick reversal trigger
        
        Args:
            wick_ratio: Minimum wick to body ratio (e.g., 0.3 for 30%)
            symbol: Trading symbol to monitor
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name=f"wick_reversal_{symbol}",
            priority=TriggerPriority.MEDIUM,
            severity=TriggerSeverity.MEDIUM,
            **kwargs
        )
        self.wick_ratio = wick_ratio
        self.symbol = symbol
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if candle has long wick"""
        # Get candle data from context
        open_price = context.get("open")
        high = context.get("high")
        low = context.get("low")
        
        if not all([open_price, high, low]):
            return None
        
        # Calculate body and wick sizes
        body_size = abs(open_price - context.current_price)
        total_range = high - low
        
        if total_range <= 0:
            return None
        
        # Calculate wick sizes
        upper_wick = high - max(open_price, context.current_price)
        lower_wick = min(open_price, context.current_price) - low
        max_wick = max(upper_wick, lower_wick)
        
        # Check if wick is long enough relative to body
        if max_wick > 0 and body_size > 0:
            wick_to_body_ratio = max_wick / body_size
            if wick_to_body_ratio >= self.wick_ratio:
                return TriggerEvent(
                    event_id="",
                    trigger_name=self.name,
                    severity=self.severity,
                    data={
                        "open": open_price,
                        "close": context.current_price,
                        "high": high,
                        "low": low,
                        "upper_wick": upper_wick,
                        "lower_wick": lower_wick,
                        "wick_ratio": wick_to_body_ratio,
                        "symbol": context.symbol,
                    },
                    timestamp=context.timestamp,
                    symbol=context.symbol,
                )
        
        return None