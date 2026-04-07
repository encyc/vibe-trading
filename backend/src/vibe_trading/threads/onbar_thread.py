"""
On Bar Thread

K-line triggered main trading thread using full coordinator.
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from vibe_trading.coordinator.trading_coordinator import (
    TradingCoordinator,
    TradingDecision,
)
from vibe_trading.coordinator.thread_manager import ThreadManager, get_thread_manager
from vibe_trading.agents.messaging import get_message_broker, MessageType
from vibe_trading.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


class OnBarThread:
    """
    On Bar thread
    
    Subscribes to K-line data and executes full 5-phase decision flow.
    """
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "30m",
        thread_manager: Optional[ThreadManager] = None,
    ):
        """
        Initialize On Bar thread
        
        Args:
            symbol: Trading symbol
            interval: Time interval
            thread_manager: Thread manager instance
        """
        self.symbol = symbol
        self.interval = interval
        self.thread_manager = thread_manager or get_thread_manager()
        
        # Coordinator
        self._coordinator: Optional[TradingCoordinator] = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._emergency_mode = False
        
        # Statistics
        self._total_bars = 0
        self._decisions_made = 0
        self._emergency_stops = 0
        self._last_bar_time: Optional[datetime] = None
        
        logger.info(f"OnBarThread initialized for {symbol} ({interval})")
    
    async def initialize(self) -> None:
        """Initialize the thread"""
        # Initialize coordinator with full agent team
        self._coordinator = TradingCoordinator(
            symbol=self.symbol,
            interval=self.interval,
        )
        await self._coordinator.initialize()
        
        logger.info("OnBarThread initialized with full agent team")
    
    async def start(self) -> None:
        """Start the On Bar thread"""
        if self._running:
            logger.warning("OnBarThread already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("OnBarThread started")
    
    async def stop(self) -> None:
        """Stop the On Bar thread"""
        if not self._running:
            logger.warning("OnBarThread not running")
            return
        
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("OnBarThread stopped")
    
    async def _run_loop(self) -> None:
        """Main loop for K-line processing"""
        try:
            # Get WebSocket manager
            ws_manager = get_websocket_manager(
                api_key=None,  # Paper trading mode
                api_secret=None,
                testnet=True,
            )

            # Subscribe to K-line stream
            await ws_manager.subscribe_kline(
                symbol=self.symbol,
                interval=self.interval,
                callback=self._process_kline,
            )

            # Start WebSocket
            await ws_manager.start()

            # Keep running while thread is active
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("OnBarThread cancelled")
        except Exception as e:
            logger.error(f"Error in OnBarThread loop: {e}", exc_info=True)
        finally:
            # Stop WebSocket
            if 'ws_manager' in locals():
                await ws_manager.stop()
    
    async def _process_kline(self, kline) -> None:
        """
        Process K-line data
        
        Args:
            kline: K-line data
        """
        self._total_bars += 1
        self._last_bar_time = datetime.now()
        
        # Extract price
        close_price = float(kline.close)
        
        logger.debug(f"Processing K-line: {self.symbol} @ ${close_price:.2f}")
        
        try:
            # Execute full 5-phase decision flow with all 13 agents
            decision = await self._coordinator.analyze_and_decide(
                current_price=close_price,
                account_balance=10000.0,  # Would get from account
                current_positions=[],  # Would get from position manager
            )
            
            self._decisions_made += 1
            
            # Log decision
            logger.info(
                f"Decision: {decision.decision} - {decision.rationale[:100]}..."
            )
            
            # Send message
            message_broker = get_message_broker()
            message_broker.send(
                sender="onbar_thread",
                receiver="all",
                message_type=MessageType.INFO,
                content={
                    "type": "trading_decision",
                    "symbol": self.symbol,
                    "decision": decision.decision,
                    "price": close_price,
                },
                correlation_id=f"onbar_{int(datetime.now().timestamp() * 1000)}",
            )
            
            # Execute trade if needed
            if decision.decision in ["BUY", "SELL", "STRONG_BUY", "STRONG_SELL"]:
                await self._execute_trade(decision)
            
        except Exception as e:
            logger.error(f"Error in decision flow: {e}", exc_info=True)
    
    async def _execute_trade(self, decision: TradingDecision) -> None:
        """
        Execute trading decision
        
        Args:
            decision: Trading decision
        """
        logger.info(f"Executing trade: {decision.decision}")
        
        # TODO: Implement actual trade execution
        # This would integrate with OrderExecutor
        
        # For now, just log
        logger.info(f"Trade execution placeholder: {decision.decision}")
    
    async def _is_emergency_mode(self) -> bool:
        """
        Check if system is in emergency mode
        
        Returns:
            True if in emergency mode
        """
        return await self.thread_manager.is_emergency_mode()
    
    async def _handle_emergency_message(self, message) -> None:
        """
        Handle emergency message
        
        Args:
            message: Emergency message
        """
        content = message.content
        action = content.get("action")
        
        if action == "emergency_stop":
            logger.warning("Received emergency stop command")
            self._emergency_mode = True
        elif action == "emergency_resume":
            logger.info("Received emergency resume command")
            self._emergency_mode = False
        elif action == "emergency_suggestion":
            logger.info(f"Received emergency suggestion: {content.get('suggestion')}")
            # Handle suggestion
    
    def get_statistics(self) -> Dict:
        """
        Get thread statistics
        
        Returns:
            Dictionary of statistics
        """
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "running": self._running,
            "emergency_mode": self._emergency_mode,
            "total_bars": self._total_bars,
            "decisions_made": self._decisions_made,
            "emergency_stops": self._emergency_stops,
            "decision_rate": (
                self._decisions_made / self._total_bars
                if self._total_bars > 0 else 0.0
            ),
            "last_bar_time": (
                self._last_bar_time.isoformat()
                if self._last_bar_time else None
            ),
        }
    
    async def run_once(self, price: float) -> Optional[Dict]:
        """
        Run decision flow once (for testing)
        
        Args:
            price: Current price
            
        Returns:
            Decision or None if failed
        """
        try:
            logger.info(f"Running OnBarThread once for {self.symbol} @ ${price:.2f}")
            
            # Execute full 5-phase decision flow with all 13 agents
            decision = await self._coordinator.analyze_and_decide(
                current_price=price,
                account_balance=10000.0,
                current_positions=[],
            )
            
            logger.info(f"Decision: {decision.decision}")
            return decision.to_dict()
            
        except Exception as e:
            logger.error(f"Error running OnBarThread once: {e}", exc_info=True)
            return None