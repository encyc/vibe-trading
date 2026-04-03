"""
Triggers Module

Provides event-driven trigger system for the trading system.
Triggers monitor market conditions and can trigger emergency actions.
"""

from .base_trigger import (
    BaseTrigger,
    TriggerContext,
    TriggerEvent,
    TriggerPriority,
    TriggerSeverity,
)
from .trigger_registry import (
    TriggerRegistry,
    get_trigger_registry,
    register_trigger,
)

# Price triggers
from .price_triggers import (
    PriceDropTrigger,
    PriceSpikeTrigger,
    SupportBreakoutTrigger,
    ResistanceBreakoutTrigger,
    WickReversalTrigger,
)

# Risk triggers
from .risk_triggers import (
    MarginRatioTrigger,
    ConsecutiveLossTrigger,
    DrawdownTrigger,
    VaRTrigger,
    PositionSizeTrigger,
    LiquidationRiskTrigger,
)

__all__ = [
    # Base classes
    "BaseTrigger",
    "TriggerContext",
    "TriggerEvent",
    "TriggerPriority",
    "TriggerSeverity",
    
    # Registry
    "TriggerRegistry",
    "get_trigger_registry",
    "register_trigger",
    
    # Price triggers
    "PriceDropTrigger",
    "PriceSpikeTrigger",
    "SupportBreakoutTrigger",
    "ResistanceBreakoutTrigger",
    "WickReversalTrigger",
    
    # Risk triggers
    "MarginRatioTrigger",
    "ConsecutiveLossTrigger",
    "DrawdownTrigger",
    "VaRTrigger",
    "PositionSizeTrigger",
    "LiquidationRiskTrigger",
]