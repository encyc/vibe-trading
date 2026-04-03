"""
Risk Triggers

Triggers based on risk metrics and position management.
"""
import logging
from typing import Optional

from .base_trigger import BaseTrigger, TriggerContext, TriggerEvent, TriggerPriority, TriggerSeverity

logger = logging.getLogger(__name__)


class MarginRatioTrigger(BaseTrigger):
    """
    Margin ratio trigger
    
    Fires when margin ratio exceeds threshold.
    """
    
    def __init__(
        self,
        threshold_ratio: float = 0.5,
        **kwargs
    ):
        """
        Initialize margin ratio trigger
        
        Args:
            threshold_ratio: Margin ratio threshold (e.g., 0.5 for 50%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="margin_ratio_warning",
            priority=TriggerPriority.CRITICAL,
            severity=TriggerSeverity.CRITICAL,
            **kwargs
        )
        self.threshold_ratio = threshold_ratio
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if margin ratio exceeds threshold"""
        margin_ratio = context.get("margin_ratio", 0.0)
        
        if margin_ratio >= self.threshold_ratio:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=TriggerSeverity.CRITICAL,
                data={
                    "margin_ratio": margin_ratio,
                    "threshold_ratio": self.threshold_ratio,
                    "account_balance": context.account_balance,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class ConsecutiveLossTrigger(BaseTrigger):
    """
    Consecutive loss trigger
    
    Fires when consecutive losses exceed threshold.
    """
    
    def __init__(
        self,
        threshold_losses: int = 5,
        **kwargs
    ):
        """
        Initialize consecutive loss trigger
        
        Args:
            threshold_losses: Maximum consecutive losses before trigger
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="consecutive_loss_warning",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.threshold_losses = threshold_losses
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if consecutive losses exceed threshold"""
        consecutive_losses = context.get("consecutive_losses", 0)
        
        if consecutive_losses >= self.threshold_losses:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=TriggerSeverity.HIGH,
                data={
                    "consecutive_losses": consecutive_losses,
                    "threshold_losses": self.threshold_losses,
                },
                timestamp=context.timestamp,
            )
        
        return None


class DrawdownTrigger(BaseTrigger):
    """
    Drawdown trigger
    
    Fires when drawdown exceeds threshold.
    """
    
    def __init__(
        self,
        threshold_drawdown: float = 0.2,
        **kwargs
    ):
        """
        Initialize drawdown trigger
        
        Args:
            threshold_drawdown: Drawdown threshold (e.g., 0.2 for 20%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="drawdown_warning",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.threshold_drawdown = threshold_drawdown
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if drawdown exceeds threshold"""
        current_drawdown = context.get("current_drawdown", 0.0)
        
        if current_drawdown >= self.threshold_drawdown:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=TriggerSeverity.HIGH,
                data={
                    "current_drawdown": current_drawdown,
                    "threshold_drawdown": self.threshold_drawdown,
                    "peak_balance": context.get("peak_balance", 0.0),
                    "account_balance": context.account_balance,
                },
                timestamp=context.timestamp,
            )
        
        return None


class VaRTrigger(BaseTrigger):
    """
    Value at Risk (VaR) trigger
    
    Fires when VaR exceeds threshold.
    """
    
    def __init__(
        self,
        threshold_var: float = 0.05,
        confidence_level: float = 0.95,
        **kwargs
    ):
        """
        Initialize VaR trigger
        
        Args:
            threshold_var: VaR threshold (e.g., 0.05 for 5% of portfolio)
            confidence_level: Confidence level for VaR calculation (e.g., 0.95 for 95%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="var_warning",
            priority=TriggerPriority.HIGH,
            severity=TriggerSeverity.HIGH,
            **kwargs
        )
        self.threshold_var = threshold_var
        self.confidence_level = confidence_level
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if VaR exceeds threshold"""
        var_95 = context.get("var_95", 0.0)
        var_99 = context.get("var_99", 0.0)
        
        # Use appropriate VaR based on confidence level
        current_var = var_99 if self.confidence_level >= 0.99 else var_95
        
        if current_var >= self.threshold_var:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=TriggerSeverity.HIGH,
                data={
                    "var_95": var_95,
                    "var_99": var_99,
                    "current_var": current_var,
                    "threshold_var": self.threshold_var,
                    "confidence_level": self.confidence_level,
                    "account_balance": context.account_balance,
                },
                timestamp=context.timestamp,
            )
        
        return None


class PositionSizeTrigger(BaseTrigger):
    """
    Position size trigger
    
    Fires when position size exceeds threshold.
    """
    
    def __init__(
        self,
        threshold_size_usdt: float = 1000.0,
        **kwargs
    ):
        """
        Initialize position size trigger
        
        Args:
            threshold_size_usdt: Position size threshold in USDT
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="position_size_warning",
            priority=TriggerPriority.MEDIUM,
            severity=TriggerSeverity.MEDIUM,
            **kwargs
        )
        self.threshold_size_usdt = threshold_size_usdt
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if position size exceeds threshold"""
        total_position_size = context.get("total_position_size", 0.0)
        
        if total_position_size >= self.threshold_size_usdt:
            return TriggerEvent(
                event_id="",
                trigger_name=self.name,
                severity=TriggerSeverity.MEDIUM,
                data={
                    "total_position_size": total_position_size,
                    "threshold_size_usdt": self.threshold_size_usdt,
                    "positions": context.positions,
                },
                timestamp=context.timestamp,
                symbol=context.symbol,
            )
        
        return None


class LiquidationRiskTrigger(BaseTrigger):
    """
    Liquidation risk trigger
    
    Fires when position is at risk of liquidation.
    """
    
    def __init__(
        self,
        buffer_pct: float = 0.1,
        **kwargs
    ):
        """
        Initialize liquidation risk trigger
        
        Args:
            buffer_pct: Buffer percentage from liquidation price (e.g., 0.1 for 10%)
            **kwargs: Additional arguments passed to BaseTrigger
        """
        super().__init__(
            name="liquidation_risk_warning",
            priority=TriggerPriority.CRITICAL,
            severity=TriggerSeverity.CRITICAL,
            **kwargs
        )
        self.buffer_pct = buffer_pct
    
    async def check(self, context: TriggerContext) -> Optional[TriggerEvent]:
        """Check if any position is at liquidation risk"""
        liquidation_risks = []
        
        for position in context.positions:
            entry_price = position.get("entry_price", 0.0)
            liquidation_price = position.get("liquidation_price", 0.0)
            side = position.get("side", "LONG")
            
            if liquidation_price <= 0 or entry_price <= 0:
                continue
            
            # Calculate distance from liquidation
            if side == "LONG":
                distance_pct = (context.current_price - liquidation_price) / context.current_price
            else:
                distance_pct = (liquidation_price - context.current_price) / context.current_price
            
            liquidation_risks.append({
                "symbol": position.get("symbol"),
                "side": side,
                "distance_pct": distance_pct,
                "liquidation_price": liquidation_price,
                "current_price": context.current_price,
            })
            
            # Check if position is in danger
            if distance_pct <= self.buffer_pct:
                return TriggerEvent(
                    event_id="",
                    trigger_name=self.name,
                    severity=TriggerSeverity.CRITICAL,
                    data={
                        "liquidation_risks": liquidation_risks,
                        "buffer_pct": self.buffer_pct,
                        "positions": context.positions,
                    },
                    timestamp=context.timestamp,
                    symbol=position.get("symbol"),
                )
        
        return None